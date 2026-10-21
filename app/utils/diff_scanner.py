"""
Diff-Aware Pull Request Scanning and Finding Classification Module.

Design Decision: Head SHA vs Merge Ref
---------------------------------------
CodeVanguard intentionally analyzes the exact PR commit SHA (`head.sha`) rather than
GitHub's synthetic merge ref (`refs/pull/{id}/merge`) for the following security and correctness reasons:
1. Reproducibility & Cryptographic Integrity: `head.sha` is an immutable, signed commit authored
   by the contributor. The merge ref is dynamically and ephemerally constructed by GitHub,
   can change between webhook delivery and tarball download, and is not signed.
2. Branch Protection Requirements: GitHub's Required Status Checks and Check Runs must be
   associated directly with `head.sha` to unblock pull request merging.
3. Conflict Isolation: A synthetic merge ref can fail to build or parse if the base branch has
   diverged with syntactic merge conflicts, causing false positive scan failures.

Cross-File Analysis Limits:
---------------------------
Scanning only files modified in the pull request provides sub-minute feedback and focuses
remediation on developer diffs. However, diff scanning cannot detect inter-procedural taint
flows originating from unchanged caller modules unless the full AST dependency graph is
constructed. CodeVanguard compensates for this by running a full-codebase baseline scan on
every default-branch merge.
"""

import os
import json
import logging
import urllib.request
import urllib.error
from typing import List, Set, Dict, Tuple, Optional, Any

from app.utils.file_filter import SUPPORTED_EXTENSIONS, matches_ignore_patterns, MAX_FILE_BYTES
from app.utils.github import get_safe_opener

logger = logging.getLogger(__name__)

MAX_PR_FILES_LIMIT = int(os.environ.get("MAX_PR_CHANGED_FILES", 300))

def fetch_pr_changed_files(
    owner: str,
    repo: str,
    pull_number: int,
    auth_token: Optional[str] = None
) -> List[str]:
    """
    Fetches the list of filenames modified in a pull request via the GitHub REST API.
    Handles pagination (up to MAX_PR_FILES_LIMIT files).
    Uses safe opener to prevent SSRF and caps response read size.
    """
    changed_files: List[str] = []
    page = 1
    per_page = 100

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "CodeVanguard-SAST/1.0"
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    opener = get_safe_opener()

    while len(changed_files) < MAX_PR_FILES_LIMIT:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}/files?page={page}&per_page={per_page}"
        req = urllib.request.Request(api_url, headers=headers)

        try:
            with opener.open(req, timeout=15) as resp:
                data = json.loads(resp.read(10 * 1024 * 1024).decode("utf-8"))
                if not data or not isinstance(data, list):
                    break
                for item in data:
                    filename = item.get("filename")
                    status = item.get("status")
                    # Ignore deleted files since they no longer exist in the head workspace
                    if filename and status != "removed":
                        changed_files.append(filename)
                if len(data) < per_page:
                    break
                page += 1
        except urllib.error.HTTPError as he:
            logger.warning(f"GitHub API error fetching PR changed files ({he.code}): {he.reason}")
            break
        except Exception as e:
            logger.warning(f"Failed to fetch PR changed files: {e}")
            break

    return changed_files

def fetch_pr_files_with_patches(
    owner: str,
    repo: str,
    pull_number: int,
    auth_token: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetches the list of changed files with diff patches from GitHub REST API.
    Caps max files at MAX_PR_FILES_LIMIT and enforces size limit per response.
    """
    file_items: List[Dict[str, Any]] = []
    page = 1
    per_page = 100

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "CodeVanguard-SAST/1.0"
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    opener = get_safe_opener()

    while len(file_items) < MAX_PR_FILES_LIMIT:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}/files?page={page}&per_page={per_page}"
        req = urllib.request.Request(api_url, headers=headers)

        try:
            with opener.open(req, timeout=15) as resp:
                data = json.loads(resp.read(10 * 1024 * 1024).decode("utf-8"))
                if not data or not isinstance(data, list):
                    break
                for item in data:
                    filename = item.get("filename")
                    if filename:
                        file_items.append({
                            "filename": filename,
                            "status": item.get("status", "modified"),
                            "additions": item.get("additions", 0),
                            "deletions": item.get("deletions", 0),
                            "patch": item.get("patch", "")
                        })
                if len(data) < per_page:
                    break
                page += 1
        except Exception as e:
            logger.warning(f"Failed to fetch PR files with patches: {e}")
            break

    return file_items

def fetch_pr_metadata(
    owner: str,
    repo: str,
    pull_number: int,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetches PR details (title, author, base/head SHAs, additions/deletions) from GitHub REST API.
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "CodeVanguard-SAST/1.0"
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    opener = get_safe_opener()
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with opener.open(req, timeout=15) as resp:
            data = json.loads(resp.read(10 * 1024 * 1024).decode("utf-8"))
            return {
                "number": pull_number,
                "title": data.get("title", f"Pull Request #{pull_number}"),
                "author": data.get("user", {}).get("login", "unknown"),
                "head_sha": data.get("head", {}).get("sha", ""),
                "base_sha": data.get("base", {}).get("sha", ""),
                "files_changed": data.get("changed_files", 0),
                "additions": data.get("additions", 0),
                "deletions": data.get("deletions", 0)
            }
    except Exception as e:
        logger.warning(f"Failed to fetch PR metadata for #{pull_number}: {e}")
        return {
            "number": pull_number,
            "title": f"Pull Request #{pull_number}",
            "author": "unknown",
            "head_sha": "",
            "base_sha": "",
            "files_changed": 0,
            "additions": 0,
            "deletions": 0
        }


def filter_pr_scan_targets(
    repo_dir: str,
    changed_files: List[str],
    ignore_patterns: Optional[List[str]] = None
) -> List[str]:
    """
    Intersects the PR changed files with supported source code extensions,
    file size limits, and repository ignore patterns.
    Defends against path traversal, symlinks, and files outside repo_dir.
    Returns absolute paths of target files inside repo_dir.
    """
    ignore_pats = ignore_patterns or []
    target_paths: List[str] = []
    real_repo_dir = os.path.realpath(repo_dir)

    for rel_path in changed_files:
        norm_path = rel_path.replace("\\", "/").strip().lstrip("/")
        
        # 1. Path traversal check
        if any(part in ("..", "") for part in norm_path.split("/")):
            continue

        # 2. Check ignore patterns
        if matches_ignore_patterns(norm_path, ignore_pats):
            continue

        ext = os.path.splitext(norm_path)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        candidate_path = os.path.join(repo_dir, norm_path)
        
        # 3. Disallow symlinks
        if os.path.islink(candidate_path):
            continue

        try:
            real_candidate = os.path.realpath(candidate_path)
            # 4. Strict repository directory containment
            if os.path.commonpath([real_repo_dir, real_candidate]) != real_repo_dir:
                continue

            if os.path.isfile(real_candidate):
                if os.path.getsize(real_candidate) <= MAX_FILE_BYTES:
                    target_paths.append(real_candidate)
        except (OSError, ValueError):
            pass

    return target_paths

def classify_pr_findings(
    current_issues: List[dict],
    baseline_findings: Dict[str, dict],
    changed_files: List[str]
) -> Tuple[List[dict], List[dict], List[dict]]:
    """
    Classifies scan findings for a PR against the baseline findings:
    - new_findings: Found in PR and absent from repository baseline.
    - existing_findings: Found in PR and already recorded in baseline.
    - fixed_findings: Baseline findings located in changed files that no longer exist in PR.
    """
    new_findings: List[dict] = []
    existing_findings: List[dict] = []

    current_fps: Set[str] = set()

    for issue in current_issues:
        fp = issue.get("fingerprint")
        if not fp:
            continue
        current_fps.add(fp)

        if fp in baseline_findings:
            issue["is_new"] = False
            issue["finding_id"] = baseline_findings[fp]["id"]
            existing_findings.append(issue)
        else:
            issue["is_new"] = True
            new_findings.append(issue)

    # Detect baseline findings in the changed files that were resolved
    norm_changed_files = {f.replace("\\", "/").strip().lstrip("/") for f in changed_files}
    fixed_findings: List[dict] = []

    for fp, base_finding in baseline_findings.items():
        base_path = base_finding.get("filepath", "").replace("\\", "/").strip().lstrip("/")
        if base_path in norm_changed_files:
            if fp not in current_fps:
                fixed_findings.append(base_finding)

    return new_findings, existing_findings, fixed_findings

def determine_pr_verdict(
    new_findings: List[dict],
    fail_on: str = "high"
) -> str:
    """
    Calculates the pull request verdict:
    - BLOCK (Check Run failure): At least one new finding meets or exceeds the fail_on threshold.
    - REVIEW (Check Run neutral): New findings exist, but none meet the fail_on threshold.
    - SAFE (Check Run success): Zero new findings introduced.
    """
    if not new_findings:
        return "SAFE"

    severity_weights = {
        "critical": 4,
        "high": 3,
        "medium": 2,
        "low": 1
    }

    threshold_level = severity_weights.get(fail_on.lower(), 3)
    if fail_on.lower() == "none":
        threshold_level = 999  # Never blocks

    highest_new_severity = 0
    for finding in new_findings:
        sev = finding.get("severity", "low").lower()
        weight = severity_weights.get(sev, 1)
        if weight > highest_new_severity:
            highest_new_severity = weight

    if highest_new_severity >= threshold_level:
        return "BLOCK"
    
    return "REVIEW"
