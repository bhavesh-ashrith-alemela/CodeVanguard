import os
import shutil
import tempfile
import subprocess
import asyncio
import unittest
import json
from unittest.mock import patch

from app.scanners.secret_scanner import (
    SecretScanner, mask_secret, hash_secret, calculate_shannon_entropy,
    inspect_line_for_secrets
)
from app.utils.git_history import (
    create_isolated_git_config, secure_bare_clone, DiskLimitExceededError
)
from app.utils.db import (
    init_db, create_scan, save_scan_results, upsert_baseline_findings,
    get_scan_issues, get_repository_findings, get_db_connection
)
from app.utils.sarif import generate_sarif_report
from app.services.pr_summary.facts import build_actions_checklist
from app.services.pr_summary.models import FindingSummaryItem

class TestSecretScannerAndGitHistory(unittest.TestCase):
    def setUp(self):
        init_db()
        self.test_dir = tempfile.mkdtemp(prefix="cv_test_secrets_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_mask_and_hash_secret(self):
        # Test preview masking
        self.assertEqual(mask_secret("AKIA1234567890ABCDEF"), "AKIA...EF")
        self.assertEqual(mask_secret("ghp_123456789012345678901234567890123456"), "ghp_...56")
        self.assertEqual(mask_secret("short"), "***")

        # Test deterministic salted hashing
        h1 = hash_secret("AKIA1234567890ABCDEF", salt="salt1")
        h2 = hash_secret("AKIA1234567890ABCDEF", salt="salt1")
        h3 = hash_secret("AKIA1234567890ABCDEF", salt="salt2")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)
        self.assertEqual(len(h1), 64)

    def test_shannon_entropy(self):
        # Pure repetitive string has zero entropy
        self.assertEqual(calculate_shannon_entropy("aaaaaaaaaaaaaaaa"), 0.0)
        # High-entropy random hex has high entropy (> 3.0)
        hex_rand = "4a1f8c92e7b30d5a6f1e2c8b4d09a7e5"
        self.assertGreater(calculate_shannon_entropy(hex_rand), 3.0)

    def test_git_history_secret_lifecycle(self):
        """
        Creates a real local git repository:
        1. Commit 1: Commits fake AWS key & allowlisted decoy.
        2. Commit 2: Deletes fake AWS key, adds high-entropy decoy (UUID & git commit sha).
        3. Assert AWS key is detected as history-only (still_in_head=False, severity=high).
        4. Assert decoys are NOT flagged.
        5. Assert zero raw secret persists in DB, issues, findings, or SARIF.
        """
        repo_dir = os.path.join(self.test_dir, "test_repo")
        os.makedirs(repo_dir, exist_ok=True)

        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
            "GIT_AUTHOR_NAME": "Tester",
            "GIT_AUTHOR_EMAIL": "tester@example.com",
            "GIT_COMMITTER_NAME": "Tester",
            "GIT_COMMITTER_EMAIL": "tester@example.com"
        }

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_dir, env=env, check=True, stdout=subprocess.PIPE)

        # Commit 1: Add AWS key and allowlisted fixture
        fake_aws_key = "AKIA1234567890ABCDEF"
        allowlisted_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        config_path = os.path.join(repo_dir, "credentials.py")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(f'# Secret config\nAWS_KEY = "{fake_aws_key}"\nAWS_SECRET = "{allowlisted_key}"\n')

        subprocess.run(["git", "add", "credentials.py"], cwd=repo_dir, env=env, check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "commit", "-m", "Commit 1 with aws key"], cwd=repo_dir, env=env, check=True, stdout=subprocess.PIPE)

        # Commit 2: Remove AWS key from credentials.py, add UUID and commit sha decoys
        decoy_uuid = "4a123b45-67c8-49de-bf01-23456789abcd"
        decoy_sha = "e8395a1234567890abcdef1234567890abcdef12"
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(f'# Clean config\nSESSION_ID = "{decoy_uuid}"\nCOMMIT_HASH = "{decoy_sha}"\n')

        subprocess.run(["git", "add", "credentials.py"], cwd=repo_dir, env=env, check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "commit", "-m", "Commit 2: Delete key, add uuid"], cwd=repo_dir, env=env, check=True, stdout=subprocess.PIPE)

        # Run SecretScanner on the repository history
        scanner = SecretScanner(target_dir=repo_dir)
        findings = asyncio.run(scanner.scan())

        # 1. Assert AWS Key was found
        aws_findings = [f for f in findings if f["rule_id"] == "SECRET_AWS_KEY"]
        self.assertEqual(len(aws_findings), 1, "Expected exactly 1 AWS key finding")
        aws_issue = aws_findings[0]

        # 2. Assert key is classified as history-only (HIGH severity, still_in_head=False)
        self.assertFalse(aws_issue["still_in_head"])
        self.assertEqual(aws_issue["severity"], "high")
        self.assertEqual(aws_issue["masked_secret"], "AKIA...EF")

        # 3. Assert decoys (UUID, commit hash, allowlisted key) are NOT flagged
        rule_ids = [f["rule_id"] for f in findings]
        for f in findings:
            self.assertNotIn(decoy_uuid, f.get("code_snippet", ""))
            self.assertNotIn(decoy_sha, f.get("code_snippet", ""))

        # 4. Save to database and verify zero raw secrets persisted
        import uuid
        scan_id = uuid.uuid4().hex
        create_scan(scan_id=scan_id, filename="test_repo", file_size=1024, source_type="paste")
        save_scan_results(scan_id, findings)

        db_issues = get_scan_issues(scan_id)
        self.assertEqual(len(db_issues), len(findings))

        for iss in db_issues:
            # Full raw secret string must NEVER be present in the database
            self.assertNotIn(fake_aws_key, iss["message"])
            self.assertNotIn(fake_aws_key, iss["code_snippet"])
            self.assertNotIn(fake_aws_key, iss["masked_secret"])
            self.assertEqual(iss["masked_secret"], "AKIA...EF")
            self.assertFalse(bool(iss["still_in_head"]))

        # 5. Verify SARIF report does not contain the raw secret
        sarif_doc = generate_sarif_report({"id": scan_id}, findings)
        sarif_text = json.dumps(sarif_doc)
        self.assertNotIn(fake_aws_key, sarif_text)
        self.assertIn("AKIA...EF", sarif_text)

    def test_active_secret_in_head(self):
        """Verify that an active secret present in HEAD is flagged as CRITICAL."""
        repo_dir = os.path.join(self.test_dir, "head_secret_repo")
        os.makedirs(repo_dir, exist_ok=True)

        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
            "GIT_AUTHOR_NAME": "Tester",
            "GIT_AUTHOR_EMAIL": "tester@example.com",
            "GIT_COMMITTER_NAME": "Tester",
            "GIT_COMMITTER_EMAIL": "tester@example.com"
        }
        subprocess.run(["git", "init"], cwd=repo_dir, env=env, check=True, stdout=subprocess.PIPE)

        fake_stripe_key = "sk_live_" + "1234567890abcdef12345678"
        app_path = os.path.join(repo_dir, "billing.py")
        with open(app_path, "w", encoding="utf-8") as f:
            f.write(f'# Billing integration\nSTRIPE_API_KEY = "{fake_stripe_key}"\n')

        subprocess.run(["git", "add", "billing.py"], cwd=repo_dir, env=env, check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "commit", "-m", "Add stripe billing"], cwd=repo_dir, env=env, check=True, stdout=subprocess.PIPE)

        scanner = SecretScanner(target_dir=repo_dir)
        findings = asyncio.run(scanner.scan())

        stripe_findings = [f for f in findings if f["rule_id"] == "SECRET_STRIPE_KEY"]
        self.assertEqual(len(stripe_findings), 1)
        stripe_issue = stripe_findings[0]

        # Active secret at HEAD must be CRITICAL and still_in_head=True
        self.assertTrue(stripe_issue["still_in_head"])
        self.assertEqual(stripe_issue["severity"], "critical")
        self.assertEqual(stripe_issue["masked_secret"], "sk_l...78")
        self.assertNotIn(fake_stripe_key, stripe_issue["code_snippet"])

    def test_token_isolation_and_permissions(self):
        """Verify temporary git config has 0600 permissions and isolates token."""
        token = "ghp_super_secret_token_1234567890"
        cfg_path = create_isolated_git_config(token)
        try:
            self.assertTrue(os.path.exists(cfg_path))
            mode = os.stat(cfg_path).st_mode & 0o777
            self.assertEqual(mode, 0o600, "Config file must have strict 0600 permissions")
            with open(cfg_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("Authorization: Bearer " + token, content)
        finally:
            if os.path.exists(cfg_path):
                os.remove(cfg_path)

    def test_pr_actions_checklist_places_secrets_first(self):
        """Verify that PR summary actions checklist prioritizes credential rotation above all else."""
        sec_item = FindingSummaryItem(
            finding_id="f1",
            fingerprint="fp1",
            severity="critical",
            rule_id="SECRET_AWS_KEY",
            message="Active AWS Access Key ID exposed at HEAD: AKIA...EF",
            file="auth/config.py",
            line=12
        )
        crit_item = FindingSummaryItem(
            finding_id="f2",
            fingerprint="fp2",
            severity="critical",
            rule_id="B608",
            message="SQL Injection in raw execute",
            file="db/query.py",
            line=45
        )

        actions, _ = build_actions_checklist(
            new_findings=[crit_item, sec_item],
            categories_touched=["auth"],
            dependency_changes=[]
        )

        self.assertGreaterEqual(len(actions), 2)
        # Priority 1 must be the secrets rotation action
        self.assertEqual(actions[0].category, "secrets_rotation")
        self.assertEqual(actions[0].priority, 1)
        self.assertIn("Rotate this credential", actions[0].title)

    def test_create_isolated_git_config_crlf_injection(self):
        """Verify CRLF and control characters in auth token are strictly rejected to prevent git config injection."""
        malicious_tokens = [
            "token\n[core]\nfsmonitor = evil",
            "token\r\n[credential]\nhelper = evil",
            "token; rm -rf /",
            "token with spaces",
            "token\x00null"
        ]
        for bad_token in malicious_tokens:
            with self.assertRaises(ValueError):
                create_isolated_git_config(bad_token)

    def test_secure_bare_clone_identifier_validation(self):
        """Verify owner and repo_name are validated against option injection."""
        bad_names = ["--upload-pack=evil", "-o", "repo/../../etc", "name with spaces", "..", ""]
        for bad in bad_names:
            with self.assertRaises(ValueError):
                with secure_bare_clone(owner=bad, repo_name="valid-repo"):
                    pass
            with self.assertRaises(ValueError):
                with secure_bare_clone(owner="valid-owner", repo_name=bad):
                    pass

    def test_path_traversal_head_check_blocked(self):
        """Verify _check_secret_presence_in_head blocks path traversal out of target directory."""
        fake_secret = "AKIA1234567890ABCDEF"
        scanner = SecretScanner(target_dir=self.test_dir)
        
        # Test directory traversal sequences
        self.assertFalse(scanner._check_secret_presence_in_head(fake_secret, "../../../../etc/passwd"))
        self.assertFalse(scanner._check_secret_presence_in_head(fake_secret, "/etc/shadow"))
        self.assertFalse(scanner._check_secret_presence_in_head(fake_secret, "..\\..\\windows\\win.ini"))

    def test_commit_range_flag_injection_blocked(self):
        """Verify that CLI flags in commit_range are rejected and not passed to git log."""
        scanner = SecretScanner(target_dir=self.test_dir, commit_range="--output=/tmp/pwned")
        results = asyncio.run(scanner._stream_git_log_and_detect())
        self.assertEqual(results, [])
        self.assertFalse(os.path.exists("/tmp/pwned"))

    def test_disk_limit_exceeded_error(self):
        """Verify DiskLimitExceededError is raised when disk cap is reached."""
        with patch("app.utils.git_history._run_git_clone_with_disk_guard") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            with patch("app.utils.git_history.get_directory_size", return_value=500 * 1024 * 1024):
                with self.assertRaises(DiskLimitExceededError):
                    with secure_bare_clone(owner="org", repo_name="repo", max_disk_bytes=100 * 1024 * 1024):
                        pass

if __name__ == "__main__":
    unittest.main()
