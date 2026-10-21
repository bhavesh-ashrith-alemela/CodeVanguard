import os
import unittest
import logging
from unittest.mock import patch, MagicMock
from app.utils.github_app import (
    generate_app_jwt, get_installation_access_token,
    SensitiveTokenRedactionFilter, install_log_redaction_filter
)

class TestGitHubAppTokens(unittest.TestCase):
    def setUp(self):
        # Generate a valid RSA key if cryptography is installed, otherwise fallback to fixture
        try:
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import serialization
            priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            self.fake_key = priv.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ).decode("utf-8")
        except Exception:
            self.fake_key = (
                "-----BEGIN RSA PRIVATE KEY-----\n"
                "MIIEowIBAAKCAQEA0Y3J184920491823091283091283091283091283091283\n"
                "-----END RSA PRIVATE KEY-----"
            )
        self.env_patcher = patch.dict(os.environ, {
            "GITHUB_APP_ID": "123456",
            "GITHUB_APP_PRIVATE_KEY": self.fake_key
        })
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    def test_jwt_generation_structure(self):
        """Generates valid 3-part JWT with proper header and payload claims."""
        token = generate_app_jwt()
        parts = token.split(".")
        self.assertEqual(len(parts), 3, "JWT must consist of header, payload, and signature")

    def test_jwt_missing_config_raises(self):
        """Raises ValueError when GITHUB_APP_ID or key is omitted."""
        with patch.dict(os.environ, {"GITHUB_APP_ID": ""}):
            with self.assertRaises(ValueError):
                generate_app_jwt()

    @patch("urllib.request.urlopen")
    def test_get_installation_access_token_success(self, mock_urlopen):
        """Exchanges App JWT for installation token and applies 5m early expiry buffer."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"token": "ghs_test1234567890abcdef", "expires_at": "2030-01-01T12:00:00Z"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        token, ttl = get_installation_access_token(998877)
        self.assertEqual(token, "ghs_test1234567890abcdef")
        self.assertGreater(ttl, 0)

    @patch("urllib.request.urlopen")
    def test_get_installation_access_token_suspended(self, mock_urlopen):
        """Raises helpful ValueError when installation is suspended (403)."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://api.github.com", 403, "Forbidden", {}, None
        )
        with self.assertRaises(ValueError) as ctx:
            get_installation_access_token(998877)
        self.assertIn("suspended", str(ctx.exception).lower())

    def test_sensitive_token_log_redaction(self):
        """SensitiveTokenRedactionFilter masks ghs_*, ghu_*, and Bearer tokens in logs."""
        redactor = SensitiveTokenRedactionFilter()

        # Test string message
        record1 = logging.LogRecord(
            name="test", level=logging.INFO, pathname=__file__, lineno=10,
            msg="Acquired token ghs_secret1234567890 for repo sync", args=(), exc_info=None
        )
        redactor.filter(record1)
        self.assertNotIn("ghs_secret1234567890", record1.msg)
        self.assertIn("[REDACTED_TOKEN]", record1.msg)

        # Test Bearer header in args
        record2 = logging.LogRecord(
            name="test", level=logging.INFO, pathname=__file__, lineno=11,
            msg="Request header: %s", args=("Bearer ghu_myusertoken9988776655",), exc_info=None
        )
        redactor.filter(record2)
        self.assertNotIn("ghu_myusertoken9988776655", record2.args[0])
        self.assertIn("[REDACTED_TOKEN]", record2.args[0])

if __name__ == "__main__":
    unittest.main()
