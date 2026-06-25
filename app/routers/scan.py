import uuid
import os
from fastapi import APIRouter, Request, UploadFile, File, Form, BackgroundTasks, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from app.utils.db import (
    create_scan, get_scan, get_scan_issues, get_scan_history, delete_scan,
    get_user_by_session, create_audit_log
)
from app.utils.rate_limiter import scan_limiter, get_client_ip
from app.utils.file_handler import save_uploaded_file, save_pasted_code, delete_scan_dir
from app.utils.fix_suggestions import get_fix_suggestion
from app.utils.report_generator import (
    export_html_report, export_json_report, export_csv_report, export_pdf_report
)
from app.scanners.scanner import run_scan

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.cache = None  # Workaround for Python 3.14 + Jinja2 cache key TypeError

def render_template(request: Request, name: str, context: dict = None, status_code: int = 200):
    """Render templates injecting the admin user if a valid session is active."""
    if context is None:
        context = {}
    token = request.cookies.get("session_token")
    admin_user = None
    if token:
        admin_user = get_user_by_session(token)
    context["request"] = request
    context["admin"] = admin_user
    return templates.TemplateResponse(request=request, name=name, context=context, status_code=status_code)

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Renders the dashboard homepage."""
    return render_template(request, "index.html")

@router.post("/api/scan")
async def trigger_scan(
    request: Request,
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    code: Optional[str] = Form(None),
    extension: str = Form("py")
):
    ip = get_client_ip(request)
    if not scan_limiter.is_allowed(ip):
        raise HTTPException(status_code=429, detail="Too many scans submitted. Please wait a minute.")
        
    # Origin verification to prevent CSRF
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if origin and host not in origin:
        raise HTTPException(status_code=403, detail="CSRF check failed: Origin mismatch.")
    """
    Handles user uploads (files or .zip) or pasted code.
    Initiates parallel scans in the background.
    """
    scan_id = uuid.uuid4().hex
    filename = "Pasted Code"
    file_size = 0
    temp_path = ""
    
    if file and file.filename:
        # User uploaded a file/ZIP
        filename = file.filename
        # Read a chunk to check size (up to 10MB)
        contents = await file.read()
        file_size = len(contents)
        
        # Max file size limit: 10MB
        if file_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds maximum limit of 10MB.")
            
        # Reset cursor position
        await file.seek(0)
        
        # Save uploaded file
        temp_path, is_zip = save_uploaded_file(file, scan_id)
    elif code and code.strip():
        # User pasted raw code
        file_size = len(code.encode("utf-8"))
        if file_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Pasted code exceeds maximum limit of 10MB.")
            
        temp_path = save_pasted_code(code, scan_id, extension)
    else:
        # No file or code provided
        raise HTTPException(status_code=400, detail="Please upload a file or paste your code to scan.")

    # Create scan entry in SQLite (pending status)
    create_scan(scan_id, filename, file_size)
    
    # Run scan orchestrator in background task
    background_tasks.add_task(run_scan, scan_id, temp_path)
    
    # If request is HTMX, redirect via HTMX header
    if "hx-request" in request.headers:
        return Response(headers={"HX-Redirect": f"/scans/{scan_id}"})
    
    return RedirectResponse(url=f"/scans/{scan_id}", status_code=303)

@router.get("/scans/{scan_id}", response_class=HTMLResponse)
async def scan_results(request: Request, scan_id: str):
    """Renders the outer results page layout."""
    scan = get_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan report not found.")
    return render_template(request, "results.html", {"scan_id": scan_id, "scan": scan})

@router.get("/scans/{scan_id}/status", response_class=HTMLResponse)
async def scan_status(request: Request, scan_id: str):
    """
    Renders loading screen while scanning,
    or the rich dashboard fragment when completed.
    """
    scan = get_scan(scan_id)
    if not scan:
        return HTMLResponse("<div class='alert alert-error'>Scan record missing.</div>")
        
    status = scan["status"]
    
    if status in ("pending", "running"):
        return render_template(request, "fragments/loading.html", {
            "scan_id": scan_id,
            "scan": scan
        })
    elif status == "failed":
        return render_template(request, "fragments/error.html", {
            "scan": scan
        })
    else:
        # Status is completed
        issues = get_scan_issues(scan_id)
        
        # Hydrate issues with fix recommendations and docs links
        rich_issues = []
        for issue in issues:
            rule_id = issue.get("rule_id", "")
            message = issue.get("message", "")
            fix = get_fix_suggestion(rule_id, message)
            
            rich_issues.append({
                **issue,
                "fix_title": fix["title"],
                "fix_description": fix["description"],
                "fix_before": fix["before"],
                "fix_after": fix["after"],
                "doc_url": fix["doc_url"]
            })
            
        return render_template(request, "dashboard_metrics.html", {
            "scan": scan,
            "issues": rich_issues
        })

@router.get("/scans/{scan_id}/export/{export_format}")
async def export_report(scan_id: str, export_format: str):
    """Exports scan report in PDF, HTML, JSON, or CSV format."""
    scan = get_scan(scan_id)
    if not scan or scan["status"] != "completed":
        raise HTTPException(status_code=404, detail="Scan results not ready or scan failed.")
        
    issues = get_scan_issues(scan_id)
    export_format = export_format.lower()
    
    filename_base = f"codevanguard_{scan_id}"
    
    if export_format == "html":
        content = export_html_report(scan, issues)
        return Response(
            content=content,
            media_type="text/html",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.html"}
        )
    elif export_format == "json":
        content = export_json_report(scan, issues)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.json"}
        )
    elif export_format == "csv":
        content = export_csv_report(scan, issues)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.csv"}
        )
    elif export_format == "pdf":
        try:
            content = export_pdf_report(scan, issues)
            return Response(
                content=content,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename_base}.pdf"}
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF Generation failed: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="Invalid export format. Choose from html, pdf, json, or csv.")

@router.get("/history", response_class=HTMLResponse)
async def scan_history(request: Request):
    """Renders the list of previous scans."""
    history = get_scan_history()
    return render_template(request, "history.html", {"history": history})

@router.delete("/scans/{scan_id}", response_class=HTMLResponse)
async def remove_scan(request: Request, scan_id: str):
    """Deletes a scan record and its database entries + files (restricted to admins)."""
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized: Session missing.")
    user = get_user_by_session(token)
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Unauthorized: Admins only.")
        
    # Origin verification to prevent CSRF
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if origin and host not in origin:
        raise HTTPException(status_code=403, detail="CSRF check failed: Origin mismatch.")
        
    ip = get_client_ip(request)
    delete_scan(scan_id)
    delete_scan_dir(scan_id)
    create_audit_log(user["id"], "scan_delete", f"Deleted scan: {scan_id}", ip)
    return HTMLResponse(content="")

@router.get("/examples", response_class=HTMLResponse)
async def vulnerable_gallery(request: Request):
    """Renders the vulnerable code gallery for easy demo testing."""
    return render_template(request, "examples.html")

# --- REST JSON API ENDPOINTS ---

@router.post("/api/scan/json")
async def trigger_scan_json(
    request: Request,
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    code: Optional[str] = Form(None),
    extension: str = Form("py")
):
    """Processes code/file uploads and returns a JSON response containing the scan_id."""
    ip = get_client_ip(request)
    if not scan_limiter.is_allowed(ip):
        raise HTTPException(status_code=429, detail="Too many scans submitted. Please wait a minute.")
        
    scan_id = uuid.uuid4().hex
    filename = "Pasted Code"
    file_size = 0
    temp_path = ""
    
    if file and file.filename:
        filename = file.filename
        contents = await file.read()
        file_size = len(contents)
        if file_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds maximum limit of 10MB.")
        await file.seek(0)
        temp_path, is_zip = save_uploaded_file(file, scan_id)
    elif code and code.strip():
        file_size = len(code.encode("utf-8"))
        if file_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Pasted code exceeds maximum limit of 10MB.")
        temp_path = save_pasted_code(code, scan_id, extension)
    else:
        raise HTTPException(status_code=400, detail="Please upload a file or paste your code to scan.")

    create_scan(scan_id, filename, file_size)
    background_tasks.add_task(run_scan, scan_id, temp_path)
    
    return {"status": "success", "scan_id": scan_id}

@router.get("/api/scans/{scan_id}/status")
async def scan_status_json(scan_id: str):
    """Returns JSON scan metadata and status."""
    scan = get_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan record missing.")
    return {
        "id": scan_id,
        "status": scan["status"],
        "error_message": scan["error_message"],
        "total_issues": scan["total_issues"],
        "critical_count": scan["critical_count"],
        "high_count": scan["high_count"],
        "medium_count": scan["medium_count"],
        "low_count": scan["low_count"],
        "filename": scan["filename"],
        "timestamp": scan["timestamp"],
        "file_size": scan["file_size"]
    }

@router.get("/api/scans/{scan_id}/issues")
async def scan_issues_json(scan_id: str):
    """Returns JSON list of findings complete with remediation snippets."""
    scan = get_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan record missing.")
    
    issues = get_scan_issues(scan_id)
    rich_issues = []
    for issue in issues:
        rule_id = issue.get("rule_id", "")
        message = issue.get("message", "")
        fix = get_fix_suggestion(rule_id, message)
        
        rich_issues.append({
            **issue,
            "fix_title": fix["title"],
            "fix_description": fix["description"],
            "fix_before": fix["before"],
            "fix_after": fix["after"],
            "doc_url": fix["doc_url"]
        })
    return {"scan": scan, "issues": rich_issues}

@router.get("/api/history/json")
async def scan_history_json():
    """Returns JSON list of scan history."""
    history = get_scan_history()
    return {"history": history}

from fastapi import Depends
from app.routers.admin import get_current_admin_api

@router.delete("/api/scans/{scan_id}")
async def remove_scan_json(scan_id: str, admin_user: dict = Depends(get_current_admin_api)):
    """Deletes a scan record and its database entries + files. Requires Bearer authentication."""
    delete_scan(scan_id)
    delete_scan_dir(scan_id)
    return {"status": "success", "message": f"Scan {scan_id} deleted successfully."}

