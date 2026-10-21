import os
import hmac
import hashlib
import json
import uuid
import logging
import re
from typing import Optional

try:
    from fastapi import APIRouter, Request, HTTPException, Response
except ImportError:
    class APIRouter:
        def __init__(self, *args, **kwargs): pass
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
    Request = object

from app.utils.db import (
    upsert_installation, get_installation_by_github_id, set_installation_suspension,
    soft_delete_installation, upsert_repository, soft_delete_repository,
    get_db_connection, create_scan, record_webhook_delivery, update_webhook_delivery_status,
    add_installation_member, get_user_by_github_id
)
from app.utils.rate_limiter import get_redis_client
from app.queue.redis_pool import enqueue_scan_job

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_github_signature(raw_body: bytes, signature_header: Optional[str]) -> bool:
    """Performs constant-time HMAC-SHA256 signature verification against X-Hub-Signature-256."""
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
    if not secret:
        logger.warning("GITHUB_WEBHOOK_SECRET not configured. Rejecting webhook request.")
        return False

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    computed = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature_header)

def supersede_active_pr_scans(repo_id: str, pr_number: int, new_scan_id: str) -> None:
    """Cancels/supersedes any previously running scans on the same PR when a newer commit arrives."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE scans
                SET status = 'failed', error_message = 'Superseded by newer commit on pull request.', progress = 'failed'
                WHERE repo_id = ? AND pr_number = ? AND status IN ('pending', 'running') AND id != ?
            """, (repo_id, pr_number, new_scan_id))
            conn.commit()
    except Exception as e:
        logger.warning(f"Error superseding older PR scan in database: {e}")

    redis_client = get_redis_client()
    key = f"github:pr_active_scan:{repo_id}:{pr_number}"
    if redis_client:
        try:
            redis_client.set(key, new_scan_id, ex=86400)
        except Exception as e:
            logger.warning(f"Error superseding older PR scan in Redis: {e}")

@router.post("/api/github/webhook", status_code=202)
@router.post("/api/webhook/github", status_code=202)
@router.post("/webhook", status_code=202)
async def github_webhook_receiver(request: Request):
    """
    GitHub App Webhook Intake:
    1. Enforces payload body size cap (10 MB).
    2. Verifies HMAC-SHA256 signature in constant-time.
    3. Enforces deduplication using X-Hub-Delivery in Redis (24h TTL) and webhook_deliveries table.
    4. Handles pull_request, push, check_run/check_suite rerequests, installation, and repositories.
    5. Enqueues background scan jobs and returns 202 quickly without blocking delivery timeouts.
    """

    raw_body = await request.body()
    if len(raw_body) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Webhook payload exceeds maximum size limit (10MB).")

    sig_header = request.headers.get("x-hub-signature-256")

    # 1. Signature Verification
    if not verify_github_signature(raw_body, sig_header):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Hub-Signature-256")

    # 2. Delivery Deduplication via Redis & Database
    raw_delivery_id = request.headers.get("x-hub-delivery")
    if raw_delivery_id and re.match(r'^[a-zA-Z0-9_\-]+$', raw_delivery_id):
        delivery_id = raw_delivery_id
    else:
        delivery_id = uuid.uuid4().hex

    redis_client = get_redis_client()
    if redis_client:
        try:
            is_new = redis_client.set(f"github:webhook:{delivery_id}", "1", nx=True, ex=86400)
            if not is_new:
                return Response(content="Delivery already processed", status_code=202)
        except Exception as e:
            logger.warning(f"Webhook Redis deduplication check failed: {e}")

    # Fallback / Defense-in-depth: Check database delivery deduplication
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM webhook_deliveries WHERE id = ?", (delivery_id,))
            if cursor.fetchone():
                return Response(content="Delivery already processed", status_code=202)
    except Exception as e:
        logger.warning(f"Webhook DB deduplication check error: {e}")

    # 3. Payload Parsing
    event_type = request.headers.get("x-github-event")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON webhook payload")

    action = payload.get("action")
    repo_payload = payload.get("repository", {})
    github_repo_id = repo_payload.get("id")

    # Resolve local repository if present
    local_repo = None
    if github_repo_id:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM repositories WHERE github_repo_id = ? AND deleted_at IS NULL", (github_repo_id,))
            row = cursor.fetchone()
            if row:
                local_repo = dict(row)

    # Initial delivery audit record
    record_webhook_delivery(
        delivery_id=delivery_id,
        event=event_type or "unknown",
        action=action,
        repository_id=local_repo["id"] if local_repo else None,
        status="received"
    )

    # 4. Event Processing
    if event_type == "installation":
        inst_data = payload.get("installation", {})
        github_inst_id = inst_data.get("id")
        account = inst_data.get("account", {})
        account_login = account.get("login", "unknown")
        account_type = account.get("type", "User")
        account_avatar = account.get("avatar_url")

        sender = payload.get("sender", {})
        sender_github_id = sender.get("id")

        if action == "created":
            inst = upsert_installation(github_inst_id, account_login, account_type, account_avatar)
            if sender_github_id:
                sender_user = get_user_by_github_id(sender_github_id)
                if sender_user:
                    add_installation_member(inst["id"], sender_user["id"], role="admin")

            for r in payload.get("repositories", []):

                new_repo = upsert_repository(
                    inst["id"],
                    r["id"],
                    r.get("full_name", f"{account_login}/{r.get('name')}"),
                    r.get("default_branch", "main"),
                    r.get("private", False)
                )
                # Trigger initial baseline scan of default branch
                scan_id = uuid.uuid4().hex
                create_scan(
                    scan_id=scan_id,
                    filename=f"{new_repo['full_name']} (baseline)",
                    file_size=0,
                    source_type="github_app",
                    source_url=f"https://github.com/{new_repo['full_name']}",
                    branch=new_repo["default_branch"],
                    commit_sha=None,
                    repo_id=new_repo["id"],
                    trigger="push"
                )
                await enqueue_scan_job(scan_id, "127.0.0.1")

        elif action == "deleted":
            soft_delete_installation(github_inst_id)
        elif action == "suspend":
            set_installation_suspension(github_inst_id, suspended=True)
        elif action == "unsuspend":
            set_installation_suspension(github_inst_id, suspended=False)

        update_webhook_delivery_status(delivery_id, "processed")

    elif event_type == "installation_repositories":
        github_inst_id = payload.get("installation", {}).get("id")
        inst = get_installation_by_github_id(github_inst_id)
        if inst:
            for r in payload.get("repositories_added", []):
                new_repo = upsert_repository(
                    inst["id"],
                    r["id"],
                    r.get("full_name"),
                    r.get("default_branch", "main"),
                    r.get("private", False)
                )
                # Trigger baseline scan for added repository
                scan_id = uuid.uuid4().hex
                create_scan(
                    scan_id=scan_id,
                    filename=f"{new_repo['full_name']} (baseline)",
                    file_size=0,
                    source_type="github_app",
                    source_url=f"https://github.com/{new_repo['full_name']}",
                    branch=new_repo["default_branch"],
                    commit_sha=None,
                    repo_id=new_repo["id"],
                    trigger="push"
                )
                await enqueue_scan_job(scan_id, "127.0.0.1")

            for r in payload.get("repositories_removed", []):
                soft_delete_repository(r["id"])

        update_webhook_delivery_status(delivery_id, "processed")

    elif event_type == "pull_request":
        # Handled PR actions
        if action in ("opened", "reopened", "synchronize", "ready_for_review"):
            if not local_repo:
                update_webhook_delivery_status(delivery_id, "skipped", "Repository not registered")
                return Response(content="Repository not registered", status_code=202)

            if not local_repo.get("scan_enabled") or not local_repo.get("scan_on_pr", 1):
                update_webhook_delivery_status(delivery_id, "skipped", "PR scanning disabled in repo settings")
                return Response(content="PR scanning disabled", status_code=202)

            pr_data = payload.get("pull_request", {})
            is_draft = pr_data.get("draft", False)
            if is_draft and not local_repo.get("scan_drafts", 0):
                update_webhook_delivery_status(delivery_id, "skipped", "Draft PR skipped")
                return Response(content="Draft PR skipped", status_code=202)

            pr_number = pr_data.get("number")
            head_sha = pr_data.get("head", {}).get("sha")
            branch = pr_data.get("head", {}).get("ref")
            pr_title = pr_data.get("title", f"Pull Request #{pr_number}")
            html_url = repo_payload.get("html_url") or f"https://github.com/{local_repo['full_name']}"

            if not head_sha:
                update_webhook_delivery_status(delivery_id, "failed", "Missing head SHA")
                return Response(content="Missing head SHA", status_code=202)

            scan_id = uuid.uuid4().hex
            supersede_active_pr_scans(local_repo["id"], pr_number, scan_id)

            create_scan(
                scan_id=scan_id,
                filename=pr_title,
                file_size=0,
                source_type="github_app",
                source_url=html_url,
                branch=branch,
                commit_sha=head_sha,
                repo_id=local_repo["id"],
                trigger="pr",
                pr_number=pr_number
            )

            await enqueue_scan_job(scan_id, "127.0.0.1")
            update_webhook_delivery_status(delivery_id, "processed")

        elif action == "closed":
            pr_data = payload.get("pull_request", {})
            pr_number = pr_data.get("number")
            is_merged = bool(pr_data.get("merged", False))
            if local_repo and pr_number:
                try:
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        status = "merged" if is_merged else "closed"
                        cursor.execute("""
                            UPDATE fix_attempts
                            SET status = ?
                            WHERE repo_id = ? AND pr_number = ?
                        """, (status, local_repo["id"], pr_number))
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Failed to update fix_attempt status for closed PR #{pr_number}: {e}")
            update_webhook_delivery_status(delivery_id, "processed")
            return Response(content="PR closed event processed", status_code=202)

    elif event_type == "push":
        ref = payload.get("ref", "")
        if local_repo and not payload.get("deleted", False):
            default_branch = local_repo.get("default_branch", "main")
            if ref == f"refs/heads/{default_branch}":
                if local_repo.get("scan_enabled") and local_repo.get("scan_on_push", 1):
                    head_sha = payload.get("after")
                    if head_sha and head_sha != "0000000000000000000000000000000000000000":
                        scan_id = uuid.uuid4().hex
                        html_url = repo_payload.get("html_url") or f"https://github.com/{local_repo['full_name']}"

                        create_scan(
                            scan_id=scan_id,
                            filename=f"{local_repo['full_name']} ({default_branch})",
                            file_size=0,
                            source_type="github_app",
                            source_url=html_url,
                            branch=default_branch,
                            commit_sha=head_sha,
                            repo_id=local_repo["id"],
                            trigger="push"
                        )

                        await enqueue_scan_job(scan_id, "127.0.0.1")
                        update_webhook_delivery_status(delivery_id, "processed")
                        return Response(content="Push scan enqueued", status_code=202)

        update_webhook_delivery_status(delivery_id, "processed")

    elif event_type in ("check_run", "check_suite") and action == "rerequested":
        check_obj = payload.get("check_run") or payload.get("check_suite", {})
        head_sha = check_obj.get("head_sha")

        if local_repo and head_sha and local_repo.get("scan_enabled"):
            scan_id = uuid.uuid4().hex
            html_url = repo_payload.get("html_url") or f"https://github.com/{local_repo['full_name']}"

            # Check if this SHA belongs to a PR
            pr_list = check_obj.get("pull_requests", [])
            pr_num = pr_list[0].get("number") if pr_list else None
            trigger_type = "pr" if pr_num else "manual"

            create_scan(
                scan_id=scan_id,
                filename=f"Re-scan {head_sha[:7]}",
                file_size=0,
                source_type="github_app",
                source_url=html_url,
                branch=check_obj.get("head_branch") or local_repo.get("default_branch", "main"),
                commit_sha=head_sha,
                repo_id=local_repo["id"],
                trigger=trigger_type,
                pr_number=pr_num
            )
            await enqueue_scan_job(scan_id, "127.0.0.1")
            update_webhook_delivery_status(delivery_id, "processed")

    return Response(content="Event accepted", status_code=202)
