import os
from datetime import datetime
from fastapi import APIRouter, Request, Response, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.utils.db import (
    authenticate_user, create_session, get_user_by_session, delete_session,
    get_audit_logs, create_audit_log, get_db_stats, wipe_all_data, get_scan_history
)
from app.utils.rate_limiter import login_limiter, get_client_ip

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")
templates.env.cache = None

def render_admin_template(request: Request, name: str, context: dict = None, status_code: int = 200):
    """Render templates with automatically populated admin context from cookies."""
    if context is None:
        context = {}
    token = request.cookies.get("session_token")
    admin_user = None
    if token:
        admin_user = get_user_by_session(token)
        
    context["request"] = request
    context["admin"] = admin_user
    return templates.TemplateResponse(request=request, name=name, context=context, status_code=status_code)

async def get_current_admin(request: Request):
    """Route dependency ensuring a valid admin session cookie is present."""
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Session missing.")
    user = get_user_by_session(token)
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=401, detail="Invalid admin session.")
    return user

@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """Renders the admin login page or redirects if already authenticated."""
    token = request.cookies.get("session_token")
    if token and get_user_by_session(token):
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    return render_admin_template(request, "admin_login.html")

@router.post("/login")
async def admin_login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...)
):
    """Validates login credentials, handles rate limits, sets HttpOnly cookies, and creates sessions."""
    ip = get_client_ip(request)
    
    # Rate Limiting Check
    if not login_limiter.is_allowed(ip):
        return render_admin_template(request, "admin_login.html", {
            "error": "Too many failed login attempts. Please wait 15 minutes."
        }, status_code=429)
        
    user = authenticate_user(username, password)
    if not user:
        # Log the failed login under system account (user_id=1 corresponds to admin)
        create_audit_log(1, "login_failed", f"Failed login attempt for username: {username}", ip)
        return render_admin_template(request, "admin_login.html", {
            "error": "Invalid username or password."
        }, status_code=401)
        
    if user["role"] != "admin":
        create_audit_log(user["id"], "login_failed", "Non-admin attempted to login to admin portal", ip)
        return render_admin_template(request, "admin_login.html", {
            "error": "Access denied. Admins only."
        }, status_code=403)
        
    # Successful Session Creation
    token = create_session(user["id"])
    create_audit_log(user["id"], "login_success", "Admin logged in successfully", ip)
    
    redirect = RedirectResponse(url="/admin/dashboard", status_code=303)
    # Set secure HttpOnly session cookie (enforce secure=True in production mode)
    secure = os.environ.get("ENV", "development").lower() == "production"
    redirect.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=3600
    )
    return redirect

@router.get("/logout")
async def admin_logout(request: Request):
    """Purges the session token, logs audit event, and clears cookie."""
    token = request.cookies.get("session_token")
    if token:
        user = get_user_by_session(token)
        if user:
            ip = request.client.host if request.client else "unknown"
            create_audit_log(user["id"], "logout", "Admin logged out", ip)
            delete_session(token)
            
    redirect = RedirectResponse(url="/admin/login", status_code=303)
    redirect.delete_cookie(key="session_token")
    return redirect

@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Gathers audit logs and scan metrics, rendering the admin dashboard."""
    try:
        await get_current_admin(request)
    except HTTPException:
        return RedirectResponse(url="/admin/login", status_code=303)
        
    stats = get_db_stats()
    audit_logs = get_audit_logs()
    history = get_scan_history()
    
    return render_admin_template(request, "admin_dashboard.html", {
        "stats": stats,
        "audit_logs": audit_logs,
        "history": history
    })

@router.post("/wipe")
async def wipe_database(request: Request):
    """Purges database tables scans/issues/logs with admin session & CSRF origin validations."""
    try:
        user = await get_current_admin(request)
    except HTTPException:
        raise HTTPException(status_code=403, detail="Unauthorized action.")
        
    # Simple Origin header CSRF validation
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if origin and host not in origin:
        raise HTTPException(status_code=403, detail="CSRF check failed: Origin mismatch.")
        
    ip = request.client.host if request.client else "unknown"
    wipe_all_data()
    create_audit_log(user["id"], "database_wipe", "Admin purged all database records", ip)
    
    return RedirectResponse(url="/admin/dashboard", status_code=303)


# --- REST JSON API ENDPOINTS FOR ADMIN ---

from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str
    password: str

async def get_current_admin_api(request: Request):
    """Route dependency ensuring a valid admin session Bearer token or cookie is present."""
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    else:
        token = request.cookies.get("session_token")
        
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token missing.")
        
    user = get_user_by_session(token)
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=401, detail="Invalid token or unauthorized role.")
    return user

@router.post("/api/login")
async def admin_login_json(request: Request, login_data: LoginRequest):
    """Validates login credentials, handles rate limits, and returns a session token."""
    ip = get_client_ip(request)
    
    # Rate Limiting Check
    if not login_limiter.is_allowed(ip):
        raise HTTPException(status_code=429, detail="Too many failed login attempts. Please wait 15 minutes.")
        
    user = authenticate_user(login_data.username, login_data.password)
    if not user:
        create_audit_log(1, "login_failed", f"Failed API login attempt for username: {login_data.username}", ip)
        raise HTTPException(status_code=401, detail="Invalid username or password.")
        
    if user["role"] != "admin":
        create_audit_log(user["id"], "login_failed", "Non-admin attempted to login to admin portal via API", ip)
        raise HTTPException(status_code=403, detail="Access denied. Admins only.")
        
    # Successful Session Creation
    token = create_session(user["id"])
    create_audit_log(user["id"], "login_success", "Admin logged in successfully via API", ip)
    
    return {
        "status": "success",
        "token": token,
        "username": user["username"],
        "role": user["role"]
    }

@router.get("/api/stats")
async def admin_stats_json(admin_user: dict = Depends(get_current_admin_api)):
    """Returns database stats and audit logs for the authenticated admin."""
    stats = get_db_stats()
    audit_logs = get_audit_logs()
    history = get_scan_history()
    
    return {
        "stats": stats,
        "audit_logs": audit_logs,
        "history": history
    }

@router.post("/api/wipe")
async def wipe_database_json(request: Request, admin_user: dict = Depends(get_current_admin_api)):
    """Purges the database (scans, issues, logs, sessions). Requires Bearer authentication."""
    ip = request.client.host if request.client else "unknown"
    wipe_all_data()
    create_audit_log(admin_user["id"], "database_wipe", "Admin purged all database records via API", ip)
    
    return {"status": "success", "message": "Database wiped successfully."}

