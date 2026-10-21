import unittest
import asyncio
import uuid
from app.utils.db import (
    init_db, upsert_installation, upsert_repository,
    save_fix_attempt, get_repo_daily_fix_count
)
from app.services.autofix.pipeline import run_autofix_pipeline

class TestAutofixQuotas(unittest.TestCase):
    """
    Validates per-repository Auto-Fix opt-in toggles and daily quota enforcement.
    """

    def setUp(self):
        init_db()
        self.inst = upsert_installation(1234567, "test-org", "Organization")
        self.repo = upsert_repository(
            self.inst["id"], 9876543, "test-org/secure-app", "main", False
        )

    def test_autofix_disabled_by_default(self):
        """Auto-fix must be strictly opt-in; running without opt-in raises ValueError."""
        finding = {
            "id": "find-01",
            "fingerprint": "fp-12345678",
            "rule_id": "B608:sql_injection",
            "filepath": "app/main.py",
            "line_number": 1
        }
        repo_data = dict(self.repo)
        repo_data["autofix_enabled"] = False

        with self.assertRaises(ValueError) as ctx:
            asyncio.run(run_autofix_pipeline(repo_data, finding, "def foo(): pass"))
        self.assertIn("Auto-fix is disabled for this repository", str(ctx.exception))

    def test_daily_quota_calculation_and_exhaustion(self):
        """When daily quota is exceeded, attempts must be blocked."""
        repo_id = uuid.uuid4().hex
        repo_data = {
            "id": repo_id,
            "full_name": f"test-org/repo-{repo_id[:6]}",
            "autofix_enabled": True,
            "autofix_daily_quota": 3
        }

        # Record 3 attempts for today
        for i in range(3):
            save_fix_attempt(
                attempt_id=uuid.uuid4().hex,
                finding_id=f"find-{i}",
                repo_id=repo_id,
                status="verified",
                provider="gemini",
                model="gemini-2.5-flash",
                target_file="app/main.py"
            )

        used_today = get_repo_daily_fix_count(repo_id)
        self.assertEqual(used_today, 3)

        # Attempt 4 must be blocked
        finding = {
            "id": "find-04",
            "fingerprint": "fp-12345678",
            "rule_id": "B608:sql_injection",
            "filepath": "app/main.py",
            "line_number": 1
        }
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(run_autofix_pipeline(repo_data, finding, "def foo(): pass"))
        self.assertIn("Daily auto-fix quota exceeded", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
