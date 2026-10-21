import os
import sys
import time
from datetime import datetime

try:
    from arq import cron
    from arq.connections import RedisSettings
except ImportError:
    cron = None
    RedisSettings = None

from app.utils.db import (
    init_db, get_db_connection, update_scan_status, update_scan_progress,
    purge_deleted_installations
)
from app.utils.file_handler import cleanup_orphaned_temp_dirs
from app.scanners.scanner import run_scan

SCAN_TIMEOUT_SECONDS = int(os.environ.get("SCAN_TIMEOUT_SECONDS", 300))
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", 30))

async def run_scan_job(ctx, scan_id: str, client_ip: str = "127.0.0.1"):
    """arq worker job executing an end-to-end scan."""
    print(f"[Worker] Starting scan execution for job {scan_id}")
    await run_scan(scan_id, client_ip=client_ip)
    print(f"[Worker] Finished scan execution for job {scan_id}")

async def sweep_stale_scans(ctx=None):
    """
    Finds scans stuck in 'running' beyond SCAN_TIMEOUT_SECONDS + 60s
    (caused by worker crashes, OOM events, or network disconnects) and marks them failed.
    """
    now = datetime.now()
    cutoff_seconds = SCAN_TIMEOUT_SECONDS + 60
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, timestamp, status FROM scans WHERE status = 'running'")
        running_scans = cursor.fetchall()
        
        for scan in running_scans:
            scan_dict = dict(scan) if hasattr(scan, "keys") else {"id": scan[0], "timestamp": scan[1]}
            scan_id = scan_dict["id"]
            try:
                started_at = datetime.fromisoformat(scan_dict["timestamp"])
                age_seconds = (now - started_at).total_seconds()
                if age_seconds > cutoff_seconds:
                    print(f"[Sweep] Marking stale scan {scan_id} as failed (running for {int(age_seconds)}s > limit {cutoff_seconds}s)")
                    update_scan_status(scan_id, "failed", error_message="Scan execution timed out or worker restarted.")
                    update_scan_progress(scan_id, "failed")
            except Exception as e:
                print(f"[Sweep] Error evaluating scan {scan_id}: {e}")

async def purge_retention_sweep(ctx=None):
    """Purges soft-deleted installations and repositories beyond RETENTION_DAYS."""
    try:
        purged = purge_deleted_installations(retention_days=RETENTION_DAYS)
        if purged > 0:
            print(f"[Retention] Purged {purged} installations older than {RETENTION_DAYS} days.")
    except Exception as e:
        print(f"[Retention] Error running installation purge sweep: {e}")

async def worker_startup(ctx):
    """Worker initialization hook: purges orphaned workspaces, runs migrations, sweeps stale scans."""
    print("=== CodeVanguard Background Worker Initializing ===")
    
    # 1. Purge all orphaned temporary scan directories from previous dead workers
    print("[Worker] Purging orphaned temp workspace directories...")
    cleanup_orphaned_temp_dirs(max_age_seconds=0)
    
    # 2. Verify Database Schema & Migrations
    print("[Worker] Verifying database connectivity and applying migrations...")
    init_db()
    
    # 3. Sweep any scans left in running state from prior crash
    print("[Worker] Sweeping any stale scans...")
    await sweep_stale_scans(ctx)

    # 4. Run data retention purge sweep
    print("[Worker] Running data retention sweep...")
    await purge_retention_sweep(ctx)
    
    print("=== CodeVanguard Background Worker Ready ===")

async def reconcile_webhooks_job(ctx=None):
    """Periodically reconciles failed GitHub App webhook deliveries."""
    try:
        from app.utils.github_app import reconcile_failed_webhook_deliveries
        count = reconcile_failed_webhook_deliveries()
        if count > 0:
            print(f"[Worker] Webhook Reconcile: Triggered redelivery for {count} failed deliveries.")
    except Exception as e:
        print(f"[Worker] Webhook reconciliation check error: {e}")

async def worker_shutdown(ctx):
    print("CodeVanguard Background Worker shutting down gracefully...")

class WorkerSettings:
    """arq Worker configuration for Render background worker service."""
    functions = [run_scan_job]
    cron_jobs = [
        cron(sweep_stale_scans, minute=None, second=0),
        cron(purge_retention_sweep, hour=3, minute=0),
        cron(reconcile_webhooks_job, minute={0, 15, 30, 45})
    ] if cron is not None else []
    max_tries = 2 # 1 retry for infrastructure error
    job_timeout = SCAN_TIMEOUT_SECONDS
    on_startup = worker_startup
    on_shutdown = worker_shutdown
    redis_settings = (
        RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        if RedisSettings is not None else None
    )
