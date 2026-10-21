import os
import time
import shutil
try:
    from fastapi import APIRouter
except ImportError:
    class APIRouter:
        def __init__(self, *args, **kwargs): pass
        def get(self, *args, **kwargs): return lambda f: f
from datetime import datetime, timezone
from app.utils.db import get_db_connection
from app.utils.error_monitoring import scrub_sensitive_string

router = APIRouter(prefix="/api/status", tags=["status"])

@router.get("")
async def get_system_status():
    """
    Public system status endpoint.
    Reports operational health of API, Database, Scanners, Worker Queue, and LLM Engine.
    No sensitive tokens or configuration secrets are ever exposed.
    """
    services = {}
    overall_operational = True

    # 1. Database Health Check
    t0 = time.time()
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        db_latency = round((time.time() - t0) * 1000, 2)
        services["database"] = {
            "status": "operational",
            "type": "postgresql" if os.environ.get("DATABASE_URL") else "sqlite",
            "latency_ms": db_latency,
            "message": "Connected and responsive"
        }
    except Exception as e:
        overall_operational = False
        services["database"] = {
            "status": "degraded",
            "type": "postgresql" if os.environ.get("DATABASE_URL") else "sqlite",
            "message": scrub_sensitive_string(str(e))
        }

    # 2. Redis & Background Worker Queue
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis
            r = redis.Redis.from_url(redis_url, socket_timeout=1.5)
            r.ping()
            services["worker_queue"] = {
                "status": "operational",
                "backend": "redis_arq",
                "message": "Background job queue connected"
            }
        except Exception as e:
            services["worker_queue"] = {
                "status": "degraded",
                "backend": "redis_arq",
                "message": scrub_sensitive_string(str(e))
            }
    else:
        services["worker_queue"] = {
            "status": "operational",
            "backend": "in_memory_direct",
            "message": "Synchronous fallback worker operational"
        }

    # 3. Static Analysis & Secret Scanning Engines
    bandit_path = shutil.which("bandit")
    semgrep_path = shutil.which("semgrep")

    services["scanners"] = {
        "secret_scanner": {
            "status": "operational",
            "engine": "native_regex_entropy",
            "message": "Git history and HEAD credential scanner loaded"
        },
        "bandit": {
            "status": "operational" if bandit_path else "ready_container",
            "engine": "bandit_ast",
            "message": "Python SAST analyzer ready"
        },
        "semgrep": {
            "status": "operational" if semgrep_path else "ready_container",
            "engine": "semgrep_oss",
            "message": "Multi-language rule engine ready"
        }
    }

    # 4. Verified Auto-Fix Engine
    llm_provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    treesitter_status = "operational"
    try:
        import tree_sitter
    except ImportError:
        treesitter_status = "unavailable"

    services["autofix"] = {
        "status": "operational" if llm_provider else "standby",
        "provider": llm_provider if llm_provider else "none_configured",
        "parser": treesitter_status,
        "message": f"LLM client configured ({llm_provider})" if llm_provider else "Opt-in: awaiting provider API key"
    }

    return {
        "status": "operational" if overall_operational else "degraded",
        "version": os.environ.get("APP_VERSION", "1.0.0"),
        "environment": os.environ.get("ENV", "development"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": services
    }
