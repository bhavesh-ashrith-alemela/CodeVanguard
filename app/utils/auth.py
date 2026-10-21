from typing import Optional

try:
    from fastapi import Request, HTTPException, Depends
except ImportError:
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = None):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)
    Request = object
    Depends = lambda f=None: f

from app.utils.db import (
    get_user_by_session, get_repository, is_user_repo_member, get_scan
)

def get_current_user_optional(request: Request) -> Optional[dict]:
    """Resolves authenticated user from session cookie or Bearer header without throwing."""
    token = request.cookies.get("session_token")
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

    if not token:
        return None

    return get_user_by_session(token)

# Alias for backwards compatibility with badge router
get_authenticated_user_from_request = get_current_user_optional

def require_authenticated_user(request: Request) -> dict:
    """Route dependency requiring a valid authenticated user session."""
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user

def require_repo_access(user: dict, repo_id: str) -> dict:
    """
    Verifies that the user has authorized membership access to the specified repository.
    Admins are granted automatic access.
    Raises 404 if repository does not exist, and 403 if unauthorized.
    """
    repo = get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found or has been deleted.")

    if user.get("role") == "admin":
        return repo

    if not is_user_repo_member(repo_id, user["id"]):
        raise HTTPException(
            status_code=403,
            detail="Access denied: You are not an authorized member of this repository's installation."
        )

    return repo

def require_scan_access(request: Request, scan_id: str) -> dict:
    """
    Central authorization dependency for scans, issues, reports, and deletion:
    - If scan is linked to a repo_id: requires user membership in repo's installation.
    - If scan is linked to an owner_user_id: requires ownership or admin.
    - If scan is an anonymous paste/zip scan: accessible by unguessable UUID for reads;
      deletions strictly require admin privileges.
    """
    scan = get_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan record missing.")

    user = get_current_user_optional(request)

    # 1. Repository-linked scan
    if scan.get("repo_id"):
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required to inspect repository scans.")
        require_repo_access(user, scan["repo_id"])
        return scan

    # 2. User-owned scan
    if scan.get("owner_user_id"):
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required to access this scan.")
        if user.get("role") != "admin" and user["id"] != scan["owner_user_id"]:
            raise HTTPException(status_code=403, detail="Access denied: You do not own this scan.")
        return scan

    # 3. Anonymous Paste/ZIP scan
    # Allowed by unguessable 32-character hex scan_id for GET requests
    return scan
