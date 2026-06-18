import time
from collections import defaultdict

class InMemoryRateLimiter:
    """Lightweight in-memory client-IP rate limiter."""
    def __init__(self, requests_limit: int, window_seconds: int):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        # Maps IP address -> list of request timestamps
        self.history = defaultdict(list)

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        # Filter out timestamps outside the sliding window
        self.history[ip] = [t for t in self.history[ip] if now - t < self.window_seconds]
        
        if len(self.history[ip]) >= self.requests_limit:
            return False
            
        self.history[ip].append(now)
        return True

# Rate Limiter Instances
# - Scans: Max 5 per minute per IP to prevent system load exhaustion
scan_limiter = InMemoryRateLimiter(requests_limit=5, window_seconds=60)

# - Logins: Max 5 attempts per 15 minutes to block brute-force attempts
login_limiter = InMemoryRateLimiter(requests_limit=5, window_seconds=900)
