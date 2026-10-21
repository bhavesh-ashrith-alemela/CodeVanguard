"""
Secure Git Bare Clone and History Inspection Module.

Guarantees:
1. Zero token leakage in command line arguments or process listings (ps aux)
   via an ephemeral GIT_CONFIG_GLOBAL with 0600 permissions.
2. Depth and time constraints (HISTORY_MAX_COMMITS, HISTORY_MAX_DAYS).
3. Disk cap enforcement for ephemeral container environments (MAX_GIT_DIR_BYTES).
4. Reliable cleanup in finally blocks.
"""
import os
import re
import time
import shutil
import tempfile
import asyncio
import subprocess
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Generator, Optional

logger = logging.getLogger(__name__)

HISTORY_MAX_COMMITS = int(os.environ.get("HISTORY_MAX_COMMITS", "500"))
HISTORY_MAX_DAYS = int(os.environ.get("HISTORY_MAX_DAYS", "90"))
# Default disk cap: 200 MB
MAX_GIT_DIR_BYTES = int(os.environ.get("MAX_GIT_DIR_BYTES", str(200 * 1024 * 1024)))

SAFE_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")
SAFE_TOKEN_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.=]+$")

class DiskLimitExceededError(RuntimeError):
    """Raised when repository clone exceeds the allowed ephemeral disk budget."""
    pass

def validate_git_identifier(name: str, label: str = "identifier") -> str:
    """Validates that a GitHub owner or repository name matches safe pattern without option injection."""
    if not name or not SAFE_IDENTIFIER_PATTERN.match(name) or name.startswith("-") or name in (".", ".."):
        raise ValueError(f"Invalid git {label}: {name!r}")
    return name

def get_directory_size(path: str) -> int:
    """Calculates total size of all files in a directory in bytes."""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat(follow_symlinks=False).st_size
            elif entry.is_dir(follow_symlinks=False):
                total += get_directory_size(entry.path)
    except (OSError, FileNotFoundError):
        pass
    return total

def create_isolated_git_config(auth_token: Optional[str] = None) -> str:
    """
    Creates a temporary gitconfig file with 0600 permissions containing
    the Authorization header. This completely isolates the token from
    command-line arguments, environment variable dumps in other processes,
    and 'ps aux' listings.
    """
    fd, path = tempfile.mkstemp(prefix="cv_gitcfg_", suffix=".conf")
    os.close(fd)
    os.chmod(path, 0o600)

    if auth_token:
        # Prevent CRLF and control character injection into git configuration
        if "\r" in auth_token or "\n" in auth_token or not SAFE_TOKEN_PATTERN.match(auth_token):
            raise ValueError("Invalid authorization token format: illegal control characters detected.")
        content = (
            '[http "https://github.com/"]\n'
            f'\textraHeader = Authorization: Bearer {auth_token}\n'
            '[credential]\n'
            '\thelper = ""\n'
            '[core]\n'
            '\tprotectNTFS = true\n'
            '\tprotectHFS = true\n'
        )
    else:
        content = (
            '[core]\n'
            '\tprotectNTFS = true\n'
            '\tprotectHFS = true\n'
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return path

def _run_git_clone_with_disk_guard(
    cmd: list,
    env: dict,
    watch_dir: str,
    max_disk_bytes: int,
    timeout: int = 120
) -> subprocess.CompletedProcess:
    """
    Executes git clone while actively monitoring disk usage every 0.5s.
    Kills the process immediately if the directory exceeds the ephemeral disk budget.
    """
    start_time = time.time()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True
    )

    try:
        while proc.poll() is None:
            if time.time() - start_time > timeout:
                proc.kill()
                raise subprocess.TimeoutExpired(cmd, timeout)

            # Check disk usage during active download
            curr_size = get_directory_size(watch_dir)
            if curr_size > max_disk_bytes:
                proc.kill()
                proc.wait(timeout=5)
                raise DiskLimitExceededError(
                    f"Repository clone exceeded disk budget during download ({curr_size // (1024*1024)}MB > {max_disk_bytes // (1024*1024)}MB)."
                )
            time.sleep(0.5)

        stdout, stderr = proc.communicate()
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    except Exception:
        if proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
        raise

@contextmanager
def secure_bare_clone(
    owner: str,
    repo_name: str,
    auth_token: Optional[str] = None,
    max_commits: int = HISTORY_MAX_COMMITS,
    max_days: int = HISTORY_MAX_DAYS,
    max_disk_bytes: int = MAX_GIT_DIR_BYTES
) -> Generator[str, None, None]:
    """
    Context manager that bare-clones a GitHub repository with:
    - Input validation against option/URL injection
    - Token isolation (GIT_CONFIG_GLOBAL with 0600 permissions, never in CLI args)
    - Non-interactive terminal execution (GIT_TERMINAL_PROMPT=0)
    - Shallow depth and date limits
    - Active disk consumption cap monitoring
    - Guaranteed cleanup in a finally block
    """
    validate_git_identifier(owner, "owner")
    validate_git_identifier(repo_name, "repository name")

    temp_dir = tempfile.mkdtemp(prefix="cv_bare_")
    bare_repo_dir = os.path.join(temp_dir, "repo.git")
    cfg_path = None

    try:
        # Pre-check available disk space
        try:
            free_bytes = shutil.disk_usage(temp_dir).free
            if free_bytes < max_disk_bytes:
                raise DiskLimitExceededError(
                    f"Insufficient disk space for bare clone: {free_bytes // (1024*1024)}MB free, requires {max_disk_bytes // (1024*1024)}MB."
                )
        except (OSError, AttributeError):
            pass

        cfg_path = create_isolated_git_config(auth_token)

        # Build git clone command with shallow constraints
        # Strictly uses HTTPS URL with NO credentials in URL
        clone_url = f"https://github.com/{owner}/{repo_name}.git"

        since_date = (datetime.now(timezone.utc) - timedelta(days=max_days)).strftime("%Y-%m-%d")
        
        cmd = [
            "git", "clone", "--bare",
            f"--depth={max_commits}",
            f"--shallow-since={since_date}",
            "--filter=blob:limit=1m",  # Partial clone: skip enormous binary blobs > 1MB
            clone_url,
            bare_repo_dir
        ]

        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
            "GIT_CONFIG_GLOBAL": cfg_path,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",  # Prevent blocking on stdin prompt
            "HOME": temp_dir,
            "LC_ALL": "C.UTF-8"
        }

        # Run clone with active disk monitoring and 120s timeout
        res = _run_git_clone_with_disk_guard(
            cmd=cmd,
            env=env,
            watch_dir=temp_dir,
            max_disk_bytes=max_disk_bytes,
            timeout=120
        )

        if res.returncode != 0:
            # Mask any possible occurrence of token in stderr before logging
            err_msg = res.stderr or "Unknown git clone error"
            if auth_token:
                err_msg = err_msg.replace(auth_token, "[REDACTED]")
            # Retry without --shallow-since if git server complains about shallow-since / shallow combo
            if "fatal" in err_msg.lower() and "--shallow-since" in err_msg.lower():
                retry_cmd = [
                    "git", "clone", "--bare",
                    f"--depth={max_commits}",
                    clone_url,
                    bare_repo_dir
                ]
                retry_res = _run_git_clone_with_disk_guard(
                    cmd=retry_cmd,
                    env=env,
                    watch_dir=temp_dir,
                    max_disk_bytes=max_disk_bytes,
                    timeout=120
                )
                if retry_res.returncode != 0:
                    r_err = retry_res.stderr or "Git clone retry failed"
                    if auth_token:
                        r_err = r_err.replace(auth_token, "[REDACTED]")
                    raise RuntimeError(f"Git bare clone failed: {r_err.strip()}")
            else:
                raise RuntimeError(f"Git bare clone failed: {err_msg.strip()}")

        # Final verification of disk budget
        dir_size = get_directory_size(bare_repo_dir)
        if dir_size > max_disk_bytes:
            raise DiskLimitExceededError(
                f"Repository clone size ({dir_size // (1024*1024)}MB) exceeds limit of ({max_disk_bytes // (1024*1024)}MB)."
            )

        yield bare_repo_dir

    finally:
        # Securely remove temporary config containing token
        if cfg_path and os.path.exists(cfg_path):
            try:
                os.remove(cfg_path)
            except OSError:
                pass

        # Purge bare git directory from ephemeral disk
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
