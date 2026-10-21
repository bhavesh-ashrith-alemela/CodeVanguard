import unittest
import os
import sys
import tarfile
import zipfile
import tempfile
import io

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.file_handler import safe_extract_tar, extract_zip

class TestSafeExtraction(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.extract_dir = os.path.join(self.test_dir.name, "extracted")

    def tearDown(self):
        self.test_dir.cleanup()

    def test_tar_path_traversal_blocked(self):
        """Prove that tarballs containing '..' path traversal segments are rejected."""
        tar_path = os.path.join(self.test_dir.name, "traversal.tar")
        with tarfile.open(tar_path, "w") as tar:
            data = b"malicious content"
            ti = tarfile.TarInfo(name="../../etc/cron.d/evil")
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))

        with self.assertRaises(ValueError):
            safe_extract_tar(tar_path, self.extract_dir)

    def test_tar_absolute_path_blocked(self):
        """Prove that tarballs containing absolute paths are rejected."""
        tar_path = os.path.join(self.test_dir.name, "absolute.tar")
        with tarfile.open(tar_path, "w") as tar:
            data = b"malicious content"
            ti = tarfile.TarInfo(name="/etc/passwd")
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))

        with self.assertRaises(ValueError):
            safe_extract_tar(tar_path, self.extract_dir)

    def test_tar_symlink_blocked(self):
        """Prove that tarballs containing symbolic links are strictly rejected."""
        tar_path = os.path.join(self.test_dir.name, "symlink.tar")
        with tarfile.open(tar_path, "w") as tar:
            ti = tarfile.TarInfo(name="repo/link_to_root")
            ti.type = tarfile.SYMTYPE
            ti.linkname = "/etc/passwd"
            tar.addfile(ti)

        with self.assertRaises(ValueError) as ctx:
            safe_extract_tar(tar_path, self.extract_dir)
        self.assertIn("Unsafe member type blocked", str(ctx.exception))

    def test_tar_entry_limit_bomb_blocked(self):
        """Prove that tar bombs with excessive file counts are aborted."""
        tar_path = os.path.join(self.test_dir.name, "many_entries.tar")
        with tarfile.open(tar_path, "w") as tar:
            for i in range(15):
                data = b"small"
                ti = tarfile.TarInfo(name=f"file_{i}.txt")
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))

        # Test with max_entries cap of 10
        with self.assertRaises(ValueError) as ctx:
            safe_extract_tar(tar_path, self.extract_dir, max_entries=10)
        self.assertIn("entry limit", str(ctx.exception))

    def test_tar_size_bomb_blocked(self):
        """Prove that tar archives expanding beyond byte caps are rejected."""
        tar_path = os.path.join(self.test_dir.name, "size_bomb.tar")
        with tarfile.open(tar_path, "w") as tar:
            data = b"A" * 1024 * 50 # 50 KB
            ti = tarfile.TarInfo(name="big_file.txt")
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))

        # Test with max_total_bytes cap of 10 KB
        with self.assertRaises(ValueError) as ctx:
            safe_extract_tar(tar_path, self.extract_dir, max_total_bytes=10 * 1024)
        self.assertIn("uncompressed size exceeds limit", str(ctx.exception))

    def test_tar_github_top_level_stripping(self):
        """Prove that GitHub codeload top-level folder 'owner-repo-sha/' is stripped cleanly."""
        tar_path = os.path.join(self.test_dir.name, "github_repo.tar")
        with tarfile.open(tar_path, "w") as tar:
            data = b"print('Hello CodeVanguard')"
            ti = tarfile.TarInfo(name="owner-repo-abcdef1234/src/main.py")
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))

        success = safe_extract_tar(tar_path, self.extract_dir, strip_top_level=True)
        self.assertTrue(success)

        extracted_file = os.path.join(self.extract_dir, "src", "main.py")
        self.assertTrue(os.path.exists(extracted_file))
        with open(extracted_file, "rb") as f:
            self.assertEqual(f.read(), data)

    def test_zip_path_traversal_blocked(self):
        """Prove that zip files with path traversal are rejected."""
        zip_path = os.path.join(self.test_dir.name, "slip.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../../etc/shadow", b"root:secret")

        with self.assertRaises(ValueError):
            extract_zip(zip_path, self.extract_dir)

    def test_zip_symlink_blocked(self):
        """Prove that zip files containing symlinks are rejected."""
        zip_path = os.path.join(self.test_dir.name, "symlink.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zi = zipfile.ZipInfo("symlink_target")
            # Unix symlink attribute
            zi.external_attr = 0o120777 << 16
            zf.writestr(zi, "/etc/passwd")

        with self.assertRaises(ValueError) as ctx:
            extract_zip(zip_path, self.extract_dir)
        self.assertIn("symlink", str(ctx.exception).lower())

    def test_zip_size_bomb_blocked(self):
        """Prove that zip bombs expanding beyond size cap are rejected."""
        zip_path = os.path.join(self.test_dir.name, "zip_bomb.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("large.txt", b"B" * 20 * 1024)

        with self.assertRaises(ValueError) as ctx:
            extract_zip(zip_path, self.extract_dir, max_total_bytes=5 * 1024)
        self.assertIn("exceeds", str(ctx.exception).lower())

    def test_streaming_chunk_copy_aborts_on_byte_limit(self):
        """Prove that _safe_stream_copy halts writes immediately when cumulative limit is breached."""
        from app.utils.file_handler import _safe_stream_copy
        src = io.BytesIO(b"Z" * 10000)
        dst = io.BytesIO()
        with self.assertRaises(ValueError) as ctx:
            # Limit to 3000 bytes with current total at 1000 bytes
            _safe_stream_copy(src, dst, current_total_bytes=1000, max_total_bytes=3000, chunk_size=512)
        self.assertIn("exceeds limit", str(ctx.exception).lower())
        # Total written to dst should be strictly <= 2048 bytes
        self.assertLessEqual(len(dst.getvalue()), 2048)

    def test_tar_multi_file_cumulative_size_limit(self):
        """Prove that cumulative bytes across multiple files in a tarball trigger extraction abort."""
        tar_path = os.path.join(self.test_dir.name, "cumulative.tar")
        with tarfile.open(tar_path, "w") as tar:
            for i in range(5):
                data = b"C" * 2048 # 2 KB each = 10 KB total
                ti = tarfile.TarInfo(name=f"file_{i}.txt")
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))

        with self.assertRaises(ValueError) as ctx:
            safe_extract_tar(tar_path, self.extract_dir, max_total_bytes=5 * 1024)
        self.assertIn("uncompressed size exceeds limit", str(ctx.exception).lower())
        # Ensure extraction directory was cleaned up
        self.assertFalse(os.path.exists(self.extract_dir))

if __name__ == "__main__":
    unittest.main()
