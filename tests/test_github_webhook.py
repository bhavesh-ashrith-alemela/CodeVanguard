import os
import hmac
import hashlib
import json
import asyncio
import unittest
from unittest.mock import patch

from app.routers.webhook import verify_github_signature, github_webhook_receiver
from app.utils.db import (
    init_db, get_installation_by_github_id, get_repository_by_github_id
)

class MockRequest:
    def __init__(self, body_bytes: bytes, headers: dict):
        self._body = body_bytes
        self.headers = headers

    async def body(self):
        return self._body

def run_async(coro):
    return asyncio.run(coro)

class TestGitHubWebhook(unittest.TestCase):
    def setUp(self):
        init_db()
        from app.utils.db import get_db_connection
        with get_db_connection() as conn:
            conn.cursor().execute("DELETE FROM webhook_deliveries")
            conn.commit()
        self.webhook_secret = "test-webhook-secret-998877"
        self.env_patcher = patch.dict(os.environ, {
            "GITHUB_WEBHOOK_SECRET": self.webhook_secret
        })
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    def _sign_payload(self, body_bytes: bytes) -> str:
        sig = hmac.new(self.webhook_secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        return f"sha256={sig}"

    def test_verify_github_signature(self):
        """Direct unit test of verify_github_signature helper."""
        body = b'{"action": "ping"}'
        valid_sig = self._sign_payload(body)

        # 1. Valid signature
        self.assertTrue(verify_github_signature(body, valid_sig))

        # 2. Tampered body
        self.assertFalse(verify_github_signature(b'{"action": "tampered"}', valid_sig))

        # 3. Missing or malformed header
        self.assertFalse(verify_github_signature(body, None))
        self.assertFalse(verify_github_signature(body, "invalid_prefix"))

        # 4. Missing webhook secret in env
        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": ""}):
            self.assertFalse(verify_github_signature(body, valid_sig))

    def test_missing_signature_raises_401(self):
        """Webhooks missing X-Hub-Signature-256 header are rejected with 401."""
        req = MockRequest(
            body_bytes=b'{"action": "created"}',
            headers={"Content-Type": "application/json", "X-GitHub-Event": "ping"}
        )
        with self.assertRaises(Exception) as ctx:
            run_async(github_webhook_receiver(req))
        exc = ctx.exception
        self.assertEqual(getattr(exc, "status_code", None), 401)

    def test_invalid_signature_raises_401(self):
        """Webhooks with mismatched HMAC signature are rejected with 401."""
        req = MockRequest(
            body_bytes=b'{"action": "created"}',
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "ping",
                "x-hub-signature-256": "sha256=invalid0000000000000000000000000000000000000000000000000000000000"
            }
        )
        with self.assertRaises(Exception) as ctx:
            run_async(github_webhook_receiver(req))
        exc = ctx.exception
        self.assertEqual(getattr(exc, "status_code", None), 401)

    def test_valid_ping_event_accepted_202(self):
        """Validly signed ping event returns 202 Accepted."""
        body = json.dumps({"zen": "Keep it logically awesome."}).encode("utf-8")
        sig = self._sign_payload(body)

        req = MockRequest(
            body_bytes=body,
            headers={
                "Content-Type": "application/json",
                "x-github-event": "ping",
                "x-hub-signature-256": sig,
                "x-hub-delivery": "delivery-uuid-001"
            }
        )
        res = run_async(github_webhook_receiver(req))
        self.assertEqual(getattr(res, "status_code", 202), 202)

    def test_installation_lifecycle(self):
        """Validates installation creation, suspension, and deletion webhook handling."""
        inst_id = 771122
        
        # 1. installation.created
        created_payload = {
            "action": "created",
            "installation": {
                "id": inst_id,
                "account": {"login": "acme-corp", "type": "Organization", "avatar_url": "https://avatars.example.com/acme"}
            },
            "repositories": [
                {"id": 8811, "name": "backend-api", "full_name": "acme-corp/backend-api", "private": True, "default_branch": "main"}
            ]
        }
        body = json.dumps(created_payload).encode("utf-8")
        sig = self._sign_payload(body)

        req1 = MockRequest(
            body_bytes=body,
            headers={
                "Content-Type": "application/json",
                "x-github-event": "installation",
                "x-hub-signature-256": sig,
                "x-hub-delivery": "delivery-inst-create-1"
            }
        )
        res1 = run_async(github_webhook_receiver(req1))
        self.assertEqual(getattr(res1, "status_code", 202), 202)

        inst = get_installation_by_github_id(inst_id)
        self.assertIsNotNone(inst)
        self.assertEqual(inst["account_login"], "acme-corp")

        repo = get_repository_by_github_id(8811)
        self.assertIsNotNone(repo)
        self.assertEqual(repo["full_name"], "acme-corp/backend-api")

        # 2. installation.suspend
        suspend_payload = {"action": "suspend", "installation": {"id": inst_id}}
        body_suspend = json.dumps(suspend_payload).encode("utf-8")
        sig_suspend = self._sign_payload(body_suspend)

        req2 = MockRequest(
            body_bytes=body_suspend,
            headers={
                "Content-Type": "application/json",
                "x-github-event": "installation",
                "x-hub-signature-256": sig_suspend,
                "x-hub-delivery": "delivery-inst-suspend-2"
            }
        )
        res2 = run_async(github_webhook_receiver(req2))
        self.assertEqual(getattr(res2, "status_code", 202), 202)
        inst_suspended = get_installation_by_github_id(inst_id)
        self.assertIsNotNone(inst_suspended["suspended_at"])

        # 3. installation.unsuspend
        unsuspend_payload = {"action": "unsuspend", "installation": {"id": inst_id}}
        body_unsuspend = json.dumps(unsuspend_payload).encode("utf-8")
        sig_unsuspend = self._sign_payload(body_unsuspend)

        req3 = MockRequest(
            body_bytes=body_unsuspend,
            headers={
                "Content-Type": "application/json",
                "x-github-event": "installation",
                "x-hub-signature-256": sig_unsuspend,
                "x-hub-delivery": "delivery-inst-unsuspend-3"
            }
        )
        res3 = run_async(github_webhook_receiver(req3))
        self.assertEqual(getattr(res3, "status_code", 202), 202)
        inst_active = get_installation_by_github_id(inst_id)
        self.assertIsNone(inst_active["suspended_at"])

        # 4. installation.deleted
        deleted_payload = {"action": "deleted", "installation": {"id": inst_id}}
        body_del = json.dumps(deleted_payload).encode("utf-8")
        sig_del = self._sign_payload(body_del)

        req4 = MockRequest(
            body_bytes=body_del,
            headers={
                "Content-Type": "application/json",
                "x-github-event": "installation",
                "x-hub-signature-256": sig_del,
                "x-hub-delivery": "delivery-inst-del-4"
            }
        )
        res4 = run_async(github_webhook_receiver(req4))
        self.assertEqual(getattr(res4, "status_code", 202), 202)
        inst_deleted = get_installation_by_github_id(inst_id)
        self.assertIsNotNone(inst_deleted["deleted_at"])

    def test_installation_repositories_added_and_removed(self):
        """Validates dynamic repository additions and removals via installation_repositories."""
        inst_id = 554433
        # Setup installation
        from app.utils.db import upsert_installation
        inst = upsert_installation(inst_id, "org-repos", "Organization")

        # 1. Add repository
        add_payload = {
            "action": "added",
            "installation": {"id": inst_id},
            "repositories_added": [
                {"id": 9901, "full_name": "org-repos/payments", "default_branch": "master", "private": False}
            ],
            "repositories_removed": []
        }
        body_add = json.dumps(add_payload).encode("utf-8")
        sig_add = self._sign_payload(body_add)

        req1 = MockRequest(
            body_bytes=body_add,
            headers={
                "Content-Type": "application/json",
                "x-github-event": "installation_repositories",
                "x-hub-signature-256": sig_add,
                "x-hub-delivery": "delivery-repos-add-1"
            }
        )
        res1 = run_async(github_webhook_receiver(req1))
        self.assertEqual(getattr(res1, "status_code", 202), 202)
        repo = get_repository_by_github_id(9901)
        self.assertIsNotNone(repo)
        self.assertEqual(repo["full_name"], "org-repos/payments")

        # 2. Remove repository
        rem_payload = {
            "action": "removed",
            "installation": {"id": inst_id},
            "repositories_added": [],
            "repositories_removed": [{"id": 9901, "full_name": "org-repos/payments"}]
        }
        body_rem = json.dumps(rem_payload).encode("utf-8")
        sig_rem = self._sign_payload(body_rem)

        req2 = MockRequest(
            body_bytes=body_rem,
            headers={
                "Content-Type": "application/json",
                "x-github-event": "installation_repositories",
                "x-hub-signature-256": sig_rem,
                "x-hub-delivery": "delivery-repos-rem-2"
            }
        )
        res2 = run_async(github_webhook_receiver(req2))
        self.assertEqual(getattr(res2, "status_code", 202), 202)
        repo_removed = get_repository_by_github_id(9901)
        self.assertIsNotNone(repo_removed["deleted_at"])

if __name__ == "__main__":
    unittest.main()
