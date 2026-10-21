from typing import Optional
try:
    from pydantic import BaseModel
except ImportError:
    from app.models.scan_result import BaseModel

try:
    from fastapi import APIRouter, Request, HTTPException, Depends, Query, Body
except ImportError:
    class APIRouter:
        def __init__(self, *args, **kwargs): pass
        def get(self, *args, **kwargs): return lambda f: f
        def post(self, *args, **kwargs): return lambda f: f
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = None):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)
    Request = object
    Depends = lambda f=None: f
    Query = lambda default=None, **kwargs: default
    Body = lambda default=None, **kwargs: default

from app.utils.auth import require_authenticated_user, require_repo_access
from app.utils.security import verify_origin_or_csrf
from app.utils.db import (
    get_repository_findings, get_finding_by_id,
    suppress_finding, unsuppress_finding
)

router = APIRouter(prefix="/api/repos/{repo_id}/findings", tags=["findings"])

class SuppressPayload(BaseModel):
    state: Optional[str] = "suppressed" # 'suppressed' or 'false_positive'
    reason: Optional[str] = None

@router.get("")
async def list_repo_findings(
    repo_id: str,
    request: Request,
    severity: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    scanner: Optional[str] = Query(None),
    is_secret: Optional[bool] = Query(None),
    introduced_by_pr: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: dict = Depends(require_authenticated_user)
):
    """Retrieves paginated findings for a repository with filtering and tenancy authorization."""
    repo = require_repo_access(user, repo_id)
    findings, total_count = get_repository_findings(
        repo_id=repo["id"],
        severity=severity,
        state=state,
        scanner=scanner,
        is_secret=is_secret,
        introduced_by_pr=introduced_by_pr,
        search=search,
        page=page,
        per_page=per_page
    )
    return {
        "findings": findings,
        "total_count": total_count,
        "page": page,
        "per_page": per_page
    }

@router.get("/{finding_id}")
async def get_finding_details(
    repo_id: str,
    finding_id: str,
    request: Request,
    user: dict = Depends(require_authenticated_user)
):
    """Retrieves details, vulnerable snippet, and remediation blueprint for a single finding."""
    repo = require_repo_access(user, repo_id)
    finding = get_finding_by_id(repo["id"], finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found in repository registry.")
    return {"finding": finding}

@router.post("/{finding_id}/suppress")
async def suppress_repo_finding(
    repo_id: str,
    finding_id: str,
    request: Request,
    payload: Optional[SuppressPayload] = Body(None),
    user: dict = Depends(require_authenticated_user)
):
    """
    Suppresses a finding or marks it as a false positive.
    Requires a non-empty audit justification reason.
    """
    verify_origin_or_csrf(request)
    repo = require_repo_access(user, repo_id)

    finding = get_finding_by_id(repo["id"], finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found in repository registry.")

    reason = payload.reason.strip() if payload and payload.reason else ""
    if not reason or len(reason) < 3:
        raise HTTPException(status_code=400, detail="A justification reason of at least 3 characters is required to suppress a finding.")

    target_state = payload.state.lower() if payload and payload.state else "suppressed"
    if target_state not in ("suppressed", "false_positive"):
        target_state = "suppressed"

    result = suppress_finding(repo["id"], finding_id, user["id"], state=target_state, reason=reason)
    return result

@router.post("/{finding_id}/unsuppress")
async def unsuppress_repo_finding(
    repo_id: str,
    finding_id: str,
    request: Request,
    user: dict = Depends(require_authenticated_user)
):
    """Restores a suppressed finding back to active/open state."""
    verify_origin_or_csrf(request)
    repo = require_repo_access(user, repo_id)

    finding = get_finding_by_id(repo["id"], finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found in repository registry.")

    result = unsuppress_finding(repo["id"], finding_id, user["id"])
    return result
