import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

from app.utils.db import init_db
from app.utils.github_app import install_log_redaction_filter
from app.utils.error_monitoring import init_error_monitoring, capture_exception
from app.routers import scan, admin, auth, repos, webhook, findings, pulls, badge, autofix, status

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions: Initialize schema and install token redaction filter
    print("CodeVanguard Startup: Initializing database...")
    try:
        init_db()
    except Exception as e:
        import traceback
        print("!!!!!!!!!!!!!!!! CRITICAL DATABASE INITIALIZATION ERROR !!!!!!!!!!!!!!!!")
        traceback.print_exc()
        print(f"Database error details: {e}")
        print("Tip: If using Supabase with Render, ensure you use the Connection Pooler host (aws-0-*.pooler.supabase.com:5432) as direct host (db.*.supabase.co) requires IPv6 which Render does not support.")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        raise

    install_log_redaction_filter()
    init_error_monitoring(app)
    yield
    # Shutdown actions (if any)
    print("CodeVanguard Shutdown...")

app = FastAPI(
    title="CodeVanguard SAST Tool",
    description="Scan. Detect. Secure. In Seconds.",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS middleware
cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
cors_origin_regex = os.environ.get("ALLOWED_ORIGIN_REGEX", r"^https:\/\/code-vanguard(-.*)?\.vercel\.app$")

if os.environ.get("ENV", "development").lower() == "production":
    allowed_origin_env = os.environ.get("ALLOWED_ORIGINS")
    if allowed_origin_env:
        cors_origins = [origin.strip() for origin in allowed_origin_env.split(",")]
    else:
        print("SECURITY NOTE: Defaulting CORS to deployed app origins and Vercel preview domain pattern.")
        cors_origins = ["https://code-vanguard.vercel.app"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(scan.router)
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(repos.router)
app.include_router(webhook.router)
app.include_router(findings.router)
app.include_router(pulls.router)
app.include_router(badge.router)
app.include_router(autofix.router)
app.include_router(autofix.repo_autofix_router)
app.include_router(status.router)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Content Security Policy (CSP)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self';"
    )
    return response

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    """Fallback custom 404 page."""
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    templates.env.cache = None  # Workaround for Python 3.14 + Jinja2 cache key TypeError
    return templates.TemplateResponse(request=request, name="error_404.html", context={}, status_code=404)

@app.exception_handler(500)
async def custom_500_handler(request: Request, exc):
    """Unhandled internal server error handler with secret and source code scrubbing."""
    capture_exception(exc, extra={"path": request.url.path, "method": request.method})
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Error details have been scrubbed for privacy."}
    )

