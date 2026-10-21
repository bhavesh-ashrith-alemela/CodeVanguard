import unittest
import asyncio
from app.services.autofix.verifier import (
    apply_patch_to_file, check_syntax, verify_patch, VerificationResult, MAX_DIFF_LINES
)
from app.utils.fingerprint import compute_fingerprint

class TestAutofixVerification(unittest.TestCase):
    """
    Validates the isolated verification pipeline:
    - Syntax compilation
    - Line replacement & diff capping (<= 50 lines)
    - Original fingerprint resolution and regression testing
    """

    def test_apply_patch_success(self):
        original = "line1\nline2\nline3\nline4\n"
        patch = "patched_line2\npatched_line3"
        result, diff, mod_lines = apply_patch_to_file(original, patch, 2, 3)

        expected = "line1\npatched_line2\npatched_line3\nline4\n"
        self.assertEqual(result, expected)
        self.assertIn("-line2", diff)
        self.assertIn("+patched_line2", diff)
        self.assertEqual(mod_lines, 4)

    def test_verify_patch_diff_cap_enforcement(self):
        """Diffs exceeding MAX_DIFF_LINES (50) must be rejected by verify_patch."""
        original = "def foo():\n    pass\n"
        huge_patch = "def foo():\n" + "\n".join(f"    x_{i} = {i}" for i in range(60))
        v_res = asyncio.run(verify_patch(
            original_content=original,
            patched_function=huge_patch,
            filepath="test.py",
            start_line=1,
            end_line=2,
            original_fingerprint="fp123"
        ))
        self.assertFalse(v_res.is_verified)
        self.assertIn("exceeds limit of 50 lines", v_res.rejection_reason)

    def test_syntax_check_python(self):
        valid_py = "def hello():\n    return 'world'\n"
        ok, err = check_syntax(valid_py, "hello.py")
        self.assertTrue(ok)
        self.assertIsNone(err)

        invalid_py = "def hello(\n    return 'world'"
        ok, err = check_syntax(invalid_py, "hello.py")
        self.assertFalse(ok)
        self.assertIn("Syntax", err)

    def test_syntax_check_javascript(self):
        valid_js = "function add(a, b) { return a + b; }"
        ok, err = check_syntax(valid_js, "calc.js")
        self.assertTrue(ok)

        invalid_js = "function add(a, b) { return a + b;"
        ok, err = check_syntax(invalid_js, "calc.js")
        self.assertFalse(ok)
        self.assertIn("Unclosed bracket", err)

    def test_syntax_check_go(self):
        valid_go = "package main\nfunc main() {\n}\n"
        ok, err = check_syntax(valid_go, "main.go")
        self.assertTrue(ok)

        invalid_go = "package main\nfunc main() {"
        ok, err = check_syntax(invalid_go, "main.go")
        self.assertFalse(ok)
        self.assertIn("Mismatched braces", err)

    def test_verify_patch_syntax_failure_rejection(self):
        original = "def query():\n    pass\n"
        invalid_patch = "def query(\n    broken"
        
        v_res = asyncio.run(verify_patch(
            original_content=original,
            patched_function=invalid_patch,
            filepath="test.py",
            start_line=1,
            end_line=2,
            original_fingerprint="fp123"
        ))

        self.assertFalse(v_res.is_verified)
        self.assertFalse(v_res.syntax_valid)
        self.assertIn("Syntax", v_res.rejection_reason)

    def test_verify_patch_success_when_fingerprint_cleared(self):
        original = """import sqlite3

def get_user(conn, uid):
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM users WHERE id = {uid}")
    return cursor.fetchone()
"""
        patched = """def get_user(conn, uid):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (uid,))
    return cursor.fetchone()"""

        orig_fp = compute_fingerprint("B608:hardcoded_sql_expressions", "test.py", original)

        v_res = asyncio.run(verify_patch(
            original_content=original,
            patched_function=patched,
            filepath="test.py",
            start_line=3,
            end_line=7,
            original_fingerprint=orig_fp
        ))

        self.assertTrue(v_res.is_verified)
        self.assertTrue(v_res.syntax_valid)
        self.assertTrue(v_res.original_fingerprint_resolved)
        self.assertEqual(v_res.new_findings_count, 0)
        self.assertIsNone(v_res.rejection_reason)
        self.assertIsNotNone(v_res.diff)

if __name__ == "__main__":
    unittest.main()
