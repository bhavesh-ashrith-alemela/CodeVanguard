import unittest
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.file_filter import filter_repository_files

class TestFileFiltering(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.root = self.test_dir.name

    def tearDown(self):
        self.test_dir.cleanup()

    def _create_file(self, rel_path: str, content: bytes = b"sample code"):
        full_path = os.path.join(self.root, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(content)
        return full_path

    def test_default_ignored_directories_skipped(self):
        """Prove that directories like node_modules, .git, venv, dist, __pycache__ are excluded."""
        self._create_file("src/app.py", b"print('valid python')")
        self._create_file("node_modules/lib/index.js", b"console.log('third party')")
        self._create_file(".git/hooks/pre-commit", b"echo git")
        self._create_file("venv/bin/activate", b"echo venv")
        self._create_file("dist/bundle.js", b"var dist = 1;")
        self._create_file("src/__pycache__/app.cpython-313.pyc", b"bytecode")

        result = filter_repository_files(self.root)
        self.assertEqual(result.files_scanned, 1)
        self.assertTrue(result.has_python)
        self.assertFalse(result.has_js_ts)
        self.assertEqual(os.path.basename(result.scanned_files[0]), "app.py")

    def test_lockfiles_and_binaries_skipped(self):
        """Prove that lockfiles, binaries, images, and minified JS are excluded."""
        self._create_file("src/server.go", b"package main")
        self._create_file("package-lock.json", b"{}")
        self._create_file("poetry.lock", b"[metadata]")
        self._create_file("assets/logo.png", b"\x89PNG\r\n\x1a\n")
        self._create_file("static/bundle.min.js", b"function min(){}")
        self._create_file("lib/crypto.so", b"\x7fELF")

        result = filter_repository_files(self.root)
        self.assertEqual(result.files_scanned, 1)
        self.assertTrue(result.has_go)
        self.assertEqual(os.path.basename(result.scanned_files[0]), "server.go")

    def test_codevanguardignore_respected(self):
        """Prove that custom .codevanguardignore rules are honored."""
        self._create_file("src/safe.py", b"print('scan me')")
        self._create_file("legacy/old_script.py", b"print('skip me')")
        self._create_file("generated/auto.py", b"print('auto')")
        self._create_file(".codevanguardignore", b"legacy/*\ngenerated/\n")

        result = filter_repository_files(self.root)
        self.assertEqual(result.files_scanned, 1)
        self.assertEqual(os.path.basename(result.scanned_files[0]), "safe.py")

    def test_file_size_limit_skipped(self):
        """Prove that files exceeding 1MB (MAX_FILE_BYTES) are skipped."""
        self._create_file("src/normal.py", b"print('normal')")
        # 1.5MB file
        self._create_file("src/huge_data.js", b"x" * (1500 * 1024))

        result = filter_repository_files(self.root)
        self.assertEqual(result.files_scanned, 1)
        self.assertEqual(os.path.basename(result.scanned_files[0]), "normal.py")
        self.assertEqual(result.files_skipped, 1)

    def test_language_detection(self):
        """Prove that language flags accurately reflect scanned file types."""
        self._create_file("backend/app.py", b"import os")
        self._create_file("frontend/index.tsx", b"export default () => null")
        self._create_file("services/main.go", b"package main")

        result = filter_repository_files(self.root)
        self.assertEqual(result.files_scanned, 3)
        self.assertTrue(result.has_python)
        self.assertTrue(result.has_js_ts)
        self.assertTrue(result.has_go)

if __name__ == "__main__":
    unittest.main()
