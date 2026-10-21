import unittest
import json
from unittest.mock import patch, MagicMock
from app.services.autofix.git_pr import (
    generate_fix_branch_name, format_fix_pr_body, create_fix_pull_request
)

class TestAutofixGitPR(unittest.TestCase):
    """
    Validates GitHub Pull Request creation logic for verified auto-fix patches.
    """

    def test_branch_name_convention(self):
        """Branch names must strictly adhere to cv/fix-<rule>-<fingerprint8>."""
        branch = generate_fix_branch_name(
            rule_id="B608:hardcoded_sql_expressions",
            fingerprint="a1b2c3d4e5f678901234567890abcdef"
        )
        self.assertEqual(branch, "cv/fix-hardcoded_sql_expres-a1b2c3d4")
        self.assertTrue(branch.startswith("cv/fix-"))
        self.assertNotIn(":", branch)

    def test_format_fix_pr_body_evidence_table(self):
        """PR body must contain verification table, disclaimer, and scanner details."""
        body = format_fix_pr_body(
            rule_id="B608",
            severity="critical",
            filepath="app/db.py",
            start_line=10,
            end_line=20,
            explanation="Parameterized query prevents SQL injection.",
            scanners_run=["bandit", "semgrep"],
            original_fingerprint="fp123456789"
        )

        self.assertIn("## 🛡️ CodeVanguard Automated Security Fix", body)
        self.assertIn("AI-generated security patch verified by static analysis", body)
        self.assertIn("| **Syntax Compilation** | PASSED |", body)
        self.assertIn("| **Vulnerability Resolution** | RESOLVED |", body)
        self.assertIn("| **Regression Analysis** | ZERO REGRESSIONS |", body)
        self.assertIn("Bandit, Semgrep", body)
        self.assertIn("Source code was never persisted to database", body)

    @patch("app.services.autofix.git_pr.get_safe_opener")
    def test_create_fix_pull_request_workflow(self, mock_get_opener):
        """Verifies end-to-end GitHub Contents & Pulls API sequence."""
        mock_opener = MagicMock()
        mock_get_opener.return_value = mock_opener

        def make_mock_resp(data: dict):
            m = MagicMock()
            m.__enter__.return_value = m
            m.__exit__.return_value = None
            m.read.return_value = json.dumps(data).encode("utf-8")
            return m

        ref_resp = make_mock_resp({"object": {"sha": "basesha1234567890"}})
        branch_resp = make_mock_resp({"ref": "refs/heads/cv/fix-rule1-fp123456"})
        file_resp = make_mock_resp({"sha": "filesha99999"})
        commit_resp = make_mock_resp({"content": {"name": "test.py"}})
        pr_resp = make_mock_resp({
            "number": 42,
            "html_url": "https://github.com/test-org/test-repo/pull/42"
        })
        labels_resp = make_mock_resp([])

        mock_opener.open.side_effect = [
            ref_resp,
            branch_resp,
            file_resp,
            commit_resp,
            pr_resp,
            labels_resp
        ]

        result = create_fix_pull_request(
            owner="test-org",
            repo="test-repo",
            default_branch="main",
            filepath="app/test.py",
            patched_file_content="def fixed(): pass\n",
            rule_id="B608",
            severity="critical",
            start_line=1,
            end_line=2,
            explanation="Fixed SQLi",
            original_fingerprint="fp123456789",
            scanners_run=["bandit"],
            auth_token="ghs_mocktoken"
        )

        self.assertEqual(result["pr_number"], 42)
        self.assertEqual(result["pr_url"], "https://github.com/test-org/test-repo/pull/42")
        self.assertTrue(result["branch_name"].startswith("cv/fix-"))

if __name__ == "__main__":
    unittest.main()
