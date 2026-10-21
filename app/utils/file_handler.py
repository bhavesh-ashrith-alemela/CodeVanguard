import os
import tarfile
import zipfile
import shutil
try:
    from fastapi import UploadFile
except ImportError:
    UploadFile = object

TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "temp")

DEFAULT_MAX_ARCHIVE_ENTRIES = int(os.environ.get("MAX_ARCHIVE_ENTRIES", 5000))
DEFAULT_MAX_UNCOMPRESSED_BYTES = int(os.environ.get("MAX_UNCOMPRESSED_BYTES", 100 * 1024 * 1024)) # 100 MB

def get_scan_dir(scan_id: str) -> str:
    """Returns the temporary scan directory for a given scan_id."""
    return os.path.join(TEMP_DIR, scan_id)

def ensure_temp_dir():
    """Ensures that the global temp directory exists."""
    os.makedirs(TEMP_DIR, exist_ok=True)

def is_safe_path(base_dir: str, path: str) -> bool:
    """
    Prevents Zip Slip / Path Traversal vulnerabilities by ensuring that
    all extracted paths resolve to be strictly under base_dir.
    """
    base_abs = os.path.abspath(base_dir)
    target_abs = os.path.abspath(path)
    return base_abs == os.path.commonpath((base_abs, target_abs))

def _safe_stream_copy(src, dst, current_total_bytes: int, max_total_bytes: int, chunk_size: int = 64 * 1024) -> int:
    """
    Copies chunks from src to dst while tracking cumulative byte count across the entire archive extraction.
    Raises ValueError immediately if the cumulative bytes exceed max_total_bytes.
    Returns the number of bytes written in this operation.
    """
    written = 0
    while True:
        chunk = src.read(chunk_size)
        if not chunk:
            break
        if current_total_bytes + written + len(chunk) > max_total_bytes:
            raise ValueError(f"Archive uncompressed size exceeds limit of {max_total_bytes} bytes.")
        dst.write(chunk)
        written += len(chunk)
    return written

def safe_extract_tar(
    tar_path: str,
    extract_to: str,
    max_entries: int = DEFAULT_MAX_ARCHIVE_ENTRIES,
    max_total_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
    strip_top_level: bool = True
) -> bool:
    """
    Safely extracts a tarball (.tar, .tar.gz):
    - Rejects absolute paths and '..' traversal segments.
    - Rejects symlinks, hardlinks, character/block devices, and fifos.
    - Caps total entry count and total uncompressed bytes (bomb protection).
    - Strips the top-level GitHub repository directory if present.
    """
    os.makedirs(extract_to, exist_ok=True)
    extract_to_abs = os.path.abspath(extract_to)

    entry_count = 0
    total_uncompressed_bytes = 0

    try:
        with tarfile.open(tar_path, "r:*") as tar:
            members = tar.getmembers()

            # Check if all members share a common root directory (e.g. GitHub codeload archives)
            common_root = None
            if strip_top_level and members:
                has_nested = any(len(m.name.replace("\\", "/").strip("/").split("/")) > 1 for m in members)
                if has_nested:
                    first_parts = [m.name.replace("\\", "/").strip("/").split("/")[0] for m in members if m.name.strip("/")]
                    if first_parts and all(p == first_parts[0] for p in first_parts):
                        common_root = first_parts[0]

            for member in members:
                entry_count += 1
                if entry_count > max_entries:
                    raise ValueError(f"Tar bomb blocked: archive exceeds entry limit ({max_entries}).")

                # Block unsafe member types: symlinks, hardlinks, device files, fifos
                if member.issym() or member.islnk() or member.ischr() or member.isblk() or member.isfifo() or member.isdev():
                    raise ValueError(f"Unsafe member type blocked (symlink/device/link): {member.name}")

                if not (member.isreg() or member.isdir()):
                    raise ValueError(f"Unsafe non-regular file blocked: {member.name}")

                # Path traversal checks
                raw_name = member.name.replace("\\", "/").strip()
                if raw_name.startswith("/") or raw_name.startswith("\\") or ":" in raw_name:
                    raise ValueError(f"Absolute path or drive specifier in archive member: {member.name}")

                parts = [p for p in raw_name.split("/") if p]
                if any(p == ".." or p == "." for p in parts):
                    raise ValueError(f"Path traversal segment '..' detected: {member.name}")

                # Determine target relative path (strip top-level common root if applicable)
                if common_root and len(parts) > 1 and parts[0] == common_root:
                    rel_parts = parts[1:]
                elif common_root and len(parts) == 1 and parts[0] == common_root:
                    # Root folder itself
                    continue
                else:
                    rel_parts = parts

                if not rel_parts:
                    continue

                target_path = os.path.abspath(os.path.join(extract_to_abs, *rel_parts))

                # Verify resolved target path is strictly within extract_to_abs
                if not is_safe_path(extract_to_abs, target_path):
                    raise ValueError(f"Path traversal outside target directory: {member.name}")

                # Check declared header size upfront as an early guard
                if total_uncompressed_bytes + member.size > max_total_bytes:
                    raise ValueError(f"Archive uncompressed size exceeds limit of {max_total_bytes} bytes.")

                # Extract safely with streaming byte tracking
                if member.isdir():
                    os.makedirs(target_path, exist_ok=True)
                elif member.isreg():
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    f_in = tar.extractfile(member)
                    if f_in:
                        with f_in, open(target_path, "wb") as f_out:
                            written = _safe_stream_copy(f_in, f_out, total_uncompressed_bytes, max_total_bytes)
                            total_uncompressed_bytes += written

        return True
    except Exception as e:
        print(f"Tar extraction failed: {e}")
        # Clean up partial extraction if failed
        if os.path.exists(extract_to_abs):
            try:
                shutil.rmtree(extract_to_abs)
            except OSError:
                pass
        raise

def extract_zip(
    zip_path: str,
    extract_to: str,
    max_entries: int = DEFAULT_MAX_ARCHIVE_ENTRIES,
    max_total_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES
) -> bool:
    """
    Safely extracts a ZIP archive with traversal, symlink, and zip-bomb protections.
    """
    os.makedirs(extract_to, exist_ok=True)
    extract_to_abs = os.path.abspath(extract_to)

    entry_count = 0
    total_uncompressed_bytes = 0

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            infolist = zip_ref.infolist()
            for member in infolist:
                entry_count += 1
                if entry_count > max_entries:
                    raise ValueError(f"Zip bomb blocked: archive exceeds entry limit ({max_entries}).")

                # Block symlinks (encoded in external_attr high 16 bits on Unix)
                mode = (member.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise ValueError(f"Unsafe ZIP member detected (symlink): {member.filename}")

                raw_name = member.filename.replace("\\", "/").strip()
                if raw_name.startswith("/") or raw_name.startswith("\\") or ":" in raw_name:
                    raise ValueError(f"Absolute path in ZIP member: {member.filename}")

                parts = [p for p in raw_name.split("/") if p]
                if any(p == ".." or p == "." for p in parts):
                    raise ValueError(f"Path traversal '..' in ZIP member: {member.filename}")

                if not parts:
                    continue

                target_path = os.path.abspath(os.path.join(extract_to_abs, *parts))
                if not is_safe_path(extract_to_abs, target_path):
                    raise ValueError(f"Zip Slip path traversal blocked: {member.filename}")

                # Check declared header size upfront as an early guard
                if total_uncompressed_bytes + member.file_size > max_total_bytes:
                    raise ValueError(f"ZIP bomb blocked: uncompressed size exceeds {max_total_bytes} bytes.")

                # Extract safely with streaming byte tracking
                is_dir = member.filename.endswith("/") or member.filename.endswith("\\")
                if is_dir:
                    os.makedirs(target_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with zip_ref.open(member) as src, open(target_path, "wb") as dst:
                        written = _safe_stream_copy(src, dst, total_uncompressed_bytes, max_total_bytes)
                        total_uncompressed_bytes += written

        return True
    except Exception as e:
        print(f"Zip extraction failed: {e}")
        if os.path.exists(extract_to_abs):
            try:
                shutil.rmtree(extract_to_abs)
            except OSError:
                pass
        raise

def save_uploaded_file(file: UploadFile, scan_id: str) -> tuple[str, bool]:
    """
    Saves an uploaded file (ZIP or PY) to a temporary directory.
    Returns a tuple: (target_path_or_dir, is_zip)
    """
    ensure_temp_dir()
    scan_dir = get_scan_dir(scan_id)
    os.makedirs(scan_dir, exist_ok=True)
    
    filename = os.path.basename(file.filename)
    temp_file_path = os.path.join(scan_dir, filename)
    
    if not is_safe_path(scan_dir, temp_file_path):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid file path sequence.")
        
    with open(temp_file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
        
    is_zip = filename.endswith(".zip")
    
    if is_zip:
        extract_dir = os.path.join(scan_dir, "extracted")
        try:
            extract_zip(temp_file_path, extract_dir)
            success = True
        except Exception:
            success = False
            
        try:
            os.remove(temp_file_path)
        except OSError:
            pass
        return (extract_dir, True) if success else (scan_dir, True)
    else:
        return temp_file_path, False

def save_pasted_code(code: str, scan_id: str, extension: str = "py") -> str:
    """
    Saves pasted text into a file named 'pasted_code.<extension>' under the scan directory.
    Returns the path to the saved source file.
    """
    ensure_temp_dir()
    scan_dir = get_scan_dir(scan_id)
    os.makedirs(scan_dir, exist_ok=True)
    
    if extension not in ("py", "js", "jsx", "ts", "tsx", "go"):
        extension = "py"
        
    file_path = os.path.join(scan_dir, f"pasted_code.{extension}")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code)
        
    return file_path

def delete_scan_dir(scan_id: str):
    """Deletes the temporary directory associated with the scan."""
    scan_dir = get_scan_dir(scan_id)
    if os.path.exists(scan_dir):
        try:
            shutil.rmtree(scan_dir)
        except OSError as e:
            print(f"Error cleaning up scan directory {scan_dir}: {e}")

def cleanup_orphaned_temp_dirs(max_age_seconds: int = 3600):
    """Removes leftover scan directories in TEMP_DIR older than max_age_seconds."""
    if not os.path.exists(TEMP_DIR):
        return
    import time
    now = time.time()
    for entry in os.listdir(TEMP_DIR):
        entry_path = os.path.join(TEMP_DIR, entry)
        if os.path.isdir(entry_path):
            try:
                mtime = os.path.getmtime(entry_path)
                if now - mtime > max_age_seconds:
                    shutil.rmtree(entry_path, ignore_errors=True)
            except OSError:
                pass
