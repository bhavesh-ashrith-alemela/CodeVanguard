import unittest
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.db import (
    init_db, create_scan, get_scan, save_scan_results, get_scan_issues,
    update_scan_progress, update_scan_metrics, get_db_connection
)

class TestDatabaseAdapter(unittest.TestCase):
    def setUp(self):
        # Use an isolated test database
        import app.utils.db as db_module
        self.orig_db_dir = db_module.DB_DIR
        self.orig_db_path = db_module.DB_PATH
        self.orig_data_dir = os.environ.get("DATA_DIR")

        self.test_dir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self.test_dir.name
        # Reset DB_PATH in db module
        db_module.DB_DIR = self.test_dir.name
        db_module.DB_PATH = os.path.join(self.test_dir.name, "codevanguard.db")
        init_db()

    def tearDown(self):
        self.test_dir.cleanup()
        import app.utils.db as db_module
        db_module.DB_DIR = self.orig_db_dir
        db_module.DB_PATH = self.orig_db_path
        if self.orig_data_dir is not None:
            os.environ["DATA_DIR"] = self.orig_data_dir
        elif "DATA_DIR" in os.environ:
            del os.environ["DATA_DIR"]

    def test_migrations_and_scan_lifecycle(self):
        scan_id = uuid.uuid4().hex
        scan = create_scan(
            scan_id=scan_id,
            filename="octocat/Hello-World@main",
            file_size=1024,
            source_type="github_public",
            source_url="https://github.com/octocat/Hello-World",
            branch="main",
            commit_sha="7fd1a60b01f91b314f59955a4e4d4e80d8edf11d"
        )

        self.assertEqual(scan["id"], scan_id)
        self.assertEqual(scan["source_type"], "github_public")
        self.assertEqual(scan["branch"], "main")
        self.assertEqual(scan["commit_sha"], "7fd1a60b01f91b314f59955a4e4d4e80d8edf11d")
        self.assertEqual(scan["progress"], "queued")
        self.assertEqual(scan["status"], "pending")

        # Update progress
        update_scan_progress(scan_id, "downloading")
        fetched = get_scan(scan_id)
        self.assertEqual(fetched["progress"], "downloading")

        # Update metrics
        update_scan_metrics(scan_id, duration_ms=1500, files_scanned=25, files_skipped=5)
        fetched = get_scan(scan_id)
        self.assertEqual(fetched["duration_ms"], 1500)
        self.assertEqual(fetched["files_scanned"], 25)
        self.assertEqual(fetched["files_skipped"], 5)

        # Save scan results and verify fingerprinting
        mock_issues = [
            {
                "scanner": "bandit",
                "rule_id": "B608",
                "severity": "high",
                "message": "Possible SQL injection",
                "filepath": "app/db.py",
                "line_number": 42,
                "col_number": 0,
                "code_snippet": "42: cursor.execute(query)"
            }
        ]
        save_scan_results(scan_id, mock_issues, duration_ms=2100, files_scanned=28, files_skipped=5)
        
        updated_scan = get_scan(scan_id)
        self.assertEqual(updated_scan["status"], "completed")
        self.assertEqual(updated_scan["progress"], "completed")
        self.assertEqual(updated_scan["total_issues"], 1)
        self.assertEqual(updated_scan["high_count"], 1)

        issues = get_scan_issues(scan_id)
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertIsNotNone(issue.get("fingerprint"))
        self.assertEqual(len(issue["fingerprint"]), 64) # SHA-256 length
        self.assertEqual(issue["state"], "open")

    def test_sanitize_database_url_special_characters(self):
        """Verifies special characters (%, ?, #, @) in db password are safely percent-encoded for psycopg2."""
        from app.utils.db import sanitize_database_url

        raw_url = "postgresql://postgres.mfz4c:%cmZR?qE%?t8se4@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require"
        sanitized = sanitize_database_url(raw_url)

        self.assertIn("%25cmZR%3FqE%25%3Ft8se4", sanitized)
        self.assertNotIn("?qE", sanitized.split("@")[0]) # ? must be escaped in userinfo

        # Verify idempotency (no double encoding)
        self.assertEqual(sanitize_database_url(sanitized), sanitized)

    def test_postgres_cursor_wrapper_insert_or_ignore(self):
        """Verifies PostgresCursorWrapper translates INSERT OR IGNORE INTO to ON CONFLICT DO NOTHING."""
        from unittest.mock import MagicMock
        from app.utils.db import PostgresCursorWrapper

        mock_cursor = MagicMock()
        wrapper = PostgresCursorWrapper(mock_cursor)

        query = "INSERT OR IGNORE INTO installation_members (installation_id, user_id) VALUES (?, ?)"
        wrapper.execute(query, ("inst_1", 42))

        called_query = mock_cursor.execute.call_args[0][0]
        self.assertNotIn("INSERT OR IGNORE", called_query)
        self.assertIn("INSERT INTO installation_members", called_query)
        self.assertIn("ON CONFLICT DO NOTHING", called_query)
        self.assertIn("%s, %s", called_query)

if __name__ == "__main__":
    unittest.main()
