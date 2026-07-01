import json
import os
import asyncio
from app.scanners.parser import get_code_snippet, normalize_severity

class BanditScanner:
    def __init__(self, target_dir: str):
        self.target_dir = os.path.abspath(target_dir)

    async def scan(self) -> list:
        """
        Executes Bandit asynchronously and returns a list of parsed issues.
        """
        # Bandit executable location in the virtualenv
        # Windows: .venv\Scripts\bandit.exe
        # Fallback to just "bandit" if virtualenv is activated or in PATH
        venv_bin = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".venv", "Scripts", "bandit.exe")
        if not os.path.exists(venv_bin):
            # Check Linux path structure
            venv_bin_linux = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".venv", "bin", "bandit")
            if os.path.exists(venv_bin_linux):
                venv_bin = venv_bin_linux
            else:
                venv_bin = "bandit"

        # Construct bandit command
        # -f json: format as JSON
        # -r: recursive scan
        # target_dir: directory to scan
        cmd = [venv_bin, "-f", "json", "-r", "-x", "node_modules,.git,.venv,.next,venv,env,temp", self.target_dir]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            # Bandit returns exit code 1 if issues are found, and 0 if none. So we don't strictly check for process.returncode != 0.
            output_str = stdout.decode("utf-8", errors="ignore").strip()
            if not output_str:
                return []
                
            try:
                data = json.loads(output_str)
            except json.JSONDecodeError:
                # In case bandit outputs warning/error text before the JSON
                # Try to find the start of the JSON block
                json_start = output_str.find("{")
                if json_start != -1:
                    data = json.loads(output_str[json_start:])
                else:
                    return []
                    
            issues = []
            
            # Parse execution / parsing errors
            errors = data.get("errors", [])
            for err in errors:
                raw_path = err.get("filename", "")
                rel_path = os.path.relpath(os.path.abspath(raw_path), self.target_dir) if raw_path else "scan"
                rel_path = rel_path.replace("\\", "/")
                reason = err.get("reason", "Unknown Bandit scanner error")
                
                issues.append({
                    "scanner": "bandit",
                    "rule_id": "SYNTAX_ERROR" if "syntax" in reason.lower() else "SCANNER_ERROR",
                    "severity": "high",
                    "message": f"Bandit Error: {reason}",
                    "filepath": rel_path,
                    "line_number": 1,
                    "col_number": 0,
                    "code_snippet": f"File path: {rel_path}\nError details: {reason}"
                })

            results = data.get("results", [])
            for res in results:
                raw_path = res.get("filename", "")
                # Normalize file path relative to target_dir
                rel_path = os.path.relpath(os.path.abspath(raw_path), self.target_dir)
                # Ensure Windows paths are formatted nicely with forward slashes for the UI
                rel_path = rel_path.replace("\\", "/")
                
                line_no = res.get("line_number", 1)
                rule_id = res.get("test_id", "Unknown")
                raw_severity = res.get("issue_severity", "low")
                message = res.get("issue_text", "")
                
                # Fetch fresh code snippet with contextual line numbers
                snippet = get_code_snippet(raw_path, line_no)
                if not snippet:
                    snippet = res.get("code", "")
                    
                issues.append({
                    "scanner": "bandit",
                    "rule_id": rule_id,
                    "severity": normalize_severity("bandit", raw_severity, rule_id),
                    "message": message,
                    "filepath": rel_path,
                    "line_number": line_no,
                    "col_number": 0,
                    "code_snippet": snippet
                })
                
            return issues
            
        except Exception as e:
            # Return empty list and log or print error in actual application
            print(f"Bandit execution error: {e}")
            return []
