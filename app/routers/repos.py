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
    get_db_connection, soft_delete_repository,
    upsert_installation, add_installation_member, upsert_repository
)
from app.utils.github import validate_branch_name, resolve_github_repo
from app.utils.github_app import get_installation_access_token
from app.utils.security import verify_origin_or_csrf
from app.utils.rate_limiter import scan_limiter, acquire_active_scan, release_active_scan, get_client_ip
from app.queue.redis_pool import enqueue_scan_job

router = APIRouter(prefix="/api/repos", tags=["repositories"])

class RepoScanPayload(BaseModel):
    branch: Optional[str] = None

class ConnectRepoPayload(BaseModel):
    url: str
    branch: Optional[str] = None

def parse_repo_identifier(raw_input: str) -> tuple[str, str]:
    """
    Parses and sanitizes user input for repository link or path.
    Supports:
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - github.com/owner/repo
    - owner/repo
    """
    if not raw_input or not isinstance(raw_input, str):
        raise ValueError("Repository URL or 'owner/repo' must be provided.")
    cleaned = raw_input.strip()
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]

    if "://" in cleaned:
        from urllib.parse import urlparse
        parsed = urlparse(cleaned)
        if parsed.netloc and parsed.netloc.lower() not in ("github.com", "www.github.com"):
            raise ValueError("Only GitHub repositories (https://github.com/owner/repo) are supported.")
        path = parsed.path.strip("/")
    elif cleaned.startswith("github.com/"):
        path = cleaned[len("github.com/"):].strip("/")
    else:
        path = cleaned.strip("/")

    parts = [p for p in path.split("/") if p]
    if len(parts) != 2:
        raise ValueError("Invalid repository format. Please enter 'owner/repo' or 'https://github.com/owner/repo'.")

    owner, repo_name = parts[0], parts[1]
    import re
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", owner) or not re.match(r"^[a-zA-Z0-9_\-\.]+$", repo_name):
        raise ValueError("Repository name contains forbidden characters.")
    if owner.startswith(".") or repo_name.startswith(".") or ".." in owner or ".." in repo_name:
        raise ValueError("Invalid repository identifier.")

    return owner, repo_name

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
    or direct repo connections the current authenticated user has access to.
    Automatically checks and syncs installations from GitHub if none are linked yet.
    """
    repos = get_user_repositories(user["id"], search=search)
    if not repos and sync:
        repos = sync_user_installations(user["id"])
        if search and search.strip():
            repos = [r for r in repos if search.strip().lower() in r.get("full_name", "").lower()]

    from app.utils.github_app import get_github_app_slug
    slug = get_github_app_slug()
    install_url = f"https://github.com/apps/{slug}/installations/new" if slug else None

    return {
        "repositories": repos,
        "app_slug": slug or None,
        "install_url": install_url
    }

@router.post("/connect")
async def connect_repository(
    request: Request,
    payload: ConnectRepoPayload,
    user: dict = Depends(require_authenticated_user)
):
    """
    Connects a repository by inserting its GitHub link (like in Vercel or Render).
    Validates accessibility on GitHub, resolves metadata & default branch,
    creates user installation association, and adds the repo to active repositories.
    """
    verify_origin_or_csrf(request)

    try:
        owner, repo_name = parse_repo_identifier(payload.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Resolve token for GitHub REST API
    auth_token = None
    if user.get("encrypted_user_token"):
        try:
            from app.utils.crypto import decrypt_token
            auth_token = decrypt_token(user["encrypted_user_token"])
        except Exception:
            auth_token = None

    if not auth_token:
        auth_token = os.environ.get("GITHUB_TOKEN")

    import urllib.request
    import urllib.error
    import json

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "CodeVanguard-SAST/1.0"
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token.strip()}"

    api_url = f"https://api.github.com/repos/{owner}/{repo_name}"
    req = urllib.request.Request(api_url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            repo_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as he:
        if he.code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"GitHub repository '{owner}/{repo_name}' not found or is private. If it is private, please authorize access with GitHub."
            )
        elif he.code in (403, 429):
            raise HTTPException(
                status_code=429,
                detail="GitHub API rate limit reached. Please try again shortly or configure GITHUB_TOKEN."
            )
        raise HTTPException(status_code=he.code, detail=f"GitHub API error ({he.code}): {he.reason}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to connect to GitHub API: {str(e)}")

    github_repo_id = repo_data.get("id")
    full_name = repo_data.get("full_name", f"{owner}/{repo_name}")
    api_default_branch = repo_data.get("default_branch", "main")
    is_private = bool(repo_data.get("private", False))

    target_branch = api_default_branch
    if payload.branch and payload.branch.strip():
        try:
            clean_branch = validate_branch_name(payload.branch)
            if clean_branch:
                target_branch = clean_branch
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    owner_obj = repo_data.get("owner", {})
    owner_login = owner_obj.get("login", owner)
    owner_type = owner_obj.get("type", "User")
    owner_avatar = owner_obj.get("avatar_url")
    owner_gh_id = owner_obj.get("id") or (990000000 + user["id"])

    local_inst = upsert_installation(
        github_installation_id=int(owner_gh_id),
        account_login=owner_login,
        account_type=owner_type,
        account_avatar_url=owner_avatar
    )
    add_installation_member(local_inst["id"], user["id"], role="admin")

    repo_record = upsert_repository(
        installation_id=local_inst["id"],
        github_repo_id=github_repo_id,
        full_name=full_name,
        default_branch=target_branch,
        is_private=is_private
    )

    full_repo = get_repository(repo_record["id"])

    return {
        "status": "success",
        "message": f"Successfully connected repository '{full_name}'.",
        "repository": full_repo
    }

@router.get("/github-list")
async def list_user_github_repositories(
    user: dict = Depends(require_authenticated_user)
):
    """
    Fetches repositories from the user's GitHub account via OAuth token,
    marking which ones are already connected to CodeVanguard.
    """
    token = None
    if user.get("encrypted_user_token"):
        try:
            from app.utils.crypto import decrypt_token
            token = decrypt_token(user["encrypted_user_token"])
        except Exception:
            token = None

    if not token:
        return {
            "repositories": [],
            "authenticated_with_github": False
        }

    import urllib.request
    import json
    import logging
    logger = logging.getLogger(__name__)

    gh_repos = []
    page = 1
    while page <= 3:
        req = urllib.request.Request(
            f"https://api.github.com/user/repos?per_page=100&page={page}&sort=updated",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "CodeVanguard-SAST/1.0"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not data or not isinstance(data, list):
                    break
                for r in data:
                    gh_repos.append({
                        "id": r["id"],
                        "name": r.get("name"),
                        "full_name": r.get("full_name"),
                        "private": bool(r.get("private")),
                        "html_url": r.get("html_url"),
                        "default_branch": r.get("default_branch", "main"),
                        "description": r.get("description"),
                        "updated_at": r.get("updated_at")
                    })
                if len(data) < 100:
                    break
                page += 1
        except Exception as e:
            logger.debug(f"Failed to fetch user repos from GitHub: {e}")
            break

    # Get already connected repos
    connected = get_user_repositories(user["id"])
    connected_map = {r["github_repo_id"]: r["id"] for r in connected}

    annotated = []
    for r in gh_repos:
        r_id = r["id"]
        annotated.append({
            **r,
            "connected": r_id in connected_map,
            "connected_repo_id": connected_map.get(r_id)
        })

    return {
        "repositories": annotated,
        "authenticated_with_github": True
    }

@router.post("/sync")
async def trigger_repo_sync(
    user: dict = Depends(require_authenticated_user)
):
    """Explicitly triggers a sync of GitHub App installations and repositories."""
    repos = sync_user_installations(user["id"])
    from app.utils.github_app import get_github_app_slug
    slug = get_github_app_slug()
    install_url = f"https://github.com/apps/{slug}/installations/new" if slug else None
    return {
        "status": "success",
        "repositories": repos,
        "app_slug": slug or None,
        "install_url": install_url
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

        # Obtain GitHub auth token: GitHub App -> User OAuth token -> env GITHUB_TOKEN -> None
        inst_token = None
        if installation and installation.get("github_installation_id"):
            try:
                inst_token, _ = get_installation_access_token(installation["github_installation_id"])
            except Exception:
                inst_token = None

        if not inst_token and user.get("encrypted_user_token"):
            try:
                from app.utils.crypto import decrypt_token
                inst_token = decrypt_token(user["encrypted_user_token"])
            except Exception:
                inst_token = None

        if not inst_token:
            inst_token = os.environ.get("GITHUB_TOKEN")

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
        source_type="github_app" if inst_token else "github_public",
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
        inst_token = None
        if installation and installation.get("github_installation_id"):
            try:
                inst_token, _ = get_installation_access_token(installation["github_installation_id"])
            except Exception:
                inst_token = None

        if not inst_token and user.get("encrypted_user_token"):
            try:
                from app.utils.crypto import decrypt_token
                inst_token = decrypt_token(user["encrypted_user_token"])
            except Exception:
                inst_token = None

        if not inst_token:
            inst_token = os.environ.get("GITHUB_TOKEN")

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
        source_type="github_app" if inst_token else "github_public",
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
