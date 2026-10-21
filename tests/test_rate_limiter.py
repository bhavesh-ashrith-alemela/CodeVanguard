import unittest
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.rate_limiter import (
    InMemoryRateLimiter, acquire_active_scan, release_active_scan,
    GLOBAL_CONCURRENT_SCANS_LIMIT
)

class TestRateLimiterAndAbuseControls(unittest.TestCase):
    def test_in_memory_rate_limiter_window(self):
        """Prove that requests exceeding limit within sliding window are rejected."""
        limiter = InMemoryRateLimiter(requests_limit=3, window_seconds=1)
        ip = "192.168.1.100"

        self.assertTrue(limiter.is_allowed(ip))
        self.assertTrue(limiter.is_allowed(ip))
        self.assertTrue(limiter.is_allowed(ip))
        # 4th request within window rejected
        self.assertFalse(limiter.is_allowed(ip))

        # Sleep past window
        time.sleep(1.05)
        self.assertTrue(limiter.is_allowed(ip))

    def test_per_ip_active_scan_limit(self):
        """Prove that a client IP cannot start more than 1 active scan at a time."""
        ip = "10.0.0.5"
        scan_1 = "scan_001"
        scan_2 = "scan_002"

        # 1. Acquire scan 1
        allowed, reason = acquire_active_scan(ip, scan_1)
        self.assertTrue(allowed)

        # 2. Try acquiring scan 2 from same IP -> Rejected!
        allowed_second, reason_second = acquire_active_scan(ip, scan_2)
        self.assertFalse(allowed_second)
        self.assertIn("already have an active scan in progress", reason_second)

        # 3. Release scan 1
        release_active_scan(ip, scan_1)

        # 4. Now scan 2 should succeed
        allowed_retry, _ = acquire_active_scan(ip, scan_2)
        self.assertTrue(allowed_retry)

        # Clean up
        release_active_scan(ip, scan_2)

    def test_global_concurrency_cap(self):
        """Prove that scans exceeding GLOBAL_CONCURRENT_SCANS_LIMIT are rejected."""
        allocated = []
        for i in range(GLOBAL_CONCURRENT_SCANS_LIMIT):
            ip = f"172.16.0.{i+1}"
            scan_id = f"test_concurrency_{i}"
            allowed, _ = acquire_active_scan(ip, scan_id)
            self.assertTrue(allowed)
            allocated.append((ip, scan_id))

        # Next one from a new IP should hit global concurrency cap
        busy_ip = "172.16.0.250"
        allowed_busy, reason_busy = acquire_active_scan(busy_ip, "excess_scan")
        self.assertFalse(allowed_busy)
        self.assertIn("Server busy", reason_busy)

        # Release one
        first_ip, first_scan = allocated[0]
        release_active_scan(first_ip, first_scan)

        # Now the busy IP should be allowed
        allowed_after, _ = acquire_active_scan(busy_ip, "excess_scan")
        self.assertTrue(allowed_after)

        # Clean up all
        release_active_scan(busy_ip, "excess_scan")
        for ip, s_id in allocated[1:]:
            release_active_scan(ip, s_id)

if __name__ == "__main__":
    unittest.main()
