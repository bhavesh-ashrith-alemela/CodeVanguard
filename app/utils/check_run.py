import json
import logging
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional, List, Dict
from app.utils.github import get_safe_opener

logger = logging.getLogger(__name__)

CHECK_RUN_NAME = "CodeVanguard"
MAX_ANNOTATIONS_PER_REQUEST = 50

def create_check_run(
    owner: str,
    repo: str,
    head_sha: str,
    auth_token: str,
    details_url: Optional[str] = None
) -> Optional[int]:
    """
    Creates an 'in_progress' GitHub Check Run for the target commit SHA.
    Returns the integer check_run_id, or None if creation fails.
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/check-runs"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "CodeVanguard-SAST/1.0",
        "Content-Type": "application/json"
    }

    payload = {
        "name": CHECK_RUN_NAME,
        "head_sha": head_sha,
        "status": "in_progress",
        "started_at": datetime.now().isoformat() + "Z"
    }
    if details_url:
        payload["details_url"] = details_url

    req = urllib.request.Request(api_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    opener = get_safe_opener()

    try:
        with opener.open(req, timeout=15) as resp:
            data = json.loads(resp.read(10 * 1024 * 1024).decode("utf-8"))
            return data.get("id")
    except Exception as e:
        logger.warning(f"Failed to create GitHub Check Run: {e}")
        return None

def build_check_run_annotations(new_findings: List[dict]) -> List[dict]:
    """
    Transforms new findings into GitHub Check Run annotations.
    Severity mapping:
    - critical -> failure
    - high -> failure
    - medium -> warning
    - low -> notice
    """
    annotations = []
    level_map = {
        "critical": "failure",
        "high": "failure",
        "medium": "warning",
        "low": "notice"
    }

    for f in new_findings:
        sev = f.get("severity", "medium").lower()
        level = level_map.get(sev, "warning")
        line = int(f.get("line_number") or 1)
        path = f.get("filepath", "code").replace("\\", "/").strip().lstrip("/")

        title = f.get("fix_title") or f.get("rule_id", "Security Finding")
        msg = f.get("message") or f.get("fix_description", "Potential security vulnerability.")

        annotation = {
            "path": path,
            "start_line": line,
            "end_line": line,
            "annotation_level": level,
            "title": f"[{sev.upper()}] {title}",
            "message": msg
        }
        if f.get("fix_after"):
            annotation["raw_details"] = f"Remediation blueprint:\n{f.get('fix_after')}"

        annotations.append(annotation)

    return annotations

def complete_check_run(
    owner: str,
    repo: str,
    check_run_id: int,
    verdict: str,
    new_findings: List[dict],
    fixed_count: int,
    existing_count: int,
    auth_token: str,
    details_url: Optional[str] = None,
    summary: Optional[str] = None
) -> bool:
    """
    Completes a GitHub Check Run with conclusion ('success', 'failure', or 'neutral')
    and attaches batched annotations (up to 50 annotations per request).
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/check-runs/{check_run_id}"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "CodeVanguard-SAST/1.0",
        "Content-Type": "application/json"
    }

    conclusion_map = {
        "BLOCK": "failure",
        "REVIEW": "neutral",
        "SAFE": "success",
        "block": "failure",
        "attention": "neutral",
        "safe": "success"
    }
    conclusion = conclusion_map.get(verdict, "neutral")

    title = f"CodeVanguard: {len(new_findings)} new issue{'s' if len(new_findings) != 1 else ''} ({verdict.upper()})"
    if verdict.lower() == "safe":
        title = "CodeVanguard: All clear — zero new vulnerabilities (SAFE)"

    summary_text = summary or (
        f"### Security Scan Results: **{verdict.upper()}**\n\n"
        f"- **New Findings:** {len(new_findings)}\n"
        f"- **Fixed Baseline Findings:** {fixed_count}\n"
        f"- **Existing Baseline Findings:** {existing_count}\n"
    )

    all_annotations = build_check_run_annotations(new_findings)
    first_batch = all_annotations[:MAX_ANNOTATIONS_PER_REQUEST]

    output = {
        "title": title,
        "summary": summary_text,
        "annotations": first_batch
    }

    payload = {
        "status": "completed",
        "conclusion": conclusion,
        "completed_at": datetime.now().isoformat() + "Z",
        "output": output
    }
    if details_url:
        payload["details_url"] = details_url

    req = urllib.request.Request(api_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="PATCH")
    opener = get_safe_opener()

    try:
        with opener.open(req, timeout=15):
            pass
    except Exception as e:
        logger.warning(f"Failed to complete GitHub Check Run {check_run_id}: {e}")
        return False

    # Send any remaining annotations in chunks of 50
    remaining = all_annotations[MAX_ANNOTATIONS_PER_REQUEST:]
    while remaining:
        chunk = remaining[:MAX_ANNOTATIONS_PER_REQUEST]
        remaining = remaining[MAX_ANNOTATIONS_PER_REQUEST:]

        patch_payload = {
            "output": {
                "title": title,
                "summary": summary,
                "annotations": chunk
            }
        }
        patch_req = urllib.request.Request(api_url, data=json.dumps(patch_payload).encode("utf-8"), headers=headers, method="PATCH")
        try:
            with opener.open(patch_req, timeout=15):
                pass
        except Exception as e:
            logger.warning(f"Failed to send chunk of annotations for Check Run {check_run_id}: {e}")
            break

    return True
