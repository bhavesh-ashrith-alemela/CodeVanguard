"""
Tests for PR Summary API Endpoints, Tenancy IDOR Defense, and Database Idempotency.
"""
import unittest
import asyncio
import uuid
from unittest.mock import MagicMock

from app.utils.db import (
    init_db, upsert_github_user, create_session, upsert_installation,
    add_installation_member, upsert_repository, create_scan,
    save_pr_summary, get_latest_pr_summary, get_pr_summaries_history
)
from app.utils.auth import HTTPException
from app.routers.pulls import get_pull_request_summary, get_pull_request_details

def run_async(coro):
    return asyncio.run(coro)

class TestPRSummaryAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

        # Create User A and User B
        cls.user_a = upsert_github_user(
            github_id=8801, github_login="dev_a", avatar_url="https://avatar/a"
        )
        cls.user_b = upsert_github_user(
            github_id=8802, github_login="dev_b", avatar_url="https://avatar/b"
        )

        # Installation A
        cls.inst_a = upsert_installation(77001, "team-alpha", "Organization")
        add_installation_member(cls.inst_a["id"], cls.user_a["id"], role="admin")

        # Installation B
        cls.inst_b = upsert_installation(77002, "team-beta", "Organization")
        add_installation_member(cls.inst_b["id"], cls.user_b["id"], role="admin")

        # Repository A
        cls.repo_a = upsert_repository(
            cls.inst_a["id"], 66001, "team-alpha/core-api", "main", is_private=True
        )

        # Scans for PR #10 in Repo A
        cls.scan_1 = f"scan_pr10_commit1_{uuid.uuid4().hex[:8]}"
        create_scan(
            scan_id=cls.scan_1,
            filename="PR #10 Head 1",
            file_size=100,
            source_type="github_app",
            source_url="https://github.com/team-alpha/core-api",
            branch="feature-x",
            commit_sha="commit_sha_11111",
            repo_id=cls.repo_a["id"],
            trigger="pr",
            pr_number=10
        )

        cls.scan_2 = f"scan_pr10_commit2_{uuid.uuid4().hex[:8]}"
        create_scan(
            scan_id=cls.scan_2,
            filename="PR #10 Head 2",
            file_size=120,
            source_type="github_app",
            source_url="https://github.com/team-alpha/core-api",
            branch="feature-x",
            commit_sha="commit_sha_22222",
            repo_id=cls.repo_a["id"],
            trigger="pr",
            pr_number=10
        )

        # Save summary for commit 1
        save_pr_summary(
            repo_id=cls.repo_a["id"],
            pr_number=10,
            scan_id=cls.scan_1,
            head_sha="commit_sha_11111",
            facts={"verdict": "block", "reasons": ["High finding detected"], "findings": {"new": [{}], "fixed": []}},
            narrative="PR #10 commit 1 has issues.",
            narrative_source="template"
        )

        # Save summary for commit 2
        save_pr_summary(
            repo_id=cls.repo_a["id"],
            pr_number=10,
            scan_id=cls.scan_2,
            head_sha="commit_sha_22222",
            facts={"verdict": "safe", "reasons": ["Zero new findings"], "findings": {"new": [], "fixed": [{}]}},
            narrative="PR #10 commit 2 is clean.",
            narrative_source="template"
        )

    def test_authorized_user_can_get_latest_summary(self):
        """User A (member of installation) can retrieve latest PR summary."""
        mock_req = MagicMock()
        res = run_async(get_pull_request_summary(
            repo_id=self.repo_a["id"],
            pr_number=10,
            request=mock_req,
            history=False,
            user=self.user_a
        ))
        self.assertIsNotNone(res)
        self.assertEqual(res["pr_number"], 10)
        self.assertEqual(res["head_sha"], "commit_sha_22222")
        self.assertEqual(res["facts"]["verdict"], "safe")

    def test_authorized_user_can_get_summary_history(self):
        """User A can retrieve full historical sequence of PR summaries."""
        mock_req = MagicMock()
        res = run_async(get_pull_request_summary(
            repo_id=self.repo_a["id"],
            pr_number=10,
            request=mock_req,
            history=True,
            user=self.user_a
        ))
        self.assertIn("summaries", res)
        self.assertEqual(len(res["summaries"]), 2)
        shas = [s["head_sha"] for s in res["summaries"]]
        self.assertIn("commit_sha_11111", shas)
        self.assertIn("commit_sha_22222", shas)

    def test_idor_unauthorized_user_blocked(self):
        """User B (different installation) is strictly blocked with 403 Forbidden."""
        mock_req = MagicMock()
        with self.assertRaises(HTTPException) as ctx:
            run_async(get_pull_request_summary(
                repo_id=self.repo_a["id"],
                pr_number=10,
                request=mock_req,
                history=False,
                user=self.user_b
            ))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Access denied", ctx.exception.detail)

    def test_pr_details_includes_summary(self):
        """GET /api/repos/{repo_id}/pulls/{pr_number} includes latest summary."""
        mock_req = MagicMock()
        res = run_async(get_pull_request_details(
            repo_id=self.repo_a["id"],
            pr_number=10,
            request=mock_req,
            user=self.user_a
        ))
        self.assertIn("summary", res)
        self.assertIsNotNone(res["summary"])
        self.assertEqual(res["summary"]["head_sha"], "commit_sha_22222")

    def test_db_idempotency_upsert(self):
        """Saving PR summary with identical (repo_id, pr_number, head_sha) updates in-place without duplicate error."""
        res1 = save_pr_summary(
            repo_id=self.repo_a["id"],
            pr_number=99,
            scan_id=self.scan_1,
            head_sha="idempotent_sha_abc",
            facts={"verdict": "block", "counter": 1},
            narrative="Initial scan summary"
        )
        self.assertEqual(res1["facts"]["counter"], 1)

        # Second save on same commit SHA
        res2 = save_pr_summary(
            repo_id=self.repo_a["id"],
            pr_number=99,
            scan_id=self.scan_1,
            head_sha="idempotent_sha_abc",
            facts={"verdict": "safe", "counter": 2},
            narrative="Updated scan summary in-place"
        )
        self.assertEqual(res2["facts"]["counter"], 2)

        latest = get_latest_pr_summary(self.repo_a["id"], 99)
        self.assertEqual(latest["facts"]["counter"], 2)
        self.assertEqual(latest["narrative"], "Updated scan summary in-place")

if __name__ == "__main__":
    unittest.main()
