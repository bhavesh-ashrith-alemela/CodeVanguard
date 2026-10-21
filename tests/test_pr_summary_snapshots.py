"""
Golden Snapshot Tests for PR Security Summaries.
Tests 5 distinct scenarios:
1. Clean PR (0 findings, safe)
2. 3 new findings (critical, high, medium - block)
3. PR that fixes baseline findings (safe)
4. Dependency-only PR (audit action generated)
5. 500 findings (massive scale: strictly caps comment <= 60k chars and check summary <= 65k chars)
"""
import unittest
from app.services.pr_summary.models import (
    PRSummaryFacts, PRDetails, FindingSummaryItem, FindingsGroup,
    DependencyChange, PushDelta, ActionItem
)
from app.services.pr_summary.facts import build_pr_summary_facts
from app.services.pr_summary.renderers import (
    to_markdown_comment, to_check_summary, to_json,
    STICKY_COMMENT_MARKER, MAX_PR_COMMENT_LENGTH, MAX_CHECK_SUMMARY_LENGTH
)

class TestPRSummarySnapshots(unittest.TestCase):

    def test_scenario_1_clean_pr(self):
        """Case 1: Clean PR with zero findings -> Safe verdict."""
        pr_meta = {
            "number": 101,
            "title": "Refactor auth helper functions",
            "author": "alice",
            "head_sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "base_sha": "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
            "files_changed": 2,
            "additions": 45,
            "deletions": 12
        }
        changed_files = ["app/utils/auth.py", "tests/test_auth.py"]
        file_diffs = []
        raw_new = []
        raw_fixed = []
        raw_existing = []

        facts = build_pr_summary_facts(
            pr_dict=pr_meta,
            changed_files=changed_files,
            file_diffs=file_diffs,
            raw_new_findings=raw_new,
            raw_fixed_findings=raw_fixed,
            raw_existing_findings=raw_existing,
            total_baseline_count=5,
            fail_on="high"
        )

        self.assertEqual(facts.verdict, "safe")
        self.assertIn("auth", facts.categories_touched)
        self.assertEqual(len(facts.findings.new), 0)
        self.assertEqual(facts.findings.hidden_existing_count, 5)

        comment = to_markdown_comment(facts, dashboard_url="https://app.codevanguard.io/repos/1/pulls/101")
        self.assertIn(STICKY_COMMENT_MARKER, comment)
        self.assertIn("SAFE", comment)
        self.assertIn("Zero new security findings", comment)
        self.assertLess(len(comment), MAX_PR_COMMENT_LENGTH)

        check_summary = to_check_summary(facts)
        self.assertIn("SAFE", check_summary)
        self.assertLess(len(check_summary), MAX_CHECK_SUMMARY_LENGTH)

    def test_scenario_2_three_new_findings(self):
        """Case 2: 3 new findings (critical, high, medium) -> Block verdict with prioritized actions."""
        pr_meta = {
            "number": 102,
            "title": "Add payment gateway webhook listener",
            "author": "bob",
            "head_sha": "c1c2c3c4c5c6c1c2c3c4c5c6c1c2c3c4c5c6c1c2",
            "base_sha": "d1d2d3d4d5d6d1d2d3d4d5d6d1d2d3d4d5d6d1d2",
            "files_changed": 3,
            "additions": 120,
            "deletions": 5
        }
        changed_files = ["app/billing/webhook.py", "app/billing/config.py", "database/schema.sql"]
        file_diffs = []
        raw_new = [
            {
                "finding_id": "find-1",
                "fingerprint": "fp_crit_1",
                "severity": "critical",
                "rule_id": "B608:hardcoded_sql_expression",
                "message": "Possible SQL injection vector via untrusted query parameters.",
                "filepath": "app/billing/webhook.py",
                "line_number": 42
            },
            {
                "finding_id": "find-2",
                "fingerprint": "fp_secret_2",
                "severity": "high",
                "rule_id": "generic_secret_token",
                "message": "Hardcoded Stripe secret API key detected in source code.",
                "filepath": "app/billing/config.py",
                "line_number": 15
            },
            {
                "finding_id": "find-3",
                "fingerprint": "fp_med_3",
                "severity": "medium",
                "rule_id": "B101:assert_used",
                "message": "Assert used outside test suite.",
                "filepath": "app/billing/webhook.py",
                "line_number": 88
            }
        ]

        facts = build_pr_summary_facts(
            pr_dict=pr_meta,
            changed_files=changed_files,
            file_diffs=file_diffs,
            raw_new_findings=raw_new,
            raw_fixed_findings=[],
            raw_existing_findings=[],
            total_baseline_count=0,
            fail_on="high"
        )

        self.assertEqual(facts.verdict, "block")
        self.assertIn("db", facts.categories_touched)
        self.assertIn("config/secrets", facts.categories_touched)

        # Check action checklist priority: Critical first, Secrets rotate first, High, Medium
        actions = facts.actions
        self.assertGreaterEqual(len(actions), 3)
        # Action item for secret rotation must be present
        secret_actions = [a for a in actions if a.category == "secrets_rotation"]
        self.assertEqual(len(secret_actions), 1)
        self.assertIn("Rotate leaked secret", secret_actions[0].title)

        comment = to_markdown_comment(facts, dashboard_url="https://app.codevanguard.io/repos/1/pulls/102")
        self.assertIn(STICKY_COMMENT_MARKER, comment)
        self.assertIn("BLOCK", comment)
        self.assertIn("Needs Before Merge", comment)
        self.assertLess(len(comment), MAX_PR_COMMENT_LENGTH)

    def test_scenario_3_fixing_pr(self):
        """Case 3: PR that fixes baseline vulnerabilities."""
        pr_meta = {
            "number": 103,
            "title": "Remediate SQL injection in user profile lookup",
            "author": "carol",
            "head_sha": "e1e2e3e4e5e6e1e2e3e4e5e6e1e2e3e4e5e6e1e2",
            "base_sha": "f1f2f3f4f5f6f1f2f3f4f5f6f1f2f3f4f5f6f1f2",
            "files_changed": 1,
            "additions": 10,
            "deletions": 8
        }
        changed_files = ["app/routers/users.py"]
        file_diffs = []
        raw_new = []
        raw_fixed = [
            {
                "finding_id": "find-old-1",
                "fingerprint": "fp_fixed_sql",
                "severity": "critical",
                "rule_id": "B608:hardcoded_sql_expression",
                "message": "SQL injection resolved via parameterized queries.",
                "filepath": "app/routers/users.py",
                "line_number": 55
            }
        ]

        facts = build_pr_summary_facts(
            pr_dict=pr_meta,
            changed_files=changed_files,
            file_diffs=file_diffs,
            raw_new_findings=raw_new,
            raw_fixed_findings=raw_fixed,
            raw_existing_findings=[],
            total_baseline_count=3,
            fail_on="high"
        )

        self.assertEqual(facts.verdict, "safe")
        self.assertEqual(len(facts.findings.fixed), 1)

        comment = to_markdown_comment(facts)
        self.assertIn("- **Fixed Baseline Findings:** -1", comment)
        self.assertIn("Resolved Baseline Findings", comment)
        self.assertLess(len(comment), MAX_PR_COMMENT_LENGTH)

    def test_scenario_4_dependency_only_pr(self):
        """Case 4: Dependency-only PR (e.g. Dependabot package bump)."""
        pr_meta = {
            "number": 104,
            "title": "Bump cryptography from 41.0.0 to 42.0.8",
            "author": "dependabot[bot]",
            "head_sha": "1122334455661122334455661122334455661122",
            "base_sha": "2233445566772233445566772233445566772233",
            "files_changed": 1,
            "additions": 1,
            "deletions": 1
        }
        changed_files = ["requirements.txt"]
        file_diffs = [
            {
                "filename": "requirements.txt",
                "patch": "@@ -1,3 +1,3 @@\n-cryptography==41.0.0\n+cryptography==42.0.8\n requests==2.31.0"
            }
        ]

        facts = build_pr_summary_facts(
            pr_dict=pr_meta,
            changed_files=changed_files,
            file_diffs=file_diffs,
            raw_new_findings=[],
            raw_fixed_findings=[],
            raw_existing_findings=[],
            total_baseline_count=0,
            fail_on="high"
        )

        self.assertEqual(facts.verdict, "safe")
        self.assertIn("dependency manifests", facts.categories_touched)
        self.assertEqual(len(facts.dependency_changes), 1)
        dep = facts.dependency_changes[0]
        self.assertEqual(dep.name, "cryptography")
        self.assertEqual(dep.change_type, "updated")
        self.assertEqual(dep.version, "==42.0.8")
        self.assertEqual(dep.previous_version, "==41.0.0")

        comment = to_markdown_comment(facts)
        self.assertIn("cryptography", comment)
        self.assertIn("Dependency Changes", comment)
        self.assertLess(len(comment), MAX_PR_COMMENT_LENGTH)

    def test_scenario_5_five_hundred_findings_massive_scale_truncation(self):
        """Case 5: 500 findings stress test. Verifies strict length caps (<= 60,000 comment, <= 65,000 check run)."""
        pr_meta = {
            "number": 105,
            "title": "Massive monolithic merge",
            "author": "stress-tester",
            "head_sha": "9988776655449988776655449988776655449988",
            "base_sha": "1122334455661122334455661122334455661122",
            "files_changed": 80,
            "additions": 15000,
            "deletions": 3000
        }
        changed_files = [f"src/module_{i}.py" for i in range(80)]
        raw_new = []
        for i in range(500):
            raw_new.append({
                "finding_id": f"fid_{i}",
                "fingerprint": f"fp_stress_{i}",
                "severity": "high" if i % 2 == 0 else "medium",
                "rule_id": f"SECURITY_RULE_{i:04d}",
                "message": f"Security finding description #{i} with detailed context and explanation of vulnerability implications.",
                "filepath": f"src/module_{i % 80}.py",
                "line_number": (i * 7) % 500 + 1
            })

        facts = build_pr_summary_facts(
            pr_dict=pr_meta,
            changed_files=changed_files,
            file_diffs=[],
            raw_new_findings=raw_new,
            raw_fixed_findings=[],
            raw_existing_findings=[],
            total_baseline_count=100,
            fail_on="high"
        )

        self.assertEqual(facts.verdict, "block")
        self.assertEqual(len(facts.findings.new), 500)
        # Actions capped at 10 items
        self.assertEqual(len(facts.actions), 10)
        self.assertEqual(facts.omitted_actions_count, 490)

        comment = to_markdown_comment(facts, dashboard_url="https://app.codevanguard.io/repos/1/pulls/105")
        self.assertLessEqual(len(comment), MAX_PR_COMMENT_LENGTH, f"Comment length {len(comment)} exceeds 60,000 cap!")
        self.assertIn("Truncated", comment)
        self.assertIn(STICKY_COMMENT_MARKER, comment)

        check_summary = to_check_summary(facts, dashboard_url="https://app.codevanguard.io/repos/1/pulls/105")
        self.assertLessEqual(len(check_summary), MAX_CHECK_SUMMARY_LENGTH, f"Check summary length {len(check_summary)} exceeds 65,000 cap!")
        self.assertIn("Truncated", check_summary)

if __name__ == "__main__":
    unittest.main()
