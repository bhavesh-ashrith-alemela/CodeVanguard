import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.github import (
    validate_github_url, validate_branch_name, SafeGitHubRedirectHandler
)

class TestGitHubIngestion(unittest.TestCase):
    def test_valid_github_urls(self):
        """Prove that valid GitHub repository URLs are parsed cleanly."""
        valid_cases = [
            ("https://github.com/octocat/Hello-World", ("octocat", "Hello-World")),
            ("https://github.com/facebook/react.git", ("facebook", "react")),
            ("https://github.com/golang/go/", ("golang", "go")),
            ("https://github.com/owner-with-dash/repo_with_underscore", ("owner-with-dash", "repo_with_underscore")),
            ("https://github.com/org.team/app.service", ("org.team", "app.service")),
        ]
        for url, expected in valid_cases:
            owner, repo = validate_github_url(url)
            self.assertEqual((owner, repo), expected, f"Failed on URL: {url}")

    def test_insecure_or_spoofed_urls_rejected(self):
        """Prove that non-HTTPS, spoofed domains, and IP addresses are rejected (SSRF protection)."""
        invalid_urls = [
            "http://github.com/owner/repo",                # HTTP plain text
            "ftp://github.com/owner/repo",                 # FTP
            "https://evil-github.com/owner/repo",          # Domain spoofing
            "https://github.com.attacker.com/owner/repo",  # Subdomain trick
            "https://127.0.0.1/owner/repo",                # Localhost IP
            "https://169.254.169.254/owner/repo",          # AWS/Cloud Metadata IP
            "https://github.com:8443/owner/repo",          # Custom port
            "https://admin:pass@github.com/owner/repo",    # Embedded credentials
            "https://github.com/owner/repo?token=secret",  # Query strings
            "https://github.com/owner/repo#fragment",      # Fragments
            "https://github.com/..%2f..%2f/repo",          # URL encoded traversal
            "https://github.com/.hidden/repo",             # Leading dot in owner
            "https://github.com/owner/.hidden",            # Leading dot in repo
            "https://github.com/owner",                    # Missing repo segment
            "https://github.com/owner/repo/extra/path",    # Excess path segments
            "",                                            # Empty
            None,                                          # None
        ]
        for url in invalid_urls:
            with self.assertRaises(ValueError, msg=f"Should have rejected: {url}"):
                validate_github_url(url)

    def test_branch_validation(self):
        """Prove safe branch name validation."""
        self.assertEqual(validate_branch_name("main"), "main")
        self.assertEqual(validate_branch_name("feature/v1.2-patch"), "feature/v1.2-patch")
        self.assertIsNone(validate_branch_name(None))
        self.assertIsNone(validate_branch_name(""))

        invalid_branches = [
            "../main",
            "/leading/slash",
            "trailing/slash/",
            "branch.lock",
            "branch;echo evil",
            "branch`id`",
            "branch$VAR",
            "branch~1",
            "branch^2",
            "branch:name",
        ]
        for b in invalid_branches:
            with self.assertRaises(ValueError, msg=f"Should have rejected branch: {b}"):
                validate_branch_name(b)

    def test_ssrf_redirect_handler(self):
        """Prove that HTTP redirects to unauthorized hosts or non-HTTPS schemes are blocked."""
        handler = SafeGitHubRedirectHandler()

        # Insecure scheme
        with self.assertRaises(ValueError) as ctx:
            handler.redirect_request(None, None, 302, "", {}, "http://codeload.github.com/archive.tar.gz")
        self.assertIn("Insecure redirect scheme", str(ctx.exception))

        # Untrusted external host
        with self.assertRaises(ValueError) as ctx:
            handler.redirect_request(None, None, 302, "", {}, "https://attacker.com/payload.tar.gz")
        self.assertIn("Redirect to untrusted host", str(ctx.exception))

        # Internal metadata host
        with self.assertRaises(ValueError) as ctx:
            handler.redirect_request(None, None, 302, "", {}, "https://169.254.169.254/secret")
        self.assertIn("Redirect to untrusted host", str(ctx.exception))

    def test_authorization_header_stripped_on_codeload_redirect(self):
        """Prove that sensitive Authorization headers are stripped when redirected to codeload.github.com."""
        import urllib.request
        handler = SafeGitHubRedirectHandler()

        # Request to api.github.com with Bearer token
        req = urllib.request.Request(
            "https://api.github.com/repos/octocat/Hello-World/tarball/4b825dc642cb6eb9a060e54bf8d69288fbee4904",
            headers={"Authorization": "Bearer ghp_secret_github_token_12345"}
        )

        # Redirect to codeload.github.com
        new_req = handler.redirect_request(
            req, None, 302, "Found", {},
            "https://codeload.github.com/octocat/Hello-World/legacy.tar.gz/4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        )

        self.assertIsNotNone(new_req)
        # Authorization header must NOT be present in redirected request
        self.assertNotIn("Authorization", new_req.headers)
        self.assertNotIn("authorization", new_req.headers)
        self.assertNotIn("Authorization", getattr(new_req, "unredirected_hdrs", {}))
        self.assertNotIn("authorization", getattr(new_req, "unredirected_hdrs", {}))

    def test_commit_sha_validation(self):
        """Prove that commit SHA must strictly be 40 hexadecimal characters."""
        from app.utils.github import COMMIT_SHA_REGEX, download_github_tarball

        valid_sha = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        self.assertTrue(bool(COMMIT_SHA_REGEX.match(valid_sha)))

        invalid_shas = [
            "4b825dc",                              # Too short (short SHA)
            "4b825dc642cb6eb9a060e54bf8d69288fbee4904abc", # Too long
            "4b825dc642cb6eb9a060e54bf8d69288fbee490z", # Invalid char 'z'
            "../4b825dc642cb6eb9a060e54bf8d69288fbee4904", # Path traversal
            "4b825dc642cb6eb9a060e54bf8d69288fbee4904; rm -rf /", # Command injection
            "",
            "   ",
        ]

        for bad_sha in invalid_shas:
            self.assertFalse(bool(COMMIT_SHA_REGEX.match(bad_sha)), f"Should not match: {bad_sha}")
            with self.assertRaises(ValueError, msg=f"download_github_tarball should reject {bad_sha}"):
                download_github_tarball("owner", "repo", bad_sha, "/tmp/out.tar.gz")

if __name__ == "__main__":
    unittest.main()
