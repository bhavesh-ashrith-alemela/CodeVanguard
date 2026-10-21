import logging
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Request, HTTPException, Depends, Body

from app.utils.auth import require_authenticated_user, require_repo_access
from app.utils.security import verify_origin_or_csrf
from app.utils.db import (
    get_finding_by_id, get_installation, get_latest_fix_attempt_for_finding,
    update_fix_attempt_status, get_repo_daily_fix_count
)
from app.utils.github_app import get_installation_access_token
from app.utils.github import fetch_file_content_from_github
from app.services.autofix.pipeline import run_autofix_pipeline
from app.services.autofix.git_pr import create_fix_pull_request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/repos/{repo_id}/findings/{finding_id}/fix", tags=["autofix"])
repo_autofix_router = APIRouter(prefix="/api/repos/{repo_id}/autofix", tags=["autofix"])

class FixRequestPayload(BaseModel):
    file_content: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None

@router.post("")
async def generate_finding_fix(
    repo_id: str,
    finding_id: str,
    request: Request,
    payload: Optional[FixRequestPayload] = Body(None),
    user: dict = Depends(require_authenticated_user)
):
    """
    Generates and verifies an automated LLM security patch for a finding.
    Enforces repository opt-in and daily quota caps.
    """
    verify_origin_or_csrf(request)
    repo = require_repo_access(user, repo_id)
    finding = get_finding_by_id(repo["id"], finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found in repository.")

    if not repo.get("autofix_enabled"):
        raise HTTPException(
            status_code=403,
            detail="Automated fix generation is disabled for this repository. Enable it in Repository Settings."
        )

    daily_quota = int(repo.get("autofix_daily_quota") or 20)
    used_today = get_repo_daily_fix_count(repo["id"])
    if used_today >= daily_quota:
        raise HTTPException(
            status_code=429,
            detail=f"Daily auto-fix quota exceeded ({used_today}/{daily_quota}). Quota resets at midnight UTC."
        )

    # Resolve file content: from payload if provided (useful for tests/staged diffs), or GitHub Contents API
    file_content = payload.file_content if payload and payload.file_content else None
    if not file_content:
        installation = get_installation(repo["installation_id"])
        if not installation:
            raise HTTPException(status_code=404, detail="Parent GitHub App installation not found.")
        try:
            auth_token, _ = get_installation_access_token(installation["github_installation_id"])
            parts = repo["full_name"].split("/", 1)
            if len(parts) != 2:
                raise ValueError("Invalid repository name format.")
            owner, repo_name = parts[0], parts[1]
            ref_branch = repo.get("default_branch", "main")
            file_content = fetch_file_content_from_github(
                owner=owner,
                repo=repo_name,
                filepath=finding["filepath"],
                ref=ref_branch,
                auth_token=auth_token
            )
        except Exception as e:
            logger.error(f"Failed to fetch source file for auto-fix: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"Unable to fetch source file '{finding['filepath']}' from GitHub: {str(e)}"
            )

    provider = payload.provider if payload else None
    model = payload.model if payload else None

    try:
        fix_attempt = await run_autofix_pipeline(
            repo=repo,
            finding=finding,
            file_content=file_content,
            provider=provider,
            model=model
        )
        return {"fix_attempt": fix_attempt}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Auto-fix pipeline execution failure")
        raise HTTPException(status_code=500, detail=f"Auto-fix generation failed: {str(e)}")

@router.get("")
async def get_latest_fix(
    repo_id: str,
    finding_id: str,
    user: dict = Depends(require_authenticated_user)
):
    """Retrieves the most recent auto-fix attempt for a finding."""
    repo = require_repo_access(user, repo_id)
    finding = get_finding_by_id(repo["id"], finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found in repository.")

    attempt = get_latest_fix_attempt_for_finding(finding_id, repo_id=repo["id"])
    return {"fix_attempt": attempt}

@router.post("/pr")
async def create_pr_for_fix(
    repo_id: str,
    finding_id: str,
    request: Request,
    user: dict = Depends(require_authenticated_user)
):
    """
    Creates a pull request with the verified security patch on GitHub.
    Branch: cv/fix-<rule>-<fingerprint8>
    Never pushes directly to the default branch.
    """
    verify_origin_or_csrf(request)
    repo = require_repo_access(user, repo_id)
    finding = get_finding_by_id(repo["id"], finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found in repository.")

    attempt = get_latest_fix_attempt_for_finding(finding_id, repo_id=repo["id"])
    if not attempt:
        raise HTTPException(status_code=404, detail="No auto-fix attempt exists for this finding.")

    if attempt.get("status") not in ("verified", "pr_opened", "merged"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot open PR: fix attempt is in '{attempt.get('status')}' status, must be 'verified'."
        )

    if attempt.get("status") in ("pr_opened", "merged") and attempt.get("pr_number"):
        return {
            "pr_number": attempt.get("pr_number"),
            "pr_url": attempt.get("pr_url"),
            "branch_name": attempt.get("branch_name")
        }

    if not attempt.get("patch_code"):
        raise HTTPException(status_code=400, detail="Verified patch code is missing from the record.")

    installation = get_installation(repo["installation_id"])
    if not installation:
        raise HTTPException(status_code=404, detail="Parent GitHub App installation not found.")

    parts = repo["full_name"].split("/", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid repository full name.")
    owner, repo_name = parts[0], parts[1]

    try:
        auth_token, _ = get_installation_access_token(installation["github_installation_id"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to obtain GitHub App token: {str(e)}")

    v_json = attempt.get("verification_json")
    scanners = v_json.get("scanners_run", ["bandit", "semgrep"]) if isinstance(v_json, dict) else ["bandit", "semgrep"]

    try:
        pr_result = create_fix_pull_request(
            owner=owner,
            repo=repo_name,
            default_branch=repo.get("default_branch", "main"),
            filepath=attempt["target_file"],
            patched_file_content=attempt["patch_code"],
            rule_id=finding.get("rule_id", "security-issue"),
            severity=finding.get("severity", "high"),
            start_line=int(attempt.get("start_line") or 1),
            end_line=int(attempt.get("end_line") or 1),
            explanation=attempt.get("explanation") or "Automated verified security patch.",
            original_fingerprint=finding.get("fingerprint", ""),
            scanners_run=scanners,
            auth_token=auth_token
        )
    except Exception as e:
        logger.error(f"Failed to create fix PR on GitHub: {e}")
        raise HTTPException(status_code=502, detail=f"GitHub PR creation failed: {str(e)}")

    update_fix_attempt_status(
        attempt["id"],
        status="pr_opened",
        pr_number=pr_result["pr_number"],
        pr_url=pr_result["pr_url"],
        branch_name=pr_result["branch_name"]
    )

    return pr_result

@repo_autofix_router.get("/quota")
async def get_autofix_quota(
    repo_id: str,
    user: dict = Depends(require_authenticated_user)
):
    """Returns the current auto-fix quota usage for the repository."""
    repo = require_repo_access(user, repo_id)
    daily_quota = int(repo.get("autofix_daily_quota") or 20)
    used_today = get_repo_daily_fix_count(repo["id"])
    enabled = bool(repo.get("autofix_enabled"))

    return {
        "autofix_enabled": enabled,
        "daily_quota": daily_quota,
        "used_today": used_today,
        "remaining": max(0, daily_quota - used_today)
    }
