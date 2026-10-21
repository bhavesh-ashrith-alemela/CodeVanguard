import os
import fnmatch
from dataclasses import dataclass, field
from typing import List, Set, Optional

DEFAULT_IGNORED_DIRS: Set[str] = {
    "node_modules", "vendor", ".git", "dist", "build", ".next",
    "venv", ".venv", "env", "__pycache__", ".idea", ".vscode",
    "target", "out", "coverage", ".turbo", ".cache", "temp", "reports"
}

BINARY_AND_MEDIA_EXTENSIONS: Set[str] = {
    ".exe", ".dll", ".so", ".dylib", ".bin", ".iso", ".pyc", ".pyo", ".class",
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp", ".tiff",
    ".mp3", ".wav", ".mp4", ".mov", ".avi", ".mkv",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".map", ".sqlite", ".db"
}

LOCKFILES_AND_GENERATED: Set[str] = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "pipfile.lock", "composer.lock", "go.sum", "cargo.lock", "gemfile.lock"
}

SUPPORTED_EXTENSIONS: Set[str] = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go"
}

MAX_FILE_BYTES: int = int(os.environ.get("MAX_FILE_BYTES", 1024 * 1024))         # 1 MB
MAX_FILES: int = int(os.environ.get("MAX_FILES", 2000))                           # 2,000 files
MAX_TOTAL_BYTES: int = int(os.environ.get("MAX_TOTAL_BYTES", 50 * 1024 * 1024))  # 50 MB

@dataclass
class FileFilterResult:
    scanned_files: List[str] = field(default_factory=list)
    files_scanned: int = 0
    files_skipped: int = 0
    total_bytes_scanned: int = 0
    has_python: bool = False
    has_js_ts: bool = False
    has_go: bool = False
    limit_exceeded: bool = False
    limit_reason: Optional[str] = None

def load_ignore_patterns(target_dir: str) -> List[str]:
    """Reads .codevanguardignore patterns from the target repository root if present."""
    ignore_file = os.path.join(target_dir, ".codevanguardignore")
    patterns = []
    if os.path.exists(ignore_file):
        try:
            with open(ignore_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
        except Exception as e:
            print(f"Warning: Failed to read .codevanguardignore: {e}")
    return patterns

def is_minified_file(filename: str) -> bool:
    """Returns True if the file name indicates minified or bundled assets."""
    lower = filename.lower()
    return (
        lower.endswith(".min.js") or
        lower.endswith(".min.css") or
        "-min.js" in lower or
        lower.endswith(".bundle.js") or
        lower.endswith(".chunk.js")
    )

def matches_ignore_patterns(rel_path: str, patterns: List[str]) -> bool:
    """Tests if a relative file path matches any .codevanguardignore glob pattern."""
    norm = rel_path.replace("\\", "/")
    for pattern in patterns:
        norm_pat = pattern.replace("\\", "/").rstrip("/")
        if fnmatch.fnmatch(norm, norm_pat) or fnmatch.fnmatch(norm, f"*/{norm_pat}") or fnmatch.fnmatch(norm, f"{norm_pat}/*"):
            return True
        if fnmatch.fnmatch(os.path.basename(norm), norm_pat):
            return True
    return False

def filter_repository_files(target_dir: str) -> FileFilterResult:
    """
    Scans target_dir and determines which files to scan vs skip.
    Applies directory pruning, ignore patterns, extension checks, and size bounds.
    """
    result = FileFilterResult()
    target_abs = os.path.abspath(target_dir)

    # Handle single file target (e.g. pasted code)
    if os.path.isfile(target_abs):
        ext = os.path.splitext(target_abs)[1].lower()
        size = os.path.getsize(target_abs)
        if ext in SUPPORTED_EXTENSIONS and size <= MAX_FILE_BYTES:
            result.scanned_files.append(target_abs)
            result.files_scanned = 1
            result.total_bytes_scanned = size
            result.has_python = (ext == ".py")
            result.has_js_ts = ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
            result.has_go = (ext == ".go")
        else:
            result.files_skipped = 1
        return result

    ignore_patterns = load_ignore_patterns(target_abs)

    for root, dirs, files in os.walk(target_abs, topdown=True):
        # 1. Prune ignored directories in-place so os.walk does not descend into them
        dirs[:] = [
            d for d in dirs
            if d.lower() not in DEFAULT_IGNORED_DIRS and
            not matches_ignore_patterns(os.path.relpath(os.path.join(root, d), target_abs), ignore_patterns)
        ]

        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, target_abs).replace("\\", "/")
            ext = os.path.splitext(file)[1].lower()
            filename_lower = file.lower()

            # Check ignore patterns
            if matches_ignore_patterns(rel_path, ignore_patterns):
                result.files_skipped += 1
                continue

            # Check lockfiles & generated files
            if filename_lower in LOCKFILES_AND_GENERATED:
                result.files_skipped += 1
                continue

            # Check minified assets
            if is_minified_file(file):
                result.files_skipped += 1
                continue

            # Check binary and media files
            if ext in BINARY_AND_MEDIA_EXTENSIONS:
                result.files_skipped += 1
                continue

            # Check supported code extensions
            if ext not in SUPPORTED_EXTENSIONS:
                result.files_skipped += 1
                continue

            # Check file size (skip files > MAX_FILE_BYTES)
            try:
                size = os.path.getsize(file_path)
            except OSError:
                result.files_skipped += 1
                continue

            if size > MAX_FILE_BYTES:
                result.files_skipped += 1
                continue

            # Check repository file limits
            if result.files_scanned >= MAX_FILES:
                result.limit_exceeded = True
                result.limit_reason = f"Maximum file limit ({MAX_FILES}) reached."
                result.files_skipped += 1
                continue

            if result.total_bytes_scanned + size > MAX_TOTAL_BYTES:
                result.limit_exceeded = True
                result.limit_reason = f"Maximum total code size ({MAX_TOTAL_BYTES // (1024*1024)}MB) reached."
                result.files_skipped += 1
                continue

            # Eligible for scan
            result.scanned_files.append(file_path)
            result.files_scanned += 1
            result.total_bytes_scanned += size

            if ext == ".py":
                result.has_python = True
            elif ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
                result.has_js_ts = True
            elif ext == ".go":
                result.has_go = True

    return result
