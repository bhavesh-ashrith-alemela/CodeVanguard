from typing import Optional
try:
    from fastapi import APIRouter, Request, HTTPException, Depends
except ImportError:
    class APIRouter:
        def __init__(self, *args, **kwargs): pass
        def get(self, *args, **kwargs): return lambda f: f
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = None):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)
    Request = object
    Depends = lambda f=None: f

from app.utils.auth import require_authenticated_user, require_repo_access
from app.utils.db import (
    get_repository_pull_requests, get_pull_request_scans,
    get_scan_issues, get_db_connection,
    get_latest_pr_summary, get_pr_summaries_history
)

router = APIRouter(prefix="/api/repos/{repo_id}/pulls", tags=["pull_requests"])

@router.get("")
async def list_repo_pull_requests(
    repo_id: str,
    request: Request,
    user: dict = Depends(require_authenticated_user)
):
    """Lists all pull requests analyzed for this repository with verdict chips and delta metrics."""
    repo = require_repo_access(user, repo_id)
    pull_requests = get_repository_pull_requests(repo["id"])
    return {"pull_requests": pull_requests}

@router.get("/{pr_number}")
async def get_pull_request_details(
    repo_id: str,
    pr_number: int,
    request: Request,
    user: dict = Depends(require_authenticated_user)
):
    """
    Retrieves PR details including verdict banner metrics, new findings list,
    findings delta, push-by-push scan timeline, and latest deterministic summary.
    """
    repo = require_repo_access(user, repo_id)
    timeline = get_pull_request_scans(repo["id"], pr_number)

    if not timeline:
        raise HTTPException(status_code=404, detail=f"No scans recorded for Pull Request #{pr_number}.")

    latest_scan_summary = timeline[0]
    scan_id = latest_scan_summary["id"]

    # Fetch issues for latest PR scan
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scans WHERE id = ?", (scan_id,))
        full_scan = dict(cursor.fetchone())

    raw_issues = get_scan_issues(scan_id)
    new_issues = [iss for iss in raw_issues if iss.get("is_new", 1)]
    existing_issues = [iss for iss in raw_issues if not iss.get("is_new", 1)]

    # Fetch latest PR summary facts if available
    latest_summary = get_latest_pr_summary(repo["id"], pr_number)

    return {
        "pr_number": pr_number,
        "repo": repo,
        "latest_scan": full_scan,
        "new_issues": new_issues,
        "existing_issues_count": len(existing_issues),
        "timeline": timeline,
        "summary": latest_summary
    }

@router.get("/{pr_number}/summary")
async def get_pull_request_summary(
    repo_id: str,
    pr_number: int,
    request: Request,
    history: bool = False,
    user: dict = Depends(require_authenticated_user)
):
    """
    Retrieves deterministic summary facts and optional narrative for a pull request.
    If history=true, returns full historical timeline of summaries for this PR.
    Enforces repository tenancy access control.
    """
    repo = require_repo_access(user, repo_id)

    if history:
        summaries = get_pr_summaries_history(repo["id"], pr_number)
        return {"summaries": summaries}

    summary = get_latest_pr_summary(repo["id"], pr_number)
    if not summary:
        raise HTTPException(status_code=404, detail=f"No security summary generated for Pull Request #{pr_number}.")
    return summary
