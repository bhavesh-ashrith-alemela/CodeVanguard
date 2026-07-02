import os
import asyncio
import json

async def execute_scanner_process(venv_binary_name: str, args: list, timeout: float = 60.0) -> dict:
    """
    Locates the scanner binary inside .venv (checking Windows and Linux paths),
    executes the subprocess asynchronously, enforces a timeout limit,
    decodes stdout, and safely parses the JSON output.
    """
    # Resolve virtualenv executable path
    venv_bin = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".venv", "Scripts", f"{venv_binary_name}.exe")
    if not os.path.exists(venv_bin):
        venv_bin_linux = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".venv", "bin", venv_binary_name)
        if os.path.exists(venv_bin_linux):
            venv_bin = venv_bin_linux
        else:
            venv_bin = venv_binary_name

    cmd = [venv_bin] + args
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
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
