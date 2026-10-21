import os
import re
from urllib.parse import urlparse
from typing import Optional

try:
    from fastapi import Request, HTTPException
except ImportError:
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = None):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)
    Request = object

DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://code-vanguard.vercel.app"
]
DEFAULT_ORIGIN_REGEX = r"^https:\/\/code-vanguard(-.*)?\.vercel\.app$"

def is_allowed_origin(origin_url: str, host: Optional[str] = None) -> bool:
    """
    Checks if a given origin or referer URL is permitted:
    1. Same-origin match against the Host header
    2. Explicitly allowed origin list (configured via ALLOWED_ORIGINS)
    3. Allowed regex pattern (configured via ALLOWED_ORIGIN_REGEX)
    """
    if not origin_url or not isinstance(origin_url, str):
        return False

    parsed = urlparse(origin_url.strip())
    if not parsed.scheme or not parsed.netloc:
        return False

    # 1. Same-origin match
    if host and parsed.netloc.lower() == host.lower():
        return True

    origin_base = f"{parsed.scheme}://{parsed.netloc}".lower()

    # 2. Allowed origins list
    allowed = set(o.lower() for o in DEFAULT_ALLOWED_ORIGINS)
    env_origins = os.environ.get("ALLOWED_ORIGINS")
    if env_origins:
        for o in env_origins.split(","):
            if o.strip():
                allowed.add(o.strip().lower())

    if origin_base in allowed or origin_url.strip().rstrip("/").lower() in allowed:
        return True

    # 3. Regex pattern match
    regex_pattern = os.environ.get("ALLOWED_ORIGIN_REGEX", DEFAULT_ORIGIN_REGEX)
    if regex_pattern and re.match(regex_pattern, origin_base, re.IGNORECASE):
        return True

    return False

def verify_origin_or_csrf(request: Request):
    """
    Validates Origin and Referer headers on incoming state-changing requests.
    - If Origin or Referer is present, it must be same-origin or from an allowed CORS origin.
    - If neither is present on a Form/Multipart submission, reject with 403 (CSRF defense).
    - Programmatic JSON API clients without browser origin headers are allowed.
    """
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    host = request.headers.get("host")

    check_url = origin or referer

    if check_url:
        if not is_allowed_origin(check_url, host):
            raise HTTPException(
                status_code=403,
                detail=f"Cross-origin request blocked: untrusted origin '{check_url}'."
            )
        return

    # Neither Origin nor Referer provided
    content_type = request.headers.get("content-type", "").lower()
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        raise HTTPException(
            status_code=403,
            detail="CSRF check failed: Missing Origin or Referer header on form submission."
        )

def verify_csrf(request: Request):
    """Legacy CSRF verification wrapper delegating to verify_origin_or_csrf."""
    verify_origin_or_csrf(request)
