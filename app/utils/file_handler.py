import os
import zipfile
import shutil
from fastapi import UploadFile

TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "temp")

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

def extract_zip(zip_path: str, extract_to: str) -> bool:
    """
    Safely extracts a ZIP archive, verifying all paths.
    Returns True if extraction is successful, False otherwise.
    """
    os.makedirs(extract_to, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.infolist():
                # Get the absolute target path for this member
                target_path = os.path.join(extract_to, member.filename)
                
                # Check for Zip Slip
                if not is_safe_path(extract_to, target_path):
                    print(f"Warning: Blocked unsafe path extraction: {member.filename}")
                    continue
                    
                # Extract if it's safe
                zip_ref.extract(member, extract_to)
        return True
    except Exception as e:
        print(f"Zip extraction failed: {e}")
        return False

def save_uploaded_file(file: UploadFile, scan_id: str) -> tuple[str, bool]:
    """
    Saves an uploaded file (ZIP or PY) to a temporary directory.
    Returns a tuple: (target_path_or_dir, is_zip)
    """
    ensure_temp_dir()
    scan_dir = get_scan_dir(scan_id)
    os.makedirs(scan_dir, exist_ok=True)
    
    filename = file.filename
    temp_file_path = os.path.join(scan_dir, filename)
    
    # Write file to disk
    with open(temp_file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
        
    is_zip = filename.endswith(".zip")
    
    if is_zip:
        extract_dir = os.path.join(scan_dir, "extracted")
        success = extract_zip(temp_file_path, extract_dir)
        # Remove the raw zip file to save space and avoid scanning the ZIP binary
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
    
    # Sanitize extension
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
