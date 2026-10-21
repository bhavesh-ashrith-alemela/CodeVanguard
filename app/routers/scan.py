import uuid
import os
try:
    from fastapi import APIRouter, Request, UploadFile, File, Form, BackgroundTasks, HTTPException, Response, Body, Depends
    from fastapi.responses import HTMLResponse, RedirectResponse
    from fastapi.templating import Jinja2Templates
except ImportError:
    class APIRouter:
        def __init__(self, *args, **kwargs): pass
        def get(self, *args, **kwargs): return lambda f: f
        def post(self, *args, **kwargs): return lambda f: f
        def delete(self, *args, **kwargs): return lambda f: f
    from app.utils.auth import HTTPException
    Request = object
    UploadFile = object
    File = lambda default=None, **kwargs: default
    Form = lambda default=None, **kwargs: default
    Body = lambda default=None, **kwargs: default
    BackgroundTasks = object
    Response = object
    Depends = lambda f=None: f
    HTMLResponse = object
    RedirectResponse = object
    class Jinja2Templates:
        def __init__(self, *args, **kwargs):
            self.env = type("Env", (), {"cache": None})()
from typing import Optional

from app.utils.db import (
    create_scan, get_scan, get_scan_issues, get_scan_history, delete_scan,
    get_user_by_session, create_audit_log
)
from app.utils.rate_limiter import scan_limiter, get_client_ip, acquire_active_scan, release_active_scan
from app.utils.file_handler import save_uploaded_file, save_pasted_code, delete_scan_dir
from app.utils.fix_suggestions import get_fix_suggestion
from app.utils.report_generator import (
    export_html_report, export_json_report, export_csv_report, export_pdf_report
)
from app.utils.github import validate_github_url, validate_branch_name, resolve_github_repo
from app.utils.security import verify_origin_or_csrf
from app.queue.redis_pool import enqueue_scan_job
from app.models.scan_result import RepoScanRequest
from app.routers.admin import get_current_admin_api
from app.utils.auth import require_scan_access, get_current_user_optional

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.cache = None

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
    """
    Handles user uploads (files or .zip) or pasted code from web forms.
    Initiates parallel scans in the background.
    """
    ip = get_client_ip(request)
    if not scan_limiter.is_allowed(ip):
        raise HTTPException(status_code=429, detail="Too many scans submitted. Please wait a minute.")
        
    # Protect against CSRF
    from app.utils.security import verify_csrf
    verify_csrf(request)

    scan_id = uuid.uuid4().hex
    filename = "Pasted Code"
    file_size = 0
    temp_path = ""
    source_type = "paste"
    
    if file and file.filename:
        filename = file.filename
        contents = await file.read()
        file_size = len(contents)
        
        if file_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds maximum limit of 10MB.")
            
        await file.seek(0)
        temp_path, is_zip = save_uploaded_file(file, scan_id)
        source_type = "zip" if is_zip else "paste"
    elif code and code.strip():
        file_size = len(code.encode("utf-8"))
        if file_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Pasted code exceeds maximum limit of 10MB.")
            
        temp_path = save_pasted_code(code, scan_id, extension)
        source_type = "paste"
    else:
        raise HTTPException(status_code=400, detail="Please upload a file or paste your code to scan.")

    # Concurrency and active scan cap
    allowed, reason = acquire_active_scan(ip, scan_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    create_scan(scan_id, filename, file_size, source_type=source_type)
    await enqueue_scan_job(scan_id, client_ip=ip, background_tasks=background_tasks)
    
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
    Renders loading screen with stage progress while scanning,
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
            
        return render_template(request, "dashboard_metrics.html", {
            "scan": scan,
            "issues": rich_issues
        })

@router.get("/scans/{scan_id}/export/{export_format}")
@router.get("/api/scans/{scan_id}/export/{export_format}")
async def export_report(request: Request, scan_id: str, export_format: str):
    """Exports scan report in PDF, HTML, JSON, or CSV format. Protected by require_scan_access."""
    scan = require_scan_access(request, scan_id)
    if scan["status"] != "completed":
        raise HTTPException(status_code=400, detail="Scan results not ready or scan failed.")
        
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
    elif export_format == "sarif":
        from app.utils.sarif import generate_sarif_report
        sarif_doc = generate_sarif_report(scan, issues)
        return Response(
            content=json.dumps(sarif_doc, indent=2),
            media_type="application/sarif+json",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.sarif"}
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid export format. Choose from html, pdf, json, csv, or sarif.")

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
        
    from app.utils.security import verify_csrf
    verify_csrf(request)
        
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
    verify_origin_or_csrf(request)

    ip = get_client_ip(request)
    if not scan_limiter.is_allowed(ip):
        raise HTTPException(status_code=429, detail="Too many scans submitted. Please wait a minute.")
        
    scan_id = uuid.uuid4().hex
    filename = "Pasted Code"
    file_size = 0
    temp_path = ""
    source_type = "paste"
    
    if file and file.filename:
        filename = file.filename
        contents = await file.read()
        file_size = len(contents)
        if file_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds maximum limit of 10MB.")
        await file.seek(0)
        temp_path, is_zip = save_uploaded_file(file, scan_id)
        source_type = "zip" if is_zip else "paste"
    elif code and code.strip():
        file_size = len(code.encode("utf-8"))
        if file_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Pasted code exceeds maximum limit of 10MB.")
        temp_path = save_pasted_code(code, scan_id, extension)
        source_type = "paste"
    else:
        raise HTTPException(status_code=400, detail="Please upload a file or paste your code to scan.")

    # Concurrency and active scan cap
    allowed, reason = acquire_active_scan(ip, scan_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    create_scan(scan_id, filename, file_size, source_type=source_type)
    await enqueue_scan_job(scan_id, client_ip=ip, background_tasks=background_tasks)
    
    return {"status": "success", "scan_id": scan_id}

@router.post("/api/scan/repo")
async def trigger_scan_repo(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Optional[RepoScanRequest] = Body(None),
    url: Optional[str] = Form(None),
    branch: Optional[str] = Form(None)
):
    """
    Intakes a public GitHub repository URL, performs strict SSRF validation,
    resolves commit SHA and default branch via GitHub REST API, enforces MAX_REPO_KB,
    creates the scan record, and enqueues the scan job.
    """
    verify_origin_or_csrf(request)

    ip = get_client_ip(request)
    if not scan_limiter.is_allowed(ip):
        raise HTTPException(status_code=429, detail="Too many scans submitted. Please wait a minute.")

    # Support JSON payload or Form data
    target_url = (payload.url if payload else None) or url
    target_branch = (payload.branch if payload else None) or branch

    if not target_url or not target_url.strip():
        raise HTTPException(status_code=400, detail="Repository URL must be provided.")

    scan_id = uuid.uuid4().hex

    # 1. Acquire active scan lock upfront to prevent rate limit & resource exhaustion
    allowed, reason = acquire_active_scan(ip, scan_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    try:
        # 2. Strict URL validation
        owner, repo = validate_github_url(target_url)

        # 3. Branch validation
        clean_branch = validate_branch_name(target_branch)

        # 4. Resolve Commit SHA and verify size via GitHub API
        repo_info = resolve_github_repo(owner, repo, clean_branch)
    except ValueError as e:
        release_active_scan(ip, scan_id)
        err_msg = str(e)
        if "not found" in err_msg.lower():
            raise HTTPException(status_code=404, detail=err_msg)
        elif "rate limit" in err_msg.lower():
            raise HTTPException(status_code=429, detail=err_msg)
        else:
            raise HTTPException(status_code=400, detail=err_msg)
    except Exception:
        release_active_scan(ip, scan_id)
        raise

    filename = f"{owner}/{repo}@{repo_info.resolved_branch}"
    file_size = repo_info.size_kb * 1024

    create_scan(
        scan_id=scan_id,
        filename=filename,
        file_size=file_size,
        source_type="github_public",
        source_url=f"https://github.com/{owner}/{repo}",
        branch=repo_info.resolved_branch,
        commit_sha=repo_info.commit_sha
    )

    await enqueue_scan_job(scan_id, client_ip=ip, background_tasks=background_tasks)

    return {
        "status": "success",
        "scan_id": scan_id,
        "owner": owner,
        "repo": repo,
        "branch": repo_info.resolved_branch,
        "commit_sha": repo_info.commit_sha
    }

@router.get("/api/scans/{scan_id}/status")
async def scan_status_json(request: Request, scan_id: str):
    """Returns JSON scan metadata, execution stage, and metrics. Protected by require_scan_access."""
    scan = require_scan_access(request, scan_id)
    return {
        "id": scan_id,
        "repo_id": scan.get("repo_id"),
        "owner_user_id": scan.get("owner_user_id"),
        "trigger": scan.get("trigger", "manual"),
        "pr_number": scan.get("pr_number"),
        "status": scan["status"],
        "progress": scan.get("progress", "queued"),
        "error_message": scan.get("error_message"),
        "total_issues": scan.get("total_issues", 0),
        "critical_count": scan.get("critical_count", 0),
        "high_count": scan.get("high_count", 0),
        "medium_count": scan.get("medium_count", 0),
        "low_count": scan.get("low_count", 0),
        "filename": scan["filename"],
        "timestamp": scan["timestamp"],
        "file_size": scan["file_size"],
        "source_type": scan.get("source_type", "paste"),
        "source_url": scan.get("source_url"),
        "branch": scan.get("branch"),
        "commit_sha": scan.get("commit_sha"),
        "duration_ms": scan.get("duration_ms", 0),
        "files_scanned": scan.get("files_scanned", 0),
        "files_skipped": scan.get("files_skipped", 0)
    }

@router.get("/api/scans/{scan_id}/issues")
async def scan_issues_json(request: Request, scan_id: str):
    """Returns JSON list of findings with remediation snippets and fingerprints. Protected by require_scan_access."""
    scan = require_scan_access(request, scan_id)
    
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
async def scan_history_json(request: Request):
    """
    Returns JSON list of scan history:
    - Admins view all scans.
    - Authenticated users view only their personal and installation repo scans.
    - Unauthenticated requests are rejected with 401.
    """
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")

    if user.get("role") == "admin":
        history = get_scan_history()
    else:
        history = get_scan_history(user_id=user["id"])

    return {"history": history}

@router.delete("/api/scans/{scan_id}")
async def remove_scan_json(request: Request, scan_id: str):
    """
    Deletes a scan record and its database entries + files.
    - Repository scans: authorized if user is an admin of the repo's installation or site admin.
    - User-owned scans: authorized if user is the owner or site admin.
    - Anonymous scans: strictly requires admin authentication.
    """
    scan = require_scan_access(request, scan_id)
    user = get_current_user_optional(request)

    is_admin = user and user.get("role") == "admin"
    is_owner = user and scan.get("owner_user_id") and user["id"] == scan["owner_user_id"]

    if not is_admin and not is_owner:
        raise HTTPException(
            status_code=403,
            detail="Permission denied: Only the scan owner or administrator can delete this scan."
        )

    delete_scan(scan_id)
    delete_scan_dir(scan_id)
    return {"status": "success", "message": f"Scan {scan_id} deleted successfully."}
