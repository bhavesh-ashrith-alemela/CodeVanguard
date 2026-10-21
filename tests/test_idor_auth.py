import os
import unittest
import asyncio
from unittest.mock import patch, MagicMock

from app.utils.db import (
    init_db, upsert_github_user, create_session, upsert_installation,
    add_installation_member, upsert_repository, create_scan, get_scan_history,
    delete_scan
)
from app.utils.auth import (
    require_repo_access, require_scan_access, get_current_user_optional,
    HTTPException
)
from app.routers.scan import remove_scan_json
from app.routers.repos import trigger_repo_scan

class MockRequest:
    def __init__(self, cookies: dict = None, headers: dict = None):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.client = MagicMock()
        self.client.host = "127.0.0.1"

def run_async(coro):
    return asyncio.run(coro)

class TestIdorAndTenancyAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

        # 1. Create User A and User B
        cls.user_a = upsert_github_user(
            github_id=1001, github_login="alice_dev", avatar_url="https://avatar/alice"
        )
        cls.token_a = create_session(cls.user_a["id"])

        cls.user_b = upsert_github_user(
            github_id=1002, github_login="bob_dev", avatar_url="https://avatar/bob"
        )
        cls.token_b = create_session(cls.user_b["id"])

        cls.admin_user = {
            "id": 9999,
            "username": "sysadmin",
            "role": "admin"
        }
        cls.token_admin = create_session(cls.admin_user["id"])

        # 2. Setup Installations
        cls.inst_a = upsert_installation(11001, "alice-org", "User")
        add_installation_member(cls.inst_a["id"], cls.user_a["id"], role="admin")

        cls.inst_b = upsert_installation(11002, "bob-org", "User")
        add_installation_member(cls.inst_b["id"], cls.user_b["id"], role="admin")

        # 3. Setup Repositories
        cls.repo_a = upsert_repository(
            cls.inst_a["id"], 21001, "alice-org/microservice-a", "main", is_private=True
        )
        cls.repo_b = upsert_repository(
            cls.inst_b["id"], 21002, "bob-org/payment-service", "main", is_private=True
        )

        # 4. Setup Scans with unique IDs
        import uuid
        cls.scan_a_id = f"scan_alice_{uuid.uuid4().hex[:16]}"
        create_scan(
            scan_id=cls.scan_a_id,
            filename="microservice-a@main",
            file_size=5000,
            source_type="github_app",
            repo_id=cls.repo_a["id"],
            owner_user_id=cls.user_a["id"],
            trigger="manual"
        )

        cls.scan_b_id = f"scan_bob_{uuid.uuid4().hex[:16]}"
        create_scan(
            scan_id=cls.scan_b_id,
            filename="payment-service@main",
            file_size=8000,
            source_type="github_app",
            repo_id=cls.repo_b["id"],
            owner_user_id=cls.user_b["id"],
            trigger="push"
        )

        cls.scan_anon_id = f"scan_anon_{uuid.uuid4().hex[:16]}"
        create_scan(
            scan_id=cls.scan_anon_id,
            filename="Pasted Code",
            file_size=1200,
            source_type="paste"
        )

    def test_repo_access_authorization_blocks_cross_tenant(self):
        """User A cannot access User B's repository (403 Forbidden)."""
        # User A accessing their own repo -> OK
        repo = require_repo_access(self.user_a, self.repo_a["id"])
        self.assertEqual(repo["id"], self.repo_a["id"])

        # User A accessing User B's repo -> 403 Forbidden
        with self.assertRaises(HTTPException) as ctx:
            require_repo_access(self.user_a, self.repo_b["id"])
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Access denied", ctx.exception.detail)

        # Admin accessing User B's repo -> OK
        admin_repo = require_repo_access(self.admin_user, self.repo_b["id"])
        self.assertEqual(admin_repo["id"], self.repo_b["id"])

    def test_scan_access_authorization_blocks_idor(self):
        """User A cannot inspect User B's scan reports or findings."""
        req_a = MockRequest(cookies={"session_token": self.token_a})
        req_b = MockRequest(cookies={"session_token": self.token_b})
        req_unauth = MockRequest(cookies={})

        # User A reads Scan A -> OK
        scan_a = require_scan_access(req_a, self.scan_a_id)
        self.assertEqual(scan_a["id"], self.scan_a_id)

        # User A attempts to read Scan B -> 403 Forbidden
        with self.assertRaises(HTTPException) as ctx:
            require_scan_access(req_a, self.scan_b_id)
        self.assertEqual(ctx.exception.status_code, 403)

        # Unauthenticated user attempts to read Scan B -> 401 Unauthorized
        with self.assertRaises(HTTPException) as ctx:
            require_scan_access(req_unauth, self.scan_b_id)
        self.assertEqual(ctx.exception.status_code, 401)

        # Anonymous paste scan can be read by anyone holding the unguessable ID
        anon_scan = require_scan_access(req_unauth, self.scan_anon_id)
        self.assertEqual(anon_scan["id"], self.scan_anon_id)

    def test_user_repository_listing_isolation(self):
        """Each user's repository listing returns only their authorized repos."""
        from app.utils.db import get_user_repositories

        repos_a = get_user_repositories(self.user_a["id"])
        repos_b = get_user_repositories(self.user_b["id"])

        repo_a_ids = [r["id"] for r in repos_a]
        repo_b_ids = [r["id"] for r in repos_b]

        self.assertIn(self.repo_a["id"], repo_a_ids)
        self.assertNotIn(self.repo_b["id"], repo_a_ids)

        self.assertIn(self.repo_b["id"], repo_b_ids)
        self.assertNotIn(self.repo_a["id"], repo_b_ids)

    def test_scan_history_isolation(self):
        """Scan history query filters scans by the user's membership."""
        history_a = get_scan_history(user_id=self.user_a["id"])
        history_b = get_scan_history(user_id=self.user_b["id"])

        history_a_ids = [s["id"] for s in history_a]
        history_b_ids = [s["id"] for s in history_b]

        self.assertIn(self.scan_a_id, history_a_ids)
        self.assertNotIn(self.scan_b_id, history_a_ids)

        self.assertIn(self.scan_b_id, history_b_ids)
        self.assertNotIn(self.scan_a_id, history_b_ids)

    def test_scan_deletion_idor_protection(self):
        """User A cannot delete User B's scans."""
        req_a = MockRequest(
            cookies={"session_token": self.token_a},
            headers={"origin": "http://localhost:3000"}
        )

        # User A tries to delete Scan B -> 403
        with self.assertRaises(HTTPException) as ctx:
            run_async(remove_scan_json(req_a, self.scan_b_id))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_anonymous_scan_deletion_requires_admin(self):
        """Anonymous scans cannot be deleted by unauthorized users."""
        req_anon = MockRequest(
            cookies={},
            headers={"origin": "http://localhost:3000"}
        )
        with self.assertRaises(HTTPException) as ctx:
            run_async(remove_scan_json(req_anon, self.scan_anon_id))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_trigger_repo_scan_idor_protection(self):
        """User A cannot trigger scans on User B's repository."""
        req_a = MockRequest(
            cookies={"session_token": self.token_a},
            headers={"origin": "http://localhost:3000"}
        )
        bg = MagicMock()

        with self.assertRaises(HTTPException) as ctx:
            run_async(trigger_repo_scan(
                repo_id=self.repo_b["id"],
                request=req_a,
                background_tasks=bg,
                payload=None,
                user=self.user_a
            ))
        self.assertEqual(ctx.exception.status_code, 403)

if __name__ == "__main__":
    unittest.main()
