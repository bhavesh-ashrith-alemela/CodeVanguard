import os
import json
import secrets
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional

try:
    from fastapi import APIRouter, Request, Response, HTTPException, Depends
    from fastapi.responses import RedirectResponse
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
    class Response:
        def __init__(self, content="", status_code=200, media_type=None, headers=None):
            self.content = content
            self.status_code = status_code
            self.media_type = media_type
            self.headers = headers or {}
        def set_cookie(self, *args, **kwargs): pass
        def delete_cookie(self, *args, **kwargs): pass
    class RedirectResponse(Response):
        def __init__(self, url="", status_code=303, headers=None):
            super().__init__(content="", status_code=status_code, headers=headers)
            self.url = url
    Request = object
    Depends = lambda f=None: f

from app.utils.db import (
    upsert_github_user, get_user_by_session, create_session, delete_session,
    upsert_installation, add_installation_member, upsert_repository,
    get_installation_by_github_id, delete_user_data
)
from app.utils.crypto import encrypt_token, decrypt_token
from app.utils.github_app import generate_app_jwt, get_installation_access_token
from app.utils.rate_limiter import get_redis_client

router = APIRouter()

def get_client_redirect_base(request: Request) -> str:
    """Returns the frontend base URL for OAuth redirects (Vercel domain or request origin)."""
    return os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")

@router.get("/api/auth/github/login")
async def github_oauth_login(request: Request, return_to: Optional[str] = "/dashboard"):
    """
    Initiates GitHub App user-authorization OAuth flow.
    Generates a secure state parameter stored in Redis/cookie to prevent CSRF.
    """
    client_id = os.environ.get("GITHUB_APP_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="GITHUB_APP_CLIENT_ID not configured.")

    state = secrets.token_hex(24)

    # Store state in Redis with 10-minute TTL
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.setex(f"github:oauth_state:{state}", 600, return_to or "/dashboard")
        except Exception:
            pass

    frontend_base = get_client_redirect_base(request)
    redirect_uri = f"{frontend_base}/api/auth/github/callback"

    params = {
        "client_id": client_id,
        "state": state,
        "redirect_uri": redirect_uri,
        "scope": "read:user"
    }

    github_auth_url = f"https://github.com/login/oauth/authorize?{urllib.parse.urlencode(params)}"
    response = RedirectResponse(url=github_auth_url, status_code=303)
    # Also set as fallback cookie in case Redis is not active
    response.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=600)
    response.set_cookie("oauth_return", return_to or "/dashboard", httponly=True, samesite="lax", max_age=600)
    return response

@router.get("/api/auth/github/callback")
async def github_oauth_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None
):
    """
    Exchanges OAuth code for access token, validates state, resolves user profile,
    encrypts user token with Fernet, creates a session, and sets first-party HttpOnly cookies.
    """
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter.")

    # 1. State Validation
    valid_state = False
    return_to = "/dashboard"

    redis_client = get_redis_client()
    if redis_client:
        try:
            val = redis_client.get(f"github:oauth_state:{state}")
            if val:
                valid_state = True
                return_to = val.decode("utf-8") if isinstance(val, bytes) else str(val)
                redis_client.delete(f"github:oauth_state:{state}")
        except Exception:
            pass

    if not valid_state:
        cookie_state = request.cookies.get("oauth_state")
        if cookie_state and hmac_compare_safe(cookie_state, state):
            valid_state = True
            return_to = request.cookies.get("oauth_return", "/dashboard")

    if not valid_state:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state parameter.")

    # 2. Exchange code for access token
    client_id = os.environ.get("GITHUB_APP_CLIENT_ID")
    client_secret = os.environ.get("GITHUB_APP_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="GitHub App credentials not configured.")

    token_url = "https://github.com/login/oauth/access_token"
    token_payload = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code
    }).encode("utf-8")

    req_token = urllib.request.Request(
        token_url,
        data=token_payload,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "CodeVanguard-SAST/1.0"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req_token, timeout=15) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to exchange OAuth code: {e}")

    access_token = token_data.get("access_token")
    if not access_token:
        err = token_data.get("error_description", token_data.get("error", "Unknown token error"))
        raise HTTPException(status_code=400, detail=f"GitHub OAuth error: {err}")

    # 3. Retrieve User Profile from GitHub
    req_user = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "CodeVanguard-SAST/1.0"
        }
    )

    try:
        with urllib.request.urlopen(req_user, timeout=15) as resp:
            gh_user = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch GitHub user profile: {e}")

    github_id = gh_user.get("id")
    github_login = gh_user.get("login")
    avatar_url = gh_user.get("avatar_url")

    if not github_id or not github_login:
        raise HTTPException(status_code=502, detail="Incomplete GitHub user profile returned.")

    # 4. Encrypt user token and upsert user in database
    encrypted_token = encrypt_token(access_token)
    user = upsert_github_user(
        github_id=github_id,
        github_login=github_login,
        avatar_url=avatar_url,
        encrypted_user_token=encrypted_token
    )

    # 5. Create local session
    session_token = create_session(user["id"])

    # 6. Redirect to frontend with first-party HttpOnly session cookies
    frontend_base = get_client_redirect_base(request)
    target_url = f"{frontend_base}{return_to}" if return_to.startswith("/") else return_to

    response = RedirectResponse(url=target_url, status_code=303)
    is_prod = os.environ.get("ENV", "development").lower() == "production"

    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=is_prod,
        max_age=86400 * 7 # 7 days
    )
    response.set_cookie(
        key="cv_user",
        value=github_login,
        httponly=False,
        samesite="lax",
        secure=is_prod,
        max_age=86400 * 7
    )
    # Clean up state cookies
    response.delete_cookie("oauth_state")
    response.delete_cookie("oauth_return")
    return response

def hmac_compare_safe(val1: str, val2: str) -> bool:
    import hmac
    return hmac.compare_digest(val1.encode("utf-8"), val2.encode("utf-8"))

@router.get("/api/auth/me")
async def get_current_user_profile(request: Request):
    """Returns the authenticated user profile."""
    token = request.cookies.get("session_token")
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")

    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session invalid or expired.")

    return {
        "id": user["id"],
        "username": user["username"],
        "github_id": user.get("github_id"),
        "github_login": user.get("github_login"),
        "avatar_url": user.get("avatar_url"),
        "role": user["role"]
    }

@router.post("/api/auth/logout")
async def logout(request: Request):
    """Purges the active session and clears cookies."""
    token = request.cookies.get("session_token")
    if token:
        delete_session(token)
    response = Response(content=json.dumps({"status": "success", "message": "Logged out."}), media_type="application/json")
    response.delete_cookie("session_token")
    response.delete_cookie("cv_user")
    return response

@router.get("/api/github/setup")
@router.get("/github/setup")
async def github_app_setup_callback(
    request: Request,
    installation_id: Optional[int] = None,
    setup_action: Optional[str] = None
):
    """
    Handles redirect from GitHub App Setup URL.
    Anti-Hijacking Protection:
    1. Verifies the user is authenticated.
    2. Calls GET /user/installations using the user's decrypted OAuth token to verify
       that the installation_id truly belongs to them.
    3. Fetches installation details with App JWT and syncs repositories.
    """
    token = request.cookies.get("session_token")
    if not token:
        # Prompt login preserving return_to setup URL
        setup_url = f"/github/setup?installation_id={installation_id}&setup_action={setup_action}"
        frontend_base = get_client_redirect_base(request)
        return RedirectResponse(url=f"{frontend_base}/login?return_to={urllib.parse.quote(setup_url)}", status_code=303)

    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    if not installation_id:
        return RedirectResponse(url=f"{get_client_redirect_base(request)}/dashboard", status_code=303)

    # 1. Decrypt user OAuth token for verification
    encrypted_token = user.get("encrypted_user_token")
    user_token = decrypt_token(encrypted_token) if encrypted_token else None

    # 2. Verify installation access via GET /user/installations
    if user_token:
        verified = False
        page = 1
        while page <= 5: # Paginate up to 500 installations
            req = urllib.request.Request(
                f"https://api.github.com/user/installations?per_page=100&page={page}",
                headers={
                    "Authorization": f"Bearer {user_token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "CodeVanguard-SAST/1.0"
                }
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    inst_list = data.get("installations", [])
                    if any(inst.get("id") == int(installation_id) for inst in inst_list):
                        verified = True
                        break
                    if len(inst_list) < 100:
                        break
                    page += 1
            except Exception as e:
                # If API fails or user uninstalled, log and reject
                break

        if not verified:
            raise HTTPException(
                status_code=403,
                detail="Installation verification failed: you do not have permission to access or link this GitHub App installation."
            )

    # 3. Retrieve Installation Details from GitHub App API
    app_jwt = generate_app_jwt()
    req_inst = urllib.request.Request(
        f"https://api.github.com/app/installations/{installation_id}",
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "CodeVanguard-SAST/1.0"
        }
    )

    try:
        with urllib.request.urlopen(req_inst, timeout=15) as resp:
            inst_data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch installation details from GitHub: {e}")

    account = inst_data.get("account", {})
    account_login = account.get("login", "unknown")
    account_type = account.get("type", "User")
    account_avatar = account.get("avatar_url")

    # 4. Upsert Installation and Add User Membership
    inst = upsert_installation(
        github_installation_id=int(installation_id),
        account_login=account_login,
        account_type=account_type,
        account_avatar_url=account_avatar
    )
    add_installation_member(inst["id"], user["id"], role="admin")

    # 5. Sync Repositories
    try:
        inst_token, _ = get_installation_access_token(int(installation_id))
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
            with urllib.request.urlopen(req_repos, timeout=15) as resp:
                repo_data = json.loads(resp.read().decode("utf-8"))
                repos = repo_data.get("repositories", [])
                for r in repos:
                    upsert_repository(
                        inst["id"],
                        r["id"],
                        r.get("full_name"),
                        r.get("default_branch", "main"),
                        r.get("private", False)
                    )
                if len(repos) < 100:
                    break
                repo_page += 1
    except Exception as e:
        # Repositories can also be synced later via webhook
        pass

    frontend_base = get_client_redirect_base(request)
    return RedirectResponse(url=f"{frontend_base}/dashboard?installed=1", status_code=303)

@router.post("/api/user/delete-data")
async def delete_my_data(request: Request):
    """
    Self-service data deletion: purges user's personal scans, memberships,
    and removes stored OAuth access tokens.
    """
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired.")

    result = delete_user_data(user["id"])
    response = Response(content=json.dumps(result), media_type="application/json")
    response.delete_cookie("session_token")
    response.delete_cookie("cv_user")
    return response
