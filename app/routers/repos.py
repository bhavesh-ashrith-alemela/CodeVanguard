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

def sync_user_installations(user_id: int) -> list:
    """
    Discovers and syncs installations and repositories from GitHub for a user.
    1. Tries user-level discovery via GET /user/installations using the user's decrypted OAuth token.
    2. Tries app-level discovery via GET /app/installations using the App JWT matching user's github_login.
    3. For matched installations, upserts the installation, links the user as admin member, and syncs repositories.
    4. Returns the updated list of repositories for the user.
    """
    from app.utils.crypto import decrypt_token
    from app.utils.github_app import get_installation_access_token, generate_app_jwt
    from app.utils.db import (
        get_user_by_id, upsert_installation, add_installation_member,
        upsert_repository, get_user_repositories
    )
    import urllib.request
    import json
    import logging

    logger = logging.getLogger(__name__)

    user = get_user_by_id(user_id)
    if not user:
        return []

    matched_installations = {}

    # 1. Method A: User token /user/installations
    encrypted_token = user.get("encrypted_user_token")
    if encrypted_token:
        try:
            user_token = decrypt_token(encrypted_token)
            if user_token:
                page = 1
                while page <= 5:
                    req = urllib.request.Request(
                        f"https://api.github.com/user/installations?per_page=100&page={page}",
                        headers={
                            "Authorization": f"Bearer {user_token}",
                            "Accept": "application/vnd.github+json",
                            "User-Agent": "CodeVanguard-SAST/1.0"
                        }
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        inst_list = data.get("installations", [])
                        for inst in inst_list:
                            if inst.get("id"):
                                matched_installations[inst["id"]] = inst
                        if len(inst_list) < 100:
                            break
                        page += 1
        except Exception as e:
            logger.debug(f"User installations discovery via user token failed: {e}")

    # 2. Method B: App-level discovery via /app/installations matching github_login / github_id
    github_login = (user.get("github_login") or "").lower()
    github_id = user.get("github_id")
    if github_login or github_id:
        try:
            app_jwt = generate_app_jwt()
            page = 1
            while page <= 5:
                req = urllib.request.Request(
                    f"https://api.github.com/app/installations?per_page=100&page={page}",
                    headers={
                        "Authorization": f"Bearer {app_jwt}",
                        "Accept": "application/vnd.github+json",
                        "User-Agent": "CodeVanguard-SAST/1.0"
                    }
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    app_insts = json.loads(resp.read().decode("utf-8"))
                    for inst in app_insts:
                        acct = inst.get("account", {})
                        acct_login = (acct.get("login") or "").lower()
                        acct_id = acct.get("id")
                        if (github_login and acct_login == github_login) or (github_id and acct_id == github_id):
                            matched_installations[inst["id"]] = inst
                    if len(app_insts) < 100:
                        break
                    page += 1
        except Exception as e:
            logger.debug(f"App installations discovery failed: {e}")

    # 3. For all matched installations, upsert installation, add membership, and sync repositories
    for github_inst_id, inst_data in matched_installations.items():
        try:
            account = inst_data.get("account", {})
            account_login = account.get("login", "unknown")
            account_type = account.get("type", "User")
            account_avatar = account.get("avatar_url")

            local_inst = upsert_installation(
                github_installation_id=int(github_inst_id),
                account_login=account_login,
                account_type=account_type,
                account_avatar_url=account_avatar
            )
            add_installation_member(local_inst["id"], user_id, role="admin")

            # Sync repositories
            try:
                inst_token, _ = get_installation_access_token(int(github_inst_id))
                repo_page = 1
                while repo_page <= 5:
                    req_repos = urllib.request.Request(
                        f"https://api.github.com/installation/repositories?per_page=100&page={repo_page}",
                        headers={
                            "Authorization": f"Bearer {inst_token}",
                            "Accept": "application/vnd.github+json",
                            "User-Agent": "CodeVanguard-SAST/1.0"
                        }
                    )
                    with urllib.request.urlopen(req_repos, timeout=10) as resp:
                        repo_payload = json.loads(resp.read().decode("utf-8"))
                        repos = repo_payload.get("repositories", [])
                        for r in repos:
                            upsert_repository(
                                local_inst["id"],
                                r["id"],
                                r.get("full_name"),
                                r.get("default_branch", "main"),
                                r.get("private", False)
                            )
                        if len(repos) < 100:
                            break
                        repo_page += 1
            except Exception as e:
                logger.warning(f"Failed to sync repositories for installation {github_inst_id}: {e}")

        except Exception as e:
            logger.warning(f"Error processing installation {github_inst_id}: {e}")

    return get_user_repositories(user_id)

@router.get("")
async def list_repositories(
    search: Optional[str] = None,
    sync: Optional[bool] = False,
    user: dict = Depends(require_authenticated_user)
):
    """
    Lists all active repositories belonging to GitHub App installations
    the current authenticated user has access to.
    Automatically checks and syncs installations from GitHub if none are linked yet.
    """
    repos = get_user_repositories(user["id"], search=search)
    if not repos or sync:
        repos = sync_user_installations(user["id"])
        if search and search.strip():
            repos = [r for r in repos if search.strip().lower() in r.get("full_name", "").lower()]

    from app.utils.github_app import get_github_app_slug
    slug = get_github_app_slug()
    install_url = f"https://github.com/apps/{slug}/installations/new"

    return {
        "repositories": repos,
        "app_slug": slug,
        "install_url": install_url
    }

@router.post("/sync")
async def trigger_repo_sync(
    user: dict = Depends(require_authenticated_user)
):
    """Explicitly triggers a sync of GitHub App installations and repositories."""
    repos = sync_user_installations(user["id"])
    from app.utils.github_app import get_github_app_slug
    slug = get_github_app_slug()
    return {
        "status": "success",
        "repositories": repos,
        "app_slug": slug,
        "install_url": f"https://github.com/apps/{slug}/installations/new"
    }


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
