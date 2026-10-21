import json
import logging
import urllib.request
import urllib.error
from typing import Optional, List, Dict
from app.utils.github import get_safe_opener

logger = logging.getLogger(__name__)

STICKY_COMMENT_MARKER = "<!-- codevanguard-sticky-pr-comment -->"

def format_sticky_comment(
    verdict: str,
    new_findings: List[dict],
    fixed_count: int,
    existing_count: int,
    dashboard_url: str
) -> str:
    """Formats the markdown body for the single sticky PR comment."""
    verdict_badge = {
        "BLOCK": "⛔ **BLOCK** — Action required before merge",
        "REVIEW": "⚠️ **REVIEW** — Warnings detected",
        "SAFE": "✅ **SAFE** — All static security checks passed"
    }.get(verdict, verdict)

    crit = sum(1 for f in new_findings if f.get("severity") == "critical")
    high = sum(1 for f in new_findings if f.get("severity") == "high")
    med = sum(1 for f in new_findings if f.get("severity") == "medium")
    low = sum(1 for f in new_findings if f.get("severity") == "low")

    body_lines = [
        STICKY_COMMENT_MARKER,
        "## 🛡️ CodeVanguard SAST Report",
        "",
        f"**Verdict:** {verdict_badge}",
        "",
        "### Findings Delta",
        f"- **New Findings:** {len(new_findings)} ({crit} Critical, {high} High, {med} Medium, {low} Low)",
        f"- **Fixed Baseline Findings:** {fixed_count}",
        f"- **Existing Baseline Findings:** {existing_count}",
        ""
    ]

    if new_findings:
        body_lines.append("### 🔍 Top New Findings to Fix First")
        top_3 = new_findings[:3]
        for idx, f in enumerate(top_3, start=1):
            sev = f.get("severity", "medium").upper()
            title = f.get("fix_title") or f.get("rule_id", "Security issue")
            path = f.get("filepath", "file")
            line = f.get("line_number", 1)
            desc = f.get("fix_description") or f.get("message", "")

            body_lines.append(f"{idx}. **[{sev}] {title}** (`{path}:{line}`)")
            if desc:
                body_lines.append(f"   > {desc}")
            if f.get("fix_before") and f.get("fix_after"):
                body_lines.append("   ```diff")
                body_lines.append(f"   - {f.get('fix_before')}")
                body_lines.append(f"   + {f.get('fix_after')}")
                body_lines.append("   ```")
        body_lines.append("")

    body_lines.append(f"[👉 View Full Security Report & Blueprints in CodeVanguard]({dashboard_url})")
    body_lines.append("\n*Scanned in an ephemeral non-root workspace with Bandit & Semgrep. Source code is never stored.*")

    return "\n".join(body_lines)

def post_or_update_pr_comment(
    owner: str,
    repo: str,
    pull_number: int,
    verdict: str,
    new_findings: List[dict],
    fixed_count: int,
    existing_count: int,
    auth_token: str,
    dashboard_url: str,
    custom_body: Optional[str] = None
) -> bool:
    """
    Finds existing CodeVanguard sticky PR comment and updates it in place.
    If no prior comment exists, creates a new one. Guarantees zero duplicate comments.
    """
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "CodeVanguard-SAST/1.0",
        "Content-Type": "application/json"
    }

    comment_body = custom_body or format_sticky_comment(
        verdict, new_findings, fixed_count, existing_count, dashboard_url
    )

    opener = get_safe_opener()

    # 1. Look for existing sticky comment
    list_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pull_number}/comments?per_page=100"
    req = urllib.request.Request(list_url, headers=headers)

    existing_comment_id = None
    try:
        with opener.open(req, timeout=15) as resp:
            comments = json.loads(resp.read(10 * 1024 * 1024).decode("utf-8"))
            if isinstance(comments, list):
                for c in comments:
                    if STICKY_COMMENT_MARKER in (c.get("body") or ""):
                        existing_comment_id = c.get("id")
                        break
    except Exception as e:
        logger.warning(f"Error checking existing PR comments: {e}")

    # 2. Update existing or create new
    if existing_comment_id:
        patch_url = f"https://api.github.com/repos/{owner}/{repo}/issues/comments/{existing_comment_id}"
        patch_req = urllib.request.Request(
            patch_url,
            data=json.dumps({"body": comment_body}).encode("utf-8"),
            headers=headers,
            method="PATCH"
        )
        try:
            with opener.open(patch_req, timeout=15):
                logger.info(f"Updated sticky PR comment #{existing_comment_id} on PR #{pull_number}")
                return True
        except Exception as e:
            logger.warning(f"Failed to update existing sticky comment: {e}")
            return False
    else:
        post_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pull_number}/comments"
        post_req = urllib.request.Request(
            post_url,
            data=json.dumps({"body": comment_body}).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        try:
            with opener.open(post_req, timeout=15):
                logger.info(f"Created sticky PR comment on PR #{pull_number}")
                return True
        except Exception as e:
            logger.warning(f"Failed to create new sticky comment: {e}")
            return False
