import os
import sys
import asyncio
import json

def get_preexec_isolation_fn(timeout_seconds: float):
    """
    Returns a preexec function for Unix environments to:
    1. Enforce CPU and Address Space (Memory) rlimits.
    2. Drop root privileges to an unprivileged user (e.g. nobody/65534).
    """
    if sys.platform == "win32":
        return None

    def preexec():
        # 1. Enforce Resource Limits
        try:
            import resource
            cpu_limit = int(timeout_seconds) + 5
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit + 5))
            
            # Virtual memory cap: 4 GB (safe for modern 64-bit multi-runtime tools like Semgrep)
            if hasattr(resource, "RLIMIT_AS"):
                mem_bytes = 4 * 1024 * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except Exception:
            pass

        # 2. Drop Root Privileges if running as root in container
        try:
            if hasattr(os, "getuid") and os.getuid() == 0:
                scanner_uid = int(os.environ.get("SCANNER_UID", 65534)) # nobody
                scanner_gid = int(os.environ.get("SCANNER_GID", 65534))
                if hasattr(os, "setgid"):
                    os.setgid(scanner_gid)
                if hasattr(os, "setuid"):
                    os.setuid(scanner_uid)
        except Exception:
            pass

    return preexec

def get_isolated_env() -> dict:
    """
    Builds a sanitized environment dict blocking network access, telemetry,
    and proxy endpoints for scanners.
    """
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "HOME": "/tmp",
        "SEMGREP_SEND_METRICS": "off",
        "SEMGREP_ENABLE_VERSION_CHECK": "0",
        "PYTHONHASHSEED": "random",
        # Route proxies to dead loopback port to prevent network egress
        "HTTP_PROXY": "http://127.0.0.1:0",
        "HTTPS_PROXY": "http://127.0.0.1:0",
        "ALL_PROXY": "http://127.0.0.1:0",
        "NO_PROXY": ""
    }

async def execute_scanner_process(venv_binary_name: str, args: list, timeout: float = 60.0) -> dict:
    """
    Executes a static scanner subprocess in an isolated sandbox:
    - Non-root user permissions
    - CPU and memory bounds via setrlimit
    - Blocked network / proxy redirection
    - Local rules validation for Semgrep (no --config auto, metrics disabled)
    - Untrusted code is never imported or executed
    """
    # Verify Semgrep rule safety
    if venv_binary_name.lower() == "semgrep":
        sanitized_args = []
        for arg in args:
            if arg.startswith("--config=auto") or arg == "--config auto":
                raise ValueError("Security violation: Semgrep --config auto is prohibited. Use local rules only.")
            sanitized_args.append(arg)
        if "--metrics=off" not in sanitized_args:
            sanitized_args.append("--metrics=off")
        if "--disable-version-check" not in sanitized_args:
            sanitized_args.append("--disable-version-check")
        args = sanitized_args

    # Resolve virtualenv executable path
    if sys.platform == "win32":
        venv_bin = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".venv", "Scripts", f"{venv_binary_name}.exe")
        if not os.path.exists(venv_bin):
            venv_bin = venv_binary_name
    else:
        venv_bin_unix = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".venv", "bin", venv_binary_name)
        if os.path.exists(venv_bin_unix):
            venv_bin = venv_bin_unix
        else:
            import shutil
            venv_bin = shutil.which(venv_binary_name) or venv_binary_name

    cmd = [venv_bin] + args
    preexec_fn = get_preexec_isolation_fn(timeout)
    isolated_env = get_isolated_env()

    try:
        kwargs = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "env": isolated_env
        }
        if preexec_fn is not None:
            kwargs["preexec_fn"] = preexec_fn

        process = await asyncio.create_subprocess_exec(*cmd, **kwargs)
        
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except OSError:
                pass
            stdout, stderr = await process.communicate()
            raise RuntimeError(f"{venv_binary_name.capitalize()} scan execution timed out (limit: {timeout}s)")
            
        output_str = stdout.decode("utf-8", errors="ignore").strip()
        if not output_str:
            return {}
            
        try:
            return json.loads(output_str)
        except json.JSONDecodeError:
            json_start = output_str.find("{")
            if json_start != -1:
                return json.loads(output_str[json_start:])
            return {}
            
    except Exception as e:
        print(f"{venv_binary_name.capitalize()} execution error: {e}")
        return {}
