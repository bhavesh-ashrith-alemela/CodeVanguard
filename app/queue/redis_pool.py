import os
from typing import Optional

try:
    from arq import create_pool
    from arq.connections import RedisSettings, ArqRedis
except ImportError:
    create_pool = None
    RedisSettings = None
    ArqRedis = None

from app.scanners.scanner import run_scan

_arq_pool: Optional[ArqRedis] = None

async def get_arq_pool() -> Optional[ArqRedis]:
    """Retrieves or initializes the arq Redis connection pool."""
    global _arq_pool
    if _arq_pool is not None:
        return _arq_pool

    redis_url = os.environ.get("REDIS_URL")
    if not redis_url or create_pool is None:
        return None

    try:
        settings = RedisSettings.from_dsn(redis_url)
        _arq_pool = await create_pool(settings)
        return _arq_pool
    except Exception as e:
        print(f"Warning: Failed to connect to arq Redis pool: {e}")
        return None

async def enqueue_scan_job(scan_id: str, client_ip: str = "127.0.0.1", background_tasks = None):
    """
    Enqueues a scan job to the background worker via arq with job_id = scan_id for idempotency.
    If Redis or arq is unavailable (e.g. lightweight local dev), falls back to FastAPI BackgroundTasks.
    """
    pool = await get_arq_pool()
    if pool is not None:
        try:
            # Enqueue with job_id = scan_id to enforce idempotency
            await pool.enqueue_job("run_scan_job", scan_id, client_ip, _job_id=scan_id)
            print(f"[Queue] Enqueued scan job {scan_id} to arq Redis worker.")
            return
        except Exception as e:
            print(f"[Queue] Error enqueueing to Redis, falling back: {e}")

    # Fallback path for local dev or when Redis is not running
    if background_tasks is not None:
        background_tasks.add_task(run_scan, scan_id, client_ip=client_ip)
        print(f"[Queue] Dispatched scan job {scan_id} to in-process BackgroundTasks.")
    else:
        # Run directly in background loop if no BackgroundTasks object provided
        import asyncio
        asyncio.create_task(run_scan(scan_id, client_ip=client_ip))
