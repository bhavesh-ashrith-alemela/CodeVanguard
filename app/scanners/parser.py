import os

def get_code_snippet(filepath: str, line_number: int, context_lines: int = 3) -> str:
    """
    Safely reads a file and extracts a code snippet centered on line_number.
    """
    if not os.path.exists(filepath):
        return ""
        
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return ""
        
    if not lines or line_number <= 0 or line_number > len(lines):
        return ""
        
    start = max(0, line_number - 1 - context_lines)
    end = min(len(lines), line_number + context_lines)
    
    snippet_lines = []
    for idx in range(start, end):
        ln = idx + 1
        line_content = lines[idx].rstrip('\n')
        # Highlight the target line with a marker
        marker = "-> " if ln == line_number else "   "
        snippet_lines.append(f"{marker}{ln:4d} | {line_content}")
        
    return "\n".join(snippet_lines)

def normalize_severity(scanner: str, raw_severity: str, rule_id: str) -> str:
    """
    Normalizes severity flags from Bandit and Semgrep into: 'critical', 'high', 'medium', 'low'.
    Upgrades critical vulnerability classes (SQLi, RCE, Secrets) to 'critical'.
    """
    raw_sev = raw_severity.upper().strip()
    rule_lower = rule_id.lower()
    
    # Base mapping
    if scanner == "bandit":
        if raw_sev == "HIGH":
            sev = "high"
        elif raw_sev == "MEDIUM":
            sev = "medium"
        else:
            sev = "low"
    else:  # semgrep
        if raw_sev == "ERROR":
            sev = "high"
        elif raw_sev == "WARNING":
            sev = "medium"
        else:
            sev = "low"
            
    # Upgrade specific high-risk items to critical
    critical_indicators = [
        "b608", "sql-injection", "sqlite-execute", "psycopg2-execute", "sqlalchemy-execute", # SQL Injection
        "b301", "pickle", "deserialization", "marshal",                                     # Remote Code Execution / unsafe load
        "b602", "command-injection", "subprocess-shell-true",                               # Command Injection
        "b105", "hardcoded-password", "secret", "private-key", "api-key"                    # Hardcoded Credentials
    ]
    
    if sev == "high":
        for indicator in critical_indicators:
            if indicator in rule_lower:
                return "critical"
                
    return sev
