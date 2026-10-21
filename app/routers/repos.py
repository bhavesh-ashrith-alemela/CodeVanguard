import uuid
from typing import Optional
try:
    from pydantic import BaseModel
except ImportError:
    from app.models.scan_result import BaseModel

try:
    from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks, Body
except ImportError:
    class APIRouter:
        def __init__(self, *args, **kwargs): pass
        def get(self, *args, **kwargs): return lambda f: f
        def post(self, *args, **kwargs): return lambda f: f
        def patch(self, *args, **kwargs): return lambda f: f
        def delete(self, *args, **kwargs): return lambda f: f
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = None):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)
    Request = object
    Depends = lambda f=None: f
    BackgroundTasks = object
    Body = lambda default=None, **kwargs: default

from app.utils.auth import require_authenticated_user, require_repo_access
from app.utils.db import (
    get_user_repositories, get_repository, get_scan_history,
    get_installation, create_scan, update_repo_last_scanned,
    get_db_connection, soft_delete_repository
)
from app.utils.github import validate_branch_name, resolve_github_repo
from app.utils.github_app import get_installation_access_token
from app.utils.security import verify_origin_or_csrf
from app.utils.rate_limiter import scan_limiter, acquire_active_scan, release_active_scan, get_client_ip
from app.queue.redis_pool import enqueue_scan_job

router = APIRouter(prefix="/api/repos", tags=["repositories"])

class RepoScanPayload(BaseModel):
    branch: Optional[str] = None

@router.get("")
async def list_repositories(
    search: Optional[str] = None,
    user: dict = Depends(require_authenticated_user)
):
    """
    Lists all active repositories belonging to GitHub App installations
    the current authenticated user has access to.
    """
    repos = get_user_repositories(user["id"], search=search)
    return {"repositories": repos}

@router.get("/{repo_id}")
async def get_repository_details(
    repo_id: str,
    request: Request,
    user: dict = Depends(require_authenticated_user)
):
    """
    Retrieves repository metadata, installation state, and recent scan history.
    Enforces installation membership authorization.
    """
    repo = require_repo_access(user, repo_id)
    installation = get_installation(repo["installation_id"])
    scans = get_scan_history(repo_id=repo_id, limit=20)
    
    return {
        "repository": repo,
        "installation": installation,
        "scans": scans
    }

class RepoSettingsUpdatePayload(BaseModel):
    scan_enabled: Optional[bool] = None
    scan_on_pr: Optional[bool] = None
    scan_on_push: Optional[bool] = None
    fail_on: Optional[str] = None
    ignore_globs: Optional[str] = None
    pr_comment_enabled: Optional[bool] = None
    sarif_upload_enabled: Optional[bool] = None
    scan_drafts: Optional[bool] = None
    narrative_enabled: Optional[bool] = None
    autofix_enabled: Optional[bool] = None
    autofix_daily_quota: Optional[int] = None

@router.patch("/{repo_id}")
async def update_repository_settings(
    repo_id: str,
    request: Request,
    payload: Optional[RepoSettingsUpdatePayload] = Body(None),
    user: dict = Depends(require_authenticated_user)
):
    """Updates repository scanning settings with origin/CSRF verification."""
    verify_origin_or_csrf(request)
    repo = require_repo_access(user, repo_id)
    if payload:
        updates = []
        params = []
        if payload.scan_enabled is not None:
            updates.append("scan_enabled = ?")
            params.append(1 if payload.scan_enabled else 0)
            repo["scan_enabled"] = bool(payload.scan_enabled)
        if payload.scan_on_pr is not None:
            updates.append("scan_on_pr = ?")
            params.append(1 if payload.scan_on_pr else 0)
            repo["scan_on_pr"] = bool(payload.scan_on_pr)
        if payload.scan_on_push is not None:
            updates.append("scan_on_push = ?")
            params.append(1 if payload.scan_on_push else 0)
            repo["scan_on_push"] = bool(payload.scan_on_push)
        if payload.fail_on is not None:
            fo = payload.fail_on.lower()
            if fo in ("critical", "high", "medium", "none"):
                updates.append("fail_on = ?")
                params.append(fo)
                repo["fail_on"] = fo
        if payload.ignore_globs is not None:
            clean_globs = str(payload.ignore_globs)[:10000]
            updates.append("ignore_globs = ?")
            params.append(clean_globs)
            repo["ignore_globs"] = clean_globs
        if payload.pr_comment_enabled is not None:
            updates.append("pr_comment_enabled = ?")
            params.append(1 if payload.pr_comment_enabled else 0)
            repo["pr_comment_enabled"] = bool(payload.pr_comment_enabled)
        if payload.sarif_upload_enabled is not None:
            updates.append("sarif_upload_enabled = ?")
            params.append(1 if payload.sarif_upload_enabled else 0)
            repo["sarif_upload_enabled"] = bool(payload.sarif_upload_enabled)
        if payload.scan_drafts is not None:
            updates.append("scan_drafts = ?")
            params.append(1 if payload.scan_drafts else 0)
            repo["scan_drafts"] = bool(payload.scan_drafts)
        if payload.narrative_enabled is not None:
            updates.append("narrative_enabled = ?")
            params.append(1 if payload.narrative_enabled else 0)
            repo["narrative_enabled"] = bool(payload.narrative_enabled)
        if payload.autofix_enabled is not None:
            updates.append("autofix_enabled = ?")
            params.append(1 if payload.autofix_enabled else 0)
            repo["autofix_enabled"] = bool(payload.autofix_enabled)
        if payload.autofix_daily_quota is not None:
            quota = max(1, min(100, int(payload.autofix_daily_quota)))
            updates.append("autofix_daily_quota = ?")
            params.append(quota)
            repo["autofix_daily_quota"] = quota

        if updates:
            params.append(repo["id"])
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"UPDATE repositories SET {', '.join(updates)} WHERE id = ?", tuple(params))
                conn.commit()

    return {"status": "success", "repository": repo}

@router.delete("/{repo_id}")
async def disconnect_repository(
    repo_id: str,
    request: Request,
    user: dict = Depends(require_authenticated_user)
):
    """Disconnects a repository from active scanning."""
    verify_origin_or_csrf(request)
    repo = require_repo_access(user, repo_id)
    soft_delete_repository(repo["github_repo_id"])
    return {"status": "success", "message": f"Repository '{repo['full_name']}' disconnected."}


@router.post("/{repo_id}/scan")
async def trigger_repo_scan(
    repo_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Optional[RepoScanPayload] = Body(None),
    user: dict = Depends(require_authenticated_user)
):
    """
    Triggers an on-demand scan of a repository default or specified branch.
    Fetches repo metadata using the GitHub App installation token.
    Enforces authorization, CSRF protection, and concurrency locks.
    """
    verify_origin_or_csrf(request)
    repo = require_repo_access(user, repo_id)

    # Verify installation active status
    installation = get_installation(repo["installation_id"])
    if not installation:
        raise HTTPException(status_code=404, detail="Parent GitHub App installation not found.")
    if installation.get("suspended_at"):
        raise HTTPException(status_code=403, detail="Installation is currently suspended on GitHub.")

    ip = get_client_ip(request)
    if not scan_limiter.is_allowed(ip):
        raise HTTPException(status_code=429, detail="Too many scans submitted. Please wait a minute.")

    scan_id = uuid.uuid4().hex

    # Acquire concurrency lock
    allowed, reason = acquire_active_scan(ip, scan_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    try:
        # Resolve target branch
        requested_branch = payload.branch if payload else None
        clean_branch = validate_branch_name(requested_branch) if requested_branch else repo.get("default_branch", "main")

        # Obtain GitHub App Installation Access Token
        inst_token, _ = get_installation_access_token(installation["github_installation_id"])

        parts = repo["full_name"].split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid repository full name '{repo['full_name']}'.")
        owner, repo_name = parts[0], parts[1]

        # Resolve commit SHA and verify repo size limits
        repo_info = resolve_github_repo(owner, repo_name, clean_branch, auth_token=inst_token)

    except ValueError as e:
        release_active_scan(ip, scan_id)
        err_msg = str(e)
        if "not found" in err_msg.lower():
            raise HTTPException(status_code=404, detail=err_msg)
        elif "rate limit" in err_msg.lower():
            raise HTTPException(status_code=429, detail=err_msg)
        else:
            raise HTTPException(status_code=400, detail=err_msg)
    except HTTPException:
        release_active_scan(ip, scan_id)
        raise
    except Exception as e:
        release_active_scan(ip, scan_id)
        raise HTTPException(status_code=500, detail=f"Failed to resolve repository metadata: {str(e)}")

    filename = f"{repo['full_name']}@{repo_info.resolved_branch}"
    file_size = repo_info.size_kb * 1024

    create_scan(
        scan_id=scan_id,
        filename=filename,
        file_size=file_size,
        source_type="github_app",
        source_url=f"https://github.com/{repo['full_name']}",
        branch=repo_info.resolved_branch,
        commit_sha=repo_info.commit_sha,
        repo_id=repo["id"],
        owner_user_id=user["id"],
        trigger="manual"
    )

    update_repo_last_scanned(repo["id"])
    await enqueue_scan_job(scan_id, client_ip=ip, background_tasks=background_tasks)

    return {
        "status": "queued",
        "scan_id": scan_id,
        "repo_id": repo["id"],
        "branch": repo_info.resolved_branch,
        "commit_sha": repo_info.commit_sha
    }

@router.post("/{repo_id}/scan/history")
async def trigger_repo_history_scan(
    repo_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_authenticated_user)
):
    """
    Triggers an on-demand full git history secret scan.
    Clones bare with depth and date limits, streams git log -p,
    and flags both active and deleted credentials.
    """
    verify_origin_or_csrf(request)
    repo = require_repo_access(user, repo_id)

    installation = get_installation(repo["installation_id"])
    if not installation:
        raise HTTPException(status_code=404, detail="Parent GitHub App installation not found.")
    if installation.get("suspended_at"):
        raise HTTPException(status_code=403, detail="Installation is currently suspended on GitHub.")

    ip = get_client_ip(request)
    if not scan_limiter.is_allowed(ip):
        raise HTTPException(status_code=429, detail="Too many scans submitted. Please wait a minute.")

    scan_id = uuid.uuid4().hex

    allowed, reason = acquire_active_scan(ip, scan_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    try:
        inst_token, _ = get_installation_access_token(installation["github_installation_id"])
        parts = repo["full_name"].split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid repository full name '{repo['full_name']}'.")
        owner, repo_name = parts[0], parts[1]
        default_branch = repo.get("default_branch", "main")
        repo_info = resolve_github_repo(owner, repo_name, default_branch, auth_token=inst_token)
    except Exception as e:
        release_active_scan(ip, scan_id)
        raise HTTPException(status_code=400, detail=f"Failed to initialize history scan: {str(e)}")

    create_scan(
        scan_id=scan_id,
        filename=f"{repo['full_name']}@history",
        file_size=0,
        source_type="github_app",
        source_url=f"https://github.com/{repo['full_name']}",
        branch=repo_info.resolved_branch,
        commit_sha=repo_info.commit_sha,
        repo_id=repo["id"],
        owner_user_id=user["id"],
        trigger="history"
    )

    update_repo_last_scanned(repo["id"])
    await enqueue_scan_job(scan_id, client_ip=ip, background_tasks=background_tasks)

    return {
        "status": "queued",
        "scan_id": scan_id,
        "repo_id": repo["id"],
        "trigger": "history"
    }
