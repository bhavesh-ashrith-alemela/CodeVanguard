import time
import os
from collections import defaultdict
from typing import Tuple, Optional

try:
    from fastapi import Request
except ImportError:
    Request = object

try:
    import redis
except ImportError:
    redis = None

def get_client_ip(request: Request) -> str:
    """Resolves client IP address, checking X-Forwarded-For headers for proxies."""
    if not hasattr(request, "headers"):
        return "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if getattr(request, "client", None) else "unknown"

_redis_client_instance = None

def get_redis_client():
    """Returns a shared redis client instance if REDIS_URL is configured and redis is available."""
    global _redis_client_instance
    if _redis_client_instance is not None:
        return _redis_client_instance
    redis_url = os.environ.get("REDIS_URL")
    if redis_url and redis is not None:
        try:
            _redis_client_instance = redis.Redis.from_url(redis_url, decode_responses=True)
            return _redis_client_instance
        except Exception as e:
            print(f"Warning: Failed to connect to Redis: {e}")
            return None
    return None

class InMemoryRateLimiter:
    """Lightweight in-memory client-IP rate limiter fallback."""
    def __init__(self, requests_limit: int, window_seconds: int):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self.history = defaultdict(list)

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        self.history[ip] = [t for t in self.history[ip] if now - t < self.window_seconds]
        if len(self.history[ip]) >= self.requests_limit:
            return False
        self.history[ip].append(now)
        return True

class RedisRateLimiter:
    """Distributed Redis-backed sliding-window rate limiter."""
    def __init__(self, key_prefix: str, requests_limit: int, window_seconds: int, redis_client=None):
        self.key_prefix = key_prefix
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self._redis = redis_client
        self._fallback = InMemoryRateLimiter(requests_limit, window_seconds)

    def get_redis(self):
        if self._redis is not None:
            return self._redis
        self._redis = get_redis_client()
        return self._redis

    def is_allowed(self, identifier: str) -> bool:
        r = self.get_redis()
        if r is None:
            return self._fallback.is_allowed(identifier)

        key = f"codevanguard:ratelimit:{self.key_prefix}:{identifier}"
        now = time.time()
        clear_before = now - self.window_seconds

        try:
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, clear_before)
            pipe.zcard(key)
            pipe.zadd(key, {f"{now}:{time.time_ns()}": now})
            pipe.expire(key, self.window_seconds + 5)
            _, current_count, _, _ = pipe.execute()
            return current_count < self.requests_limit
        except Exception as e:
            print(f"Redis rate limiter error, falling back to in-memory: {e}")
            return self._fallback.is_allowed(identifier)

# Rate Limiter Instances
# - Scans: Max 5 per minute per IP
scan_limiter = RedisRateLimiter("scan", requests_limit=5, window_seconds=60)

# - Logins: Max 5 attempts per 15 minutes per IP
login_limiter = RedisRateLimiter("login", requests_limit=5, window_seconds=900)

# --- Active Scan Limits & Concurrency Controls ---

GLOBAL_CONCURRENT_SCANS_LIMIT = int(os.environ.get("GLOBAL_CONCURRENT_SCANS", 5))
SCAN_TIMEOUT_SECONDS = int(os.environ.get("SCAN_TIMEOUT_SECONDS", 300))

# In-memory fallbacks for active scans
_mem_active_ips = {}
_mem_global_active = 0

def acquire_active_scan(client_ip: str, scan_id: str, redis_client=None) -> Tuple[bool, str]:
    """
    Enforces abuse controls:
    1. Global concurrency cap across all running scans.
    2. Max of 1 active scan per client IP address.
    Returns (allowed: bool, reason: str)
    """
    global _mem_global_active
    r = redis_client
    if r is None and redis is not None:
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            try:
                r = redis.Redis.from_url(redis_url, decode_responses=True)
            except Exception:
                r = None

    if r is not None:
        try:
            global_key = "codevanguard:active_scans:global"
            ip_key = f"codevanguard:active_scan:ip:{client_ip}"

            # 1. Check IP active scan (atomic set with NX and TTL)
            acquired_ip = r.set(ip_key, scan_id, nx=True, ex=SCAN_TIMEOUT_SECONDS)
            if not acquired_ip:
                return False, "You already have an active scan in progress. Please wait for it to complete."

            # 2. Check global concurrency cap
            current_global = r.incr(global_key)
            if current_global > GLOBAL_CONCURRENT_SCANS_LIMIT:
                # Rollback IP lock and global count
                r.delete(ip_key)
                r.decr(global_key)
                return False, f"Server busy: maximum concurrent scans ({GLOBAL_CONCURRENT_SCANS_LIMIT}) reached. Please retry in a few moments."

            return True, ""
        except Exception as e:
            print(f"Redis active scan error, using in-memory tracker: {e}")

    # In-memory tracking fallback
    if client_ip in _mem_active_ips:
        return False, "You already have an active scan in progress. Please wait for it to complete."

    if _mem_global_active >= GLOBAL_CONCURRENT_SCANS_LIMIT:
        return False, f"Server busy: maximum concurrent scans ({GLOBAL_CONCURRENT_SCANS_LIMIT}) reached. Please retry in a few moments."

    _mem_active_ips[client_ip] = scan_id
    _mem_global_active += 1
    return True, ""

def release_active_scan(client_ip: str, scan_id: str, redis_client=None):
    """Releases the per-IP lock and decrements the global concurrent scan counter."""
    global _mem_global_active
    r = redis_client
    if r is None and redis is not None:
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            try:
                r = redis.Redis.from_url(redis_url, decode_responses=True)
            except Exception:
                r = None

    if r is not None:
        try:
            global_key = "codevanguard:active_scans:global"
            ip_key = f"codevanguard:active_scan:ip:{client_ip}"

            current = r.get(ip_key)
            if current == scan_id:
                r.delete(ip_key)

            new_val = r.decr(global_key)
            if new_val < 0:
                r.set(global_key, 0)
            return
        except Exception as e:
            print(f"Error releasing Redis active scan: {e}")

    # In-memory release fallback
    if _mem_active_ips.get(client_ip) == scan_id:
        del _mem_active_ips[client_ip]
    if _mem_global_active > 0:
        _mem_global_active -= 1
