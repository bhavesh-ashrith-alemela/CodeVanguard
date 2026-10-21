import unittest
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.fingerprint import compute_fingerprint, normalize_code_snippet, normalize_filepath

class TestFingerprint(unittest.TestCase):
    def test_stability_when_lines_inserted_above(self):
        """
        Prove fingerprint remains stable when lines (e.g. comments, imports)
        are inserted above the finding, changing line numbers.
        """
        rule_id = "B608"
        filepath = "src/database/users.py"

        # Finding at line 14
        snippet_v1 = """14: def get_user(username):
15:     cursor.execute(f"SELECT * FROM users WHERE name = '{username}'")
16:     return cursor.fetchone()"""

        # 30 lines inserted above; finding is now at line 44
        snippet_v2 = """44: def get_user(username):
45:     cursor.execute(f"SELECT * FROM users WHERE name = '{username}'")
46:     return cursor.fetchone()"""

        # Also test with different line-prefix decoration (pipe style)
        snippet_v3 = """44 | def get_user(username):
45 |     cursor.execute(f"SELECT * FROM users WHERE name = '{username}'")
46 |     return cursor.fetchone()"""

        fp1 = compute_fingerprint(rule_id, filepath, snippet_v1)
        fp2 = compute_fingerprint(rule_id, filepath, snippet_v2)
        fp3 = compute_fingerprint(rule_id, filepath, snippet_v3)

        self.assertEqual(fp1, fp2, "Fingerprint changed when lines were inserted above the finding!")
        self.assertEqual(fp1, fp3, "Fingerprint differed between line-prefix decoration styles!")

    def test_fingerprint_changes_when_code_changes(self):
        """
        Prove fingerprint changes when the vulnerable code content itself changes.
        """
        rule_id = "B608"
        filepath = "src/database/users.py"

        original_snippet = """14: def get_user(username):
15:     cursor.execute(f"SELECT * FROM users WHERE name = '{username}'")"""

        modified_code = """14: def get_user(username):
15:     cursor.execute(f"SELECT * FROM accounts WHERE id = '{username}'")"""

        fp_orig = compute_fingerprint(rule_id, filepath, original_snippet)
        fp_mod = compute_fingerprint(rule_id, filepath, modified_code)

        self.assertNotEqual(fp_orig, fp_mod, "Fingerprint should have changed when code changed!")

    def test_fingerprint_changes_when_rule_or_file_changes(self):
        snippet = """15: cursor.execute("SELECT * FROM users")"""

        fp_base = compute_fingerprint("B608", "src/db.py", snippet)
        fp_diff_rule = compute_fingerprint("python.lang.security.audit.sqli", "src/db.py", snippet)
        fp_diff_file = compute_fingerprint("B608", "src/other_db.py", snippet)

        self.assertNotEqual(fp_base, fp_diff_rule)
        self.assertNotEqual(fp_base, fp_diff_file)

    def test_path_normalization(self):
        """
        Prove filepath normalization handles Windows backslashes, leading './', and extra whitespace.
        """
        rule_id = "B101"
        snippet = "assert x == y"

        fp_unix = compute_fingerprint(rule_id, "app/utils/auth.py", snippet)
        fp_windows = compute_fingerprint(rule_id, r"app\utils\auth.py", snippet)
        fp_relative = compute_fingerprint(rule_id, "./app/utils/auth.py", snippet)

        self.assertEqual(fp_unix, fp_windows)
        self.assertEqual(fp_unix, fp_relative)

    def test_whitespace_insensitivity(self):
        """
        Prove trailing whitespace or differing indentation doesn't alter the fingerprint.
        """
        rule_id = "eval-injection"
        filepath = "handler.js"

        snippet_1 = "10:   eval(user_input);   \n11:   return true;  "
        snippet_2 = "10: eval(user_input);\n11: return true;"

        fp1 = compute_fingerprint(rule_id, filepath, snippet_1)
        fp2 = compute_fingerprint(rule_id, filepath, snippet_2)

        self.assertEqual(fp1, fp2)

if __name__ == "__main__":
    unittest.main()
