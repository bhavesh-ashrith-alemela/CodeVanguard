import logging
from typing import Optional
try:
    from fastapi import APIRouter, Request, HTTPException, Depends, Response
except ImportError:
    class APIRouter:
        def __init__(self, *args, **kwargs): pass
        def get(self, *args, **kwargs): return lambda f: f
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = None):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)
    class Response:
        def __init__(self, content="", status_code=200, media_type=None, headers=None):
            self.content = content
            self.status_code = status_code
            self.media_type = media_type
            self.headers = headers or {}
    Request = object
    Depends = lambda f=None: f

from app.utils.auth import get_authenticated_user_from_request, require_authenticated_user, require_repo_access
from app.utils.db import get_repository, get_repository_score_trend, get_db_connection, is_user_repo_member

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/repos/{repo_id}", tags=["trend_and_badges"])

def render_badge_svg(label: str, status: str, color: str) -> str:
    """Generates a clean, crisp SVG badge in neo-brutalist / shields style."""
    label_width = len(label) * 7 + 14
    status_width = len(status) * 7 + 14
    total_width = label_width + status_width

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" role="img" aria-label="{label}: {status}">
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#fff" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#14141A"/>
    <rect x="{label_width}" width="{status_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="'Space Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-weight="bold" font-size="11">
    <text x="{label_width / 2}" y="14" fill="#F5F4EE">{label}</text>
    <text x="{label_width + status_width / 2}" y="14" fill="#14141A">{status}</text>
  </g>
</svg>"""

@router.get("/trend")
async def get_security_trend(
    repo_id: str,
    request: Request,
    user: dict = Depends(require_authenticated_user)
):
    """Returns security score trend across default branch commits."""
    repo = require_repo_access(user, repo_id)
    trend = get_repository_score_trend(repo["id"], limit=20)
    return {"trend": trend}

@router.get("/badge.svg")
async def get_security_badge(
    repo_id: str,
    request: Request
):
    """
    Returns an SVG status badge for the repository.
    Public for open-source repositories; requires valid session for private repositories.
    """
    repo = get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found.")

    if repo.get("is_private"):
        user = get_authenticated_user_from_request(request)
        if not user:
            raise HTTPException(status_code=404, detail="Repository not found.")
        
        is_admin = user.get("role") == "admin"
        if not is_admin and not is_user_repo_member(repo["id"], user["id"]):
            raise HTTPException(status_code=404, detail="Repository not found.")

    trend = get_repository_score_trend(repo["id"], limit=1)
    if not trend:
        badge_svg = render_badge_svg("codevanguard", "unknown", "#E2E0D6")
    else:
        latest = trend[-1]
        score = latest["score"]
        crit = latest["critical"]
        high = latest["high"]

        if crit > 0 or high > 0:
            status_text = f"failing ({score})"
            color = "#FF6B3D"  # Orange-red
        elif score >= 90:
            status_text = f"passing ({score})"
            color = "#D6F25B"  # Lime
        else:
            status_text = f"warning ({score})"
            color = "#FFC93C"  # Yellow

        badge_svg = render_badge_svg("codevanguard", status_text, color)

    return Response(
        content=badge_svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Content-Type": "image/svg+xml"
        }
    )
