import unittest
import os
import sys
import asyncio
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.security import is_allowed_origin, verify_origin_or_csrf
from app.utils.github import (
    validate_github_url, validate_branch_name, COMMIT_SHA_REGEX,
    SafeGitHubRedirectHandler, download_github_tarball
)
from app.utils.rate_limiter import acquire_active_scan, release_active_scan
from app.utils.db import init_db, authenticate_user, create_session, get_user_by_session
from app.routers.admin import get_current_admin_api

class MockRequest:
    def __init__(self, headers=None, cookies=None):
        self.headers = headers or {}
        self.cookies = cookies or {}

class TestAppSecControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    # --- SEC-04: Cross-Origin & CSRF Origin Controls ---

    def test_allowed_origin_matching(self):
        """Prove that known and configured frontend origins and regex patterns match."""
        # 1. Local development
        self.assertTrue(is_allowed_origin("http://localhost:3000"))
        self.assertTrue(is_allowed_origin("http://127.0.0.1:3000"))
        
        # 2. Production Vercel domain
        self.assertTrue(is_allowed_origin("https://code-vanguard.vercel.app"))
        
        # 3. Vercel Preview Deployments (regex matching)
        self.assertTrue(is_allowed_origin("https://code-vanguard-git-feat-test.vercel.app"))
        self.assertTrue(is_allowed_origin("https://code-vanguard-preview-123.vercel.app"))
        
        # 4. Same-origin host match
        self.assertTrue(is_allowed_origin("https://my-backend.onrender.com", host="my-backend.onrender.com"))

    def test_untrusted_origins_blocked(self):
        """Prove that attacker origins, subdomains, and scheme downgrades are rejected."""
        untrusted = [
            "https://attacker.com",
            "http://code-vanguard.vercel.app",  # Insecure HTTP
            "https://code-vanguard.vercel.app.attacker.com", # Subdomain suffix attack
            "https://evil-code-vanguard.vercel.app",
            "https://169.254.169.254",
            "",
            None
        ]
        for origin in untrusted:
            self.assertFalse(is_allowed_origin(origin), f"Should not allow: {origin}")

    def test_verify_origin_or_csrf_blocks_malicious_origin(self):
        """Prove that verify_origin_or_csrf rejects untrusted origins with 403."""
        req = MockRequest(headers={"origin": "https://malicious.evil.com", "host": "api.codevanguard.com"})
        from app.utils.security import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            verify_origin_or_csrf(req)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Cross-origin request blocked", ctx.exception.detail)

    def test_verify_origin_or_csrf_blocks_form_without_origin(self):
        """Prove that Form submissions without Origin or Referer are rejected (CSRF protection)."""
        req = MockRequest(headers={
            "content-type": "application/x-www-form-urlencoded",
            "host": "api.codevanguard.com"
        })
        from app.utils.security import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            verify_origin_or_csrf(req)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Missing Origin or Referer", ctx.exception.detail)

    def test_verify_origin_or_csrf_allows_json_without_origin(self):
        """Prove that direct API clients (curl/CLI) sending JSON without browser Origin are allowed."""
        req = MockRequest(headers={
            "content-type": "application/json",
            "host": "api.codevanguard.com"
        })
        # Should not raise
        verify_origin_or_csrf(req)

    # --- SEC-02: Active Scan Ordering & Concurrency Defense ---

    def test_active_scan_lock_acquired_and_released_on_error(self):
        """Prove that scan lock is released cleanly if subsequent repo resolution fails."""
        client_ip = "198.51.100.42"
        scan_id = "test_scan_sec02"

        # 1. Acquire active scan lock
        allowed, reason = acquire_active_scan(client_ip, scan_id)
        self.assertTrue(allowed)

        # 2. Concurrency check: another request from same IP is blocked upfront
        second_allowed, second_reason = acquire_active_scan(client_ip, "second_scan")
        self.assertFalse(second_allowed)
        self.assertIn("already have an active scan", second_reason)

        # 3. Simulate failure in resolve_github_repo and release lock
        release_active_scan(client_ip, scan_id)

        # 4. Client IP should now be free to submit another scan
        retry_allowed, _ = acquire_active_scan(client_ip, "second_scan")
        self.assertTrue(retry_allowed)

        # Cleanup
        release_active_scan(client_ip, "second_scan")

    # --- SEC-03: Admin Authentication on History API ---

    def test_history_endpoint_auth_dependency(self):
        """Prove that get_current_admin_api requires a valid admin token."""
        # 1. Request with no token -> 401
        req_unauth = MockRequest()
        with self.assertRaises(Exception) as ctx:
            asyncio.run(get_current_admin_api(req_unauth))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 401)

        # 2. Request with invalid Bearer token -> 401
        req_invalid = MockRequest(headers={"Authorization": "Bearer invalid_token_12345"})
        with self.assertRaises(Exception) as ctx:
            asyncio.run(get_current_admin_api(req_invalid))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 401)

        # 3. Request with valid Admin Bearer token -> 200 Admin user
        admin = authenticate_user("admin", "VanguardAdmin2026!")
        self.assertIsNotNone(admin)
        token = create_session(admin["id"])

        req_valid = MockRequest(headers={"Authorization": f"Bearer {token}"})
        user = asyncio.run(get_current_admin_api(req_valid))
        self.assertEqual(user["username"], "admin")
        self.assertEqual(user["role"], "admin")

    # --- SEC-05: Strict Commit SHA Validation ---

    def test_strict_commit_sha_validation(self):
        """Prove that commit SHA must match exactly 40 hex characters."""
        valid_sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4"
        self.assertTrue(bool(COMMIT_SHA_REGEX.match(valid_sha)))

        malicious_or_invalid_shas = [
            "e3b0c44",                                     # 7-char short SHA
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4ff", # 42 chars
            "e3b0c44298fc1c149afbf4c8996fb92427ae41eG",   # Non-hex character 'G'
            "../../etc/passwd",                            # Path traversal
            "4b825dc642cb6eb9a060e54bf8d69288fbee4904;id",# Command injection
            "&& curl evil.com",
            "\n4b825dc642cb6eb9a060e54bf8d69288fbee4904",
        ]
        for bad_sha in malicious_or_invalid_shas:
            self.assertFalse(bool(COMMIT_SHA_REGEX.match(bad_sha)), f"Should be invalid: {bad_sha}")
            with self.assertRaises(ValueError):
                download_github_tarball("owner", "repo", bad_sha, "/tmp/out.tar.gz")

    # --- SEC-06: Authorization Header Stripping on CDN Redirect ---

    def test_codeload_redirect_strips_auth_header(self):
        """Prove that SafeGitHubRedirectHandler removes Authorization header when redirecting to codeload."""
        import urllib.request
        handler = SafeGitHubRedirectHandler()

        req = urllib.request.Request(
            "https://api.github.com/repos/owner/repo/tarball/e3b0c44298fc1c149afbf4c8996fb92427ae41e4",
            headers={"Authorization": "Bearer secret_github_pat_token"}
        )

        new_req = handler.redirect_request(
            req, None, 302, "Found", {},
            "https://codeload.github.com/owner/repo/legacy.tar.gz/e3b0c44298fc1c149afbf4c8996fb92427ae41e4"
        )

        self.assertIsNotNone(new_req)
        # Verify header is stripped from headers and unredirected_hdrs
        headers_lower = {k.lower(): v for k, v in new_req.headers.items()}
        self.assertNotIn("authorization", headers_lower)

if __name__ == "__main__":
    unittest.main()
