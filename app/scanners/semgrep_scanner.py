import os
from app.scanners.parser import get_code_snippet, normalize_severity
from app.scanners.runner import execute_scanner_process

class SemgrepScanner:
    def __init__(self, target_dir: str):
        self.target_dir = os.path.abspath(target_dir)

    async def scan(self) -> list:
        """
        Executes Semgrep asynchronously and returns a list of parsed issues.
        """
        rules_path = os.path.join(os.path.dirname(__file__), "rules.yaml")
        args = [
            "scan",
            f"--config={rules_path}",
            "--json",
            "--quiet",
            "--metrics=off",
            "--no-git-ignore",
            self.target_dir
        ]
        
        data = await execute_scanner_process("semgrep", args, timeout=60.0)
        
        issues = []
        if not data:
            return issues
            
        # Parse execution / parsing / rule errors
        errors = data.get("errors", [])
        for err in errors:
            err_type = str(err.get("type", ""))
            is_syntax = ("parsing" in err_type.lower() or "syntax" in err_type.lower() or "parsing" in str(err.get("message", "")).lower()) and "rule" not in err_type.lower()
            
            raw_path = err.get("path", "")
            if not raw_path and err.get("spans"):
                raw_path = err["spans"][0].get("file", "")
            
            if raw_path:
                if not os.path.isabs(raw_path):
                    full_path = os.path.join(self.target_dir, raw_path)
                else:
                    full_path = raw_path
                rel_path = os.path.relpath(os.path.abspath(full_path), self.target_dir)
                rel_path = rel_path.replace("\\", "/")
            else:
                rel_path = "scan"
                full_path = ""
            
            spans = err.get("spans", [])
            line_no = 1
            col_no = 0
            if spans:
                start_info = spans[0].get("start", {})
                line_no = start_info.get("line", 1)
                col_no = start_info.get("col", 0)
            
            message = err.get("message", "Semgrep scanner error")
            message = message.replace(self.target_dir, ".")
            if raw_path:
                message = message.replace(raw_path, ".")
            
            snippet = get_code_snippet(full_path, line_no) if full_path else ""
            if not snippet:
                snippet = f"Error Type: {err_type}\nDetails: {message}"
                
            issues.append({
                "scanner": "semgrep",
                "rule_id": "SYNTAX_ERROR" if is_syntax else "SCANNER_ERROR",
                "severity": "high",
                "message": f"Semgrep {err_type or 'Error'}: {message}",
                "filepath": rel_path,
                "line_number": line_no,
                "col_number": col_no,
                "code_snippet": snippet
            })

        results = data.get("results", [])
        for res in results:
            raw_path = res.get("path", "")
            if not os.path.isabs(raw_path):
                full_path = os.path.join(self.target_dir, raw_path)
            else:
                full_path = raw_path
                
            rel_path = os.path.relpath(os.path.abspath(full_path), self.target_dir)
            rel_path = rel_path.replace("\\", "/")
            
            start_info = res.get("start", {})
            line_no = start_info.get("line", 1)
            col_no = start_info.get("col", 0)
            
            check_id = res.get("check_id", "Unknown")
            
            extra = res.get("extra", {})
            raw_severity = extra.get("severity", "WARNING")
            message = extra.get("message", "")
            
            # Retrieve clean snippet
            snippet = get_code_snippet(full_path, line_no)
            if not snippet:
                snippet = extra.get("lines", "")
                
            issues.append({
                "scanner": "semgrep",
                "rule_id": check_id,
                "severity": normalize_severity("semgrep", raw_severity, check_id),
                "message": message,
                "filepath": rel_path,
                "line_number": line_no,
                "col_number": col_no,
                "code_snippet": snippet
            })
            
        return issues
