import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

from app.utils.db import init_db
from app.routers import scan, admin

from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions: Initialize SQLite schema
    print("CodeVanguard Startup: Initializing database...")
    init_db()
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
cors_origins = ["*"]
if os.environ.get("ENV", "development").lower() == "production":
    allowed_origin_env = os.environ.get("ALLOWED_ORIGINS")
    if allowed_origin_env:
        cors_origins = [origin.strip() for origin in allowed_origin_env.split(",")]
    else:
        print("SECURITY WARNING: Running in production mode but ALLOWED_ORIGINS is not set! Defaulting to '*' wildcard origins.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(scan.router)
app.include_router(admin.router)

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
