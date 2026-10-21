"""
Tests for Anti-Hallucination Narrative Validation & Deterministic Template Fallbacks.
"""
import unittest
from app.services.pr_summary.models import (
    PRSummaryFacts, PRDetails, FindingSummaryItem, FindingsGroup,
    DependencyChange, PushDelta, ActionItem
)
from app.services.pr_summary.narrative import (
    validate_narrative, extract_valid_integers_from_facts,
    build_template_narrative, generate_pr_narrative
)

class TestPRSummaryNarrative(unittest.TestCase):

    def setUp(self):
        self.pr_details = PRDetails(
            number=42,
            head_sha="abcdef1234567890abcdef1234567890abcdef12",
            base_sha="1234567890abcdef1234567890abcdef12345678",
            title="Update payment processor",
            author="dev_lead",
            files_changed=3,
            additions=15,
            deletions=4
        )
        self.findings = FindingsGroup(
            new=[
                FindingSummaryItem(
                    finding_id="find_001",
                    fingerprint="fp_001",
                    severity="high",
                    rule_id="B608:sql_injection",
                    message="SQL injection in query",
                    file="app/db.py",
                    line=105
                ),
                FindingSummaryItem(
                    finding_id="find_002",
                    fingerprint="fp_002",
                    severity="medium",
                    rule_id="B101:assert_used",
                    message="Assert statement used",
                    file="app/utils.py",
                    line=210
                )
            ],
            fixed=[],
            existing_touched=[],
            hidden_existing_count=0
        )
        self.facts = PRSummaryFacts(
            version=1,
            pr=self.pr_details,
            categories_touched=["db"],
            findings=self.findings,
            dependency_changes=[],
            delta_since_previous_push=PushDelta(new_count=2, fixed_count=0, delta_new=0, delta_fixed=0),
            verdict="block",
            reasons=["2 new finding(s) meet or exceed the repository block threshold ('high')."],
            actions=[
                ActionItem(
                    priority=3,
                    category="high_finding",
                    title="[HIGH] Remediate B608 in app/db.py:105",
                    description="SQL injection in query",
                    finding_id="find_001",
                    fingerprint="fp_001",
                    file="app/db.py",
                    line=105
                )
            ],
            omitted_actions_count=0
        )

    def test_extract_valid_integers(self):
        valid_ints = extract_valid_integers_from_facts(self.facts)
        # Should contain PR number 42, files_changed 3, line numbers 105 and 210, additions 15, deletions 4, new count 2
        self.assertIn(42, valid_ints)
        self.assertIn(3, valid_ints)
        self.assertIn(105, valid_ints)
        self.assertIn(210, valid_ints)
        self.assertIn(15, valid_ints)
        self.assertIn(2, valid_ints)

    def test_hallucinated_integer_rejected(self):
        """Any integer not in the facts whitelist must be rejected."""
        hallucinated_text = "Pull request #42 introduces 99 critical vulnerabilities across 3 files."
        is_valid, error = validate_narrative(self.facts, hallucinated_text, ["find_001"])
        self.assertFalse(is_valid)
        self.assertIn("Hallucinated integer detected: '99'", error)

    def test_hallucinated_line_number_rejected(self):
        """A line number not in findings must be rejected."""
        hallucinated_text = "Pull request #42 has an issue at line 888."
        is_valid, error = validate_narrative(self.facts, hallucinated_text, ["find_001"])
        self.assertFalse(is_valid)
        self.assertIn("Hallucinated integer detected: '888'", error)

    def test_legitimate_integers_accepted(self):
        """Narrative with valid integers from facts is accepted."""
        valid_text = "Pull request #42 introduces 2 new finding(s) including 1 High severity issue at line 105 across 3 files."
        is_valid, error = validate_narrative(self.facts, valid_text, ["find_001"])
        self.assertTrue(is_valid, f"Expected valid, got error: {error}")
        self.assertIsNone(error)

    def test_hallucinated_finding_id_rejected(self):
        """Referencing a non-existent finding ID must be rejected."""
        text = "Pull request #42 introduces 2 new findings across 3 files."
        is_valid, error = validate_narrative(self.facts, text, ["invented_finding_id_999"])
        self.assertFalse(is_valid)
        self.assertIn("Hallucinated finding ID detected", error)

    def test_verdict_contradiction_rejected(self):
        """Claiming a blocked PR is safe or ready to merge must be rejected."""
        contradictory_text = "Pull request #42 has all checks passed and is ready to merge."
        is_valid, error = validate_narrative(self.facts, contradictory_text, [])
        self.assertFalse(is_valid)
        self.assertIn("Verdict contradiction", error)

    def test_deterministic_template_fallback(self):
        """When narrative_enabled is False, template fallback produces accurate text with zero hallucination."""
        res = generate_pr_narrative(self.facts, narrative_enabled=False)
        self.assertEqual(res["source"], "template")
        self.assertIn("Pull request #42 introduces 2 new finding(s)", res["text"])
        self.assertIn("Remediation is required prior to merge", res["text"])

    def test_safe_verdict_template(self):
        """Safe verdict template outputs clean message."""
        safe_facts = PRSummaryFacts(
            version=1,
            pr=self.pr_details,
            categories_touched=[],
            findings=FindingsGroup(new=[], fixed=[], existing_touched=[], hidden_existing_count=0),
            dependency_changes=[],
            delta_since_previous_push=PushDelta(new_count=0, fixed_count=0, delta_new=0, delta_fixed=0),
            verdict="safe",
            reasons=["Zero new security findings introduced."],
            actions=[],
            omitted_actions_count=0
        )
        res = generate_pr_narrative(safe_facts, narrative_enabled=False)
        self.assertEqual(res["source"], "template")
        self.assertIn("introduces zero new security findings", res["text"])
        self.assertIn("passed without blocking issues", res["text"])

if __name__ == "__main__":
    unittest.main()
