import os
import unittest
import tempfile
import shutil
import json
import hmac
import hashlib
from unittest.mock import patch, MagicMock

from app.utils.diff_scanner import (
    filter_pr_scan_targets,
    classify_pr_findings,
    determine_pr_verdict
)
from app.utils.config_parser import (
    parse_codevanguard_config,
    CodeVanguardConfig
)
from app.utils.check_run import (
    build_check_run_annotations
)
from app.utils.pr_comment import (
    format_sticky_comment,
    STICKY_COMMENT_MARKER
)
from app.utils.sarif import generate_sarif_report
from app.routers.webhook import verify_github_signature
from app.utils.db import (
    init_db,
    upsert_installation,
    upsert_repository,
    add_installation_member,
    upsert_baseline_findings,
    get_repository_baseline_findings,
    get_repository_findings,
    suppress_finding,
    unsuppress_finding,
    create_scan,
    update_scan_status,
    get_scan,
    record_webhook_delivery,
    get_db_connection
)
from app.scanners.bandit_scanner import BanditScanner
from app.scanners.semgrep_scanner import SemgrepScanner

class TestPRScanningAppSec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ----------------------------------------------------
    # 1. Path Traversal & Symlink Defense in PR Scan Targets
    # ----------------------------------------------------
    def test_path_traversal_targets_blocked(self):
        """Verifies filter_pr_scan_targets strictly rejects paths outside repository root."""
        # Legitimate file inside repo
        safe_file = os.path.join(self.test_dir, "safe.py")
        with open(safe_file, "w") as f:
            f.write("print('safe')")

        # Malicious file outside repo
        outside_dir = tempfile.mkdtemp()
        try:
            outside_file = os.path.join(outside_dir, "secret.py")
            with open(outside_file, "w") as f:
                f.write("SECRET = 'stolen'")

            # Relative path traversal attempts
            traversal_candidates = [
                "../../secret.py",
                "../secret.py",
                "/etc/passwd",
                "subdir/../../safe.py",
                "safe.py"
            ]

            targets = filter_pr_scan_targets(self.test_dir, traversal_candidates)
            
            # Only safe.py must be included
            self.assertEqual(len(targets), 1)
            self.assertEqual(os.path.realpath(targets[0]), os.path.realpath(safe_file))
        finally:
            shutil.rmtree(outside_dir, ignore_errors=True)

    def test_symlinks_rejected_in_scan_targets(self):
        """Verifies symlinks pointing to external files are rejected."""
        outside_dir = tempfile.mkdtemp()
        try:
            target_outside = os.path.join(outside_dir, "target.py")
            with open(target_outside, "w") as f:
                f.write("print('target')")

            symlink_inside = os.path.join(self.test_dir, "link.py")
            os.symlink(target_outside, symlink_inside)

            targets = filter_pr_scan_targets(self.test_dir, ["link.py"])
            self.assertEqual(len(targets), 0)
        finally:
            shutil.rmtree(outside_dir, ignore_errors=True)

    # ----------------------------------------------------
    # 2. Scanner CLI Argument Flag Injection Immunity
    # ----------------------------------------------------
    def test_bandit_scanner_cli_flag_immunity(self):
        """Verifies BanditScanner uses POSIX -- separator before file targets to block flag injection."""
        malicious_filename = "--output=/tmp/evil"
        scanner = BanditScanner(self.test_dir, target_files=[malicious_filename])
        
        with patch("app.scanners.bandit_scanner.execute_scanner_process") as mock_exec:
            mock_exec.return_value = {}
            import asyncio
            asyncio.run(scanner.scan())
            
            mock_exec.assert_called_once()
            args = mock_exec.call_args[0][1]
            # Must contain '--' before the malicious flag
            dash_dash_idx = args.index("--")
            flag_idx = args.index(malicious_filename)
            self.assertGreater(flag_idx, dash_dash_idx)

    def test_semgrep_scanner_cli_flag_immunity(self):
        """Verifies SemgrepScanner uses POSIX -- separator before file targets to block flag injection."""
        malicious_filename = "--config=http://evil.com"
        scanner = SemgrepScanner(self.test_dir, target_files=[malicious_filename])
        
        with patch("app.scanners.semgrep_scanner.execute_scanner_process") as mock_exec:
            mock_exec.return_value = {}
            import asyncio
            asyncio.run(scanner.scan())
            
            mock_exec.assert_called_once()
            args = mock_exec.call_args[0][1]
            dash_dash_idx = args.index("--")
            flag_idx = args.index(malicious_filename)
            self.assertGreater(flag_idx, dash_dash_idx)

    # ----------------------------------------------------
    # 3. Webhook HMAC-SHA256 Signature Verification
    # ----------------------------------------------------
    def test_webhook_signature_verification(self):
        """Verifies constant-time HMAC-SHA256 signature enforcement."""
        secret = "super-secret-key-12345"
        payload = b'{"action": "opened", "pull_request": {"number": 42}}'

        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": secret}):
            valid_sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
            tampered_payload = b'{"action": "opened", "pull_request": {"number": 99}}'

            # Valid signature
            self.assertTrue(verify_github_signature(payload, valid_sig))
            # Tampered body
            self.assertFalse(verify_github_signature(tampered_payload, valid_sig))
            # Invalid format
            self.assertFalse(verify_github_signature(payload, "invalid_sig_without_prefix"))
            # Missing header
            self.assertFalse(verify_github_signature(payload, None))

    def test_webhook_rejects_when_secret_unset(self):
        """Verifies webhook signature rejects all requests if secret is missing."""
        with patch.dict(os.environ, {}, clear=True):
            if "GITHUB_WEBHOOK_SECRET" in os.environ:
                del os.environ["GITHUB_WEBHOOK_SECRET"]
            self.assertFalse(verify_github_signature(b'{}', "sha256=abcdef"))

    # ----------------------------------------------------
    # 4. Webhook Replay Attack Prevention (Database Fallback)
    # ----------------------------------------------------
    def test_webhook_replay_prevention_in_db(self):
        """Verifies webhook_deliveries ignores duplicate delivery IDs to preserve replay audit records."""
        delivery_id = "test-replay-uuid-001"
        record_webhook_delivery(delivery_id, "pull_request", "opened", status="processed")
        
        # Second attempt with same delivery_id must not overwrite or error
        record_webhook_delivery(delivery_id, "pull_request", "reopened", status="received")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, action FROM webhook_deliveries WHERE id = ?", (delivery_id,))
            row = cursor.fetchone()
            self.assertEqual(row["status"], "processed")
            self.assertEqual(row["action"], "opened")

    # ----------------------------------------------------
    # 5. Worker Superseded Scan Race Condition Defense
    # ----------------------------------------------------
    def test_worker_superseded_scan_cannot_transition_to_running(self):
        """Verifies update_scan_status fails atomically if scan is already failed or cancelled."""
        import uuid
        scan_id = uuid.uuid4().hex
        create_scan(scan_id=scan_id, filename="test", file_size=100)
        
        # Supersede / cancel it
        update_scan_status(scan_id, "failed", error_message="Superseded by newer commit")
        
        # Worker tries to transition to 'running'
        updated = update_scan_status(scan_id, "running")
        self.assertFalse(updated)

        # Status must remain failed
        s = get_scan(scan_id)
        self.assertEqual(s["status"], "failed")

    # ----------------------------------------------------
    # 6. Default Branch Baseline Integrity
    # ----------------------------------------------------
    def test_baseline_finding_lifecycle_and_fixed_state(self):
        """Verifies baseline tracking marks removed findings as 'fixed' and re-opens reintroduced ones."""
        import random, uuid
        inst_id = random.randint(50000, 99999)
        repo_gh_id = random.randint(100000, 999999)
        inst = upsert_installation(inst_id, f"test-org-{inst_id}", "Organization")
        repo = upsert_repository(inst["id"], repo_gh_id, f"test-org-{inst_id}/baseline-test", "main")
        repo_id = repo["id"]

        # Commit 1 has finding A and finding B
        c1_issues = [
            {"rule_id": "CV-01", "filepath": "app.py", "severity": "high", "fingerprint": f"fp-aaa-{inst_id}"},
            {"rule_id": "CV-02", "filepath": "utils.py", "severity": "medium", "fingerprint": f"fp-bbb-{inst_id}"}
        ]
        s1 = uuid.uuid4().hex
        upsert_baseline_findings(repo_id, s1, "sha-c1", c1_issues)
        
        baseline = get_repository_baseline_findings(repo_id)
        self.assertIn(f"fp-aaa-{inst_id}", baseline)
        self.assertIn(f"fp-bbb-{inst_id}", baseline)
        self.assertEqual(baseline[f"fp-aaa-{inst_id}"]["state"], "open")

        # Commit 2 fixes finding A (only finding B remains)
        c2_issues = [
            {"rule_id": "CV-02", "filepath": "utils.py", "severity": "medium", "fingerprint": f"fp-bbb-{inst_id}"}
        ]
        s2 = uuid.uuid4().hex
        upsert_baseline_findings(repo_id, s2, "sha-c2", c2_issues)

        # Active baseline should only return fp-bbb
        active_baseline = get_repository_baseline_findings(repo_id)
        self.assertNotIn(f"fp-aaa-{inst_id}", active_baseline)
        self.assertIn(f"fp-bbb-{inst_id}", active_baseline)

        # Verify in findings table that fp-aaa is marked 'fixed'
        findings, total = get_repository_findings(repo_id, state="fixed")
        fixed_fps = [f["fingerprint"] for f in findings]
        self.assertIn(f"fp-aaa-{inst_id}", fixed_fps)

        # Commit 3 re-introduces finding A
        s3 = uuid.uuid4().hex
        upsert_baseline_findings(repo_id, s3, "sha-c3", c1_issues)
        reopened_baseline = get_repository_baseline_findings(repo_id)
        self.assertIn(f"fp-aaa-{inst_id}", reopened_baseline)
        self.assertEqual(reopened_baseline[f"fp-aaa-{inst_id}"]["state"], "open")

    # ----------------------------------------------------
    # 7. Diff Classification & Verdict Logic
    # ----------------------------------------------------
    def test_diff_classification_and_verdict(self):
        """Tests classification of new, existing, and fixed findings against baseline."""
        baseline_map = {
            "fp-exist": {"id": "find-1", "filepath": "main.py", "severity": "medium"}
        }

        pr_issues = [
            {"rule_id": "CV-NEW", "filepath": "new.py", "severity": "critical", "fingerprint": "fp-new"},
            {"rule_id": "CV-OLD", "filepath": "main.py", "severity": "medium", "fingerprint": "fp-exist"}
        ]

        new_f, exist_f, fixed_f = classify_pr_findings(
            current_issues=pr_issues,
            baseline_findings=baseline_map,
            changed_files=["new.py", "main.py"]
        )

        self.assertEqual(len(new_f), 1)
        self.assertEqual(new_f[0]["fingerprint"], "fp-new")
        self.assertTrue(new_f[0]["is_new"])

        self.assertEqual(len(exist_f), 1)
        self.assertEqual(exist_f[0]["fingerprint"], "fp-exist")
        self.assertFalse(exist_f[0]["is_new"])

        # Verdict calculation
        # Critical finding exceeds high threshold -> BLOCK
        self.assertEqual(determine_pr_verdict(new_f, fail_on="high"), "BLOCK")
        # Fail on none -> never blocks (REVIEW)
        self.assertEqual(determine_pr_verdict(new_f, fail_on="none"), "REVIEW")
        # Zero new findings -> SAFE
        self.assertEqual(determine_pr_verdict([], fail_on="critical"), "SAFE")

    # ----------------------------------------------------
    # 8. SARIF 2.1.0 Specification Compliance
    # ----------------------------------------------------
    def test_sarif_generation_schema_compliance(self):
        """Verifies SARIF output conforms to 2.1.0 format with partialFingerprints."""
        scan_meta = {"id": "scan-123"}
        issues = [
            {
                "rule_id": "B101",
                "severity": "critical",
                "message": "Use of assert detected",
                "filepath": "app/auth.py",
                "line_number": 42,
                "col_number": 5,
                "fingerprint": "sha256-dummy-fingerprint"
            }
        ]

        sarif = generate_sarif_report(scan_meta, issues)
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertIn("sarif-schema-2.1.0.json", sarif["$schema"])
        
        runs = sarif["runs"]
        self.assertEqual(len(runs), 1)
        results = runs[0]["results"]
        self.assertEqual(len(results), 1)
        
        res = results[0]
        self.assertEqual(res["level"], "error")  # critical -> error
        self.assertEqual(res["partialFingerprints"]["codevanguard/v1"], "sha256-dummy-fingerprint")

    # ----------------------------------------------------
    # 9. Sticky PR Comment Marker & Idempotency
    # ----------------------------------------------------
    def test_sticky_pr_comment_formatting(self):
        """Verifies sticky comment has hidden HTML marker to guarantee update-in-place."""
        body = format_sticky_comment(
            verdict="BLOCK",
            new_findings=[{"severity": "critical", "rule_id": "CV-TEST", "filepath": "auth.py", "line_number": 10}],
            fixed_count=2,
            existing_count=5,
            dashboard_url="https://app.codevanguard.com/repos/1/pulls/10"
        )

        self.assertTrue(body.startswith(STICKY_COMMENT_MARKER))
        self.assertIn("⛔ **BLOCK**", body)
        self.assertIn("auth.py:10", body)

    # ----------------------------------------------------
    # 10. Repository Config (.codevanguard.yml) Security Limits
    # ----------------------------------------------------
    def test_config_parser_oversized_file_rejected(self):
        """Verifies .codevanguard.yml larger than 256KB is safely ignored."""
        huge_file = os.path.join(self.test_dir, ".codevanguard.yml")
        with open(huge_file, "w") as f:
            f.write("# padding\n" * 30000) # > 256 KB

        config = parse_codevanguard_config(self.test_dir)
        # Should retain safe defaults
        self.assertEqual(config.fail_on, "high")
        self.assertTrue(config.enabled)

    # ----------------------------------------------------
    # 11. Finding Suppression & Audit Logging
    # ----------------------------------------------------
    def test_finding_suppression_audit_trail(self):
        """Verifies finding suppression requires reason and updates state with audit trail."""
        import random, uuid
        inst_id = random.randint(100000, 199999)
        repo_gh_id = random.randint(200000, 299999)
        inst = upsert_installation(inst_id, f"audit-org-{inst_id}", "Organization")
        repo = upsert_repository(inst["id"], repo_gh_id, f"audit-org-{inst_id}/repo", "main")
        
        # Insert a baseline finding
        scan_id = uuid.uuid4().hex
        fp = f"audit-fp-{inst_id}"
        upsert_baseline_findings(repo["id"], scan_id, "sha-audit", [
            {"rule_id": "RULE-1", "filepath": "src/test.py", "severity": "high", "fingerprint": fp}
        ])

        findings, _ = get_repository_findings(repo["id"])
        finding_id = findings[0]["id"]

        # Suppress
        res = suppress_finding(repo["id"], finding_id, user_id=1, state="false_positive", reason="False positive in test suite.")
        self.assertEqual(res["status"], "success")

        # Verify state
        suppressed, _ = get_repository_findings(repo["id"], state="false_positive")
        self.assertEqual(len(suppressed), 1)
        self.assertEqual(suppressed[0]["reason"], "False positive in test suite.")

        # Unsuppress
        un_res = unsuppress_finding(repo["id"], finding_id, user_id=1)
        self.assertEqual(un_res["status"], "success")
        restored, _ = get_repository_findings(repo["id"], state="open")
        self.assertEqual(len(restored), 1)

if __name__ == "__main__":
    unittest.main()
