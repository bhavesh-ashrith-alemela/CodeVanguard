import unittest
from app.utils.error_monitoring import (
    scrub_sensitive_string,
    scrub_data_structures,
    sentry_before_send,
    sentry_before_breadcrumb,
    capture_exception,
    capture_message,
)

class TestErrorMonitoring(unittest.TestCase):
    def test_scrub_sensitive_string_tokens(self):
        stripe_mock = "sk_live_" + "51Abcdefghijklmnopqrstuvw"
        sample = (
            "Error with token ghs_1234567890abcdefghijklmnopqrstuvwxyz and "
            "Authorization: Bearer my_secret_bearer_token_xyz and "
            "AWS Key AKIAIOSFODNN7EXAMPLE and "
            f"Stripe {stripe_mock} and "
            "Slack xoxb-1234567890-abcdef"
        )
        scrubbed = scrub_sensitive_string(sample)
        self.assertNotIn("ghs_1234567890abcdefghijklmnopqrstuvwxyz", scrubbed)
        self.assertIn("[REDACTED_GITHUB_TOKEN]", scrubbed)
        self.assertNotIn("my_secret_bearer_token_xyz", scrubbed)
        self.assertIn("[REDACTED_BEARER_TOKEN]", scrubbed)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", scrubbed)
        self.assertIn("[REDACTED_AWS_KEY]", scrubbed)
        self.assertNotIn(stripe_mock, scrubbed)
        self.assertIn("[REDACTED_STRIPE_KEY]", scrubbed)
        self.assertNotIn("xoxb-1234567890-abcdef", scrubbed)
        self.assertIn("[REDACTED_SLACK_TOKEN]", scrubbed)

    def test_scrub_private_keys_and_jwts(self):
        priv_key = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Y...\n-----END RSA PRIVATE KEY-----"
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        text = f"Found {priv_key} and session {jwt}"
        scrubbed = scrub_sensitive_string(text)
        self.assertNotIn("BEGIN RSA PRIVATE KEY", scrubbed)
        self.assertIn("[REDACTED_PRIVATE_KEY]", scrubbed)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIs", scrubbed)
        self.assertIn("[REDACTED_JWT]", scrubbed)

    def test_scrub_data_structures(self):
        payload = {
            "normal_field": "hello world",
            "password": "SuperSecretPassword123!",
            "token": "ghp_abcdefghijklmnopqrstuvwxyz123456",
            "source_code": "def secret_algo(): return 42",
            "nested": {
                "client_secret": "my-client-secret-99",
                "details": "Safe info with Bearer abcdef123456"
            },
            "list_items": [
                {"api_key": "secret_key_val"},
                "Normal list string"
            ]
        }
        scrubbed = scrub_data_structures(payload)
        self.assertEqual(scrubbed["normal_field"], "hello world")
        self.assertEqual(scrubbed["password"], "[REDACTED]")
        self.assertEqual(scrubbed["token"], "[REDACTED]")
        self.assertEqual(scrubbed["source_code"], "[REDACTED]")
        self.assertEqual(scrubbed["nested"]["client_secret"], "[REDACTED]")
        self.assertNotIn("abcdef123456", scrubbed["nested"]["details"])
        self.assertEqual(scrubbed["list_items"][0]["api_key"], "[REDACTED]")
        self.assertEqual(scrubbed["list_items"][1], "Normal list string")

    def test_sentry_before_send_strips_code_context_and_vars(self):
        event = {
            "message": "Uncaught exception",
            "exception": {
                "values": [
                    {
                        "type": "ValueError",
                        "value": "Failed with token ghs_abcdefghijklmnopqrstuvwxyz123456",
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "app/scanner.py",
                                    "function": "run_scan",
                                    "lineno": 42,
                                    "vars": {"repo_secret": "secret123", "code": "eval(user_input)"},
                                    "pre_context": ["import os", "def run():"],
                                    "context_line": "    leak_secret(repo_secret)",
                                    "post_context": ["    return True"]
                                }
                            ]
                        }
                    }
                ]
            },
            "request": {
                "headers": {"Authorization": "Bearer secret_bearer_token_abc123"},
                "cookies": "session=xyz123",
                "data": {"password": "adminpassword"}
            },
            "breadcrumbs": {
                "values": [
                    {"message": "Processed token ghs_1234567890abcdefghijklmnopqrstuvwxyz", "data": {"key": "value"}}
                ]
            }
        }

        sanitized = sentry_before_send(event, {})
        frame = sanitized["exception"]["values"][0]["stacktrace"]["frames"][0]
        # Verify source code context is completely stripped
        self.assertNotIn("pre_context", frame)
        self.assertNotIn("context_line", frame)
        self.assertNotIn("post_context", frame)
        self.assertEqual(frame["vars"], {})

        # Verify request cookies & tokens redacted
        self.assertEqual(sanitized["request"]["cookies"], "[REDACTED]")
        self.assertNotIn("secret_bearer_token_abc123", str(sanitized["request"]["headers"]))
        self.assertEqual(sanitized["request"]["data"]["password"], "[REDACTED]")

        # Verify breadcrumbs sanitized
        crumb_msg = sanitized["breadcrumbs"]["values"][0]["message"]
        self.assertNotIn("ghs_1234567890abcdefghijklmnopqrstuvwxyz", crumb_msg)
        self.assertIn("[REDACTED_GITHUB_TOKEN]", crumb_msg)

    def test_capture_exception_and_message(self):
        try:
            raise RuntimeError("Database connection timed out with token ghs_testtesttest1234567890abcdef")
        except Exception as e:
            # Should not throw any exception
            capture_exception(e, extra={"repo_name": "owner/repo", "password": "leak"})

        capture_message("System healthy", level="info", extra={"check": "ok"})

if __name__ == "__main__":
    unittest.main()
