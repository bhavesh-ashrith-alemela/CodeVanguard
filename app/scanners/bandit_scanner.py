import os
from app.scanners.parser import get_code_snippet, normalize_severity
from app.scanners.runner import execute_scanner_process

class BanditScanner:
    def __init__(self, target_dir: str):
        self.target_dir = os.path.abspath(target_dir)

    async def scan(self) -> list:
        """
        Executes Bandit asynchronously and returns a list of parsed issues.
        """
        args = ["-f", "json", "-r", "-x", "node_modules,.git,.venv,.next,venv,env,temp", self.target_dir]
        data = await execute_scanner_process("bandit", args, timeout=60.0)
        
        issues = []
        if not data:
            return issues
            
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
