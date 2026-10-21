import re
import hashlib

# Pattern to detect and strip common line-number prefixes in code snippets
# Examples handled:
# "12: cursor.execute(...)"
# " 12 | cursor.execute(...)"
# "125 -> eval(cmd)"
# "> 45 | vulnerable_func()"
LINE_NUMBER_PREFIX_REGEX = re.compile(r'^\s*(?:[>*-]\s*)?\d+\s*[:|>-]\s*')

def normalize_code_snippet(code_snippet: str) -> str:
    """
    Normalizes a code snippet by:
    1. Stripping leading line numbers / prefix decorations from each line.
    2. Stripping leading and trailing whitespace per line.
    3. Filtering out empty lines.
    4. Joining non-empty lines with a single newline.
    """
    if not code_snippet:
        return ""

    normalized_lines = []
    for raw_line in code_snippet.splitlines():
        # Remove line-number prefixes if present
        clean_line = LINE_NUMBER_PREFIX_REGEX.sub('', raw_line)
        clean_line = clean_line.strip()
        if clean_line:
            normalized_lines.append(clean_line)

    return "\n".join(normalized_lines)

def normalize_filepath(filepath: str) -> str:
    """
    Normalizes a file path to a clean, canonical relative path:
    - Replaces backslashes with forward slashes
    - Strips leading './' or '/'
    - Strips leading/trailing whitespace
    """
    if not filepath:
        return ""
    path = filepath.strip().replace("\\", "/")
    # Remove leading './' or '/'
    while path.startswith("./") or path.startswith("/"):
        path = path[2:] if path.startswith("./") else path[1:]
    return path

def compute_fingerprint(rule_id_or_issue, filepath: str = "", code_snippet: str = "") -> str:
    """
    Computes a deterministic SHA-256 fingerprint for a static analysis issue.
    
    Supports either:
      - compute_fingerprint(issue_dict)
      - compute_fingerprint(rule_id, filepath, code_snippet)
    
    Formula:
        sha256(rule_id + ":" + normalized_relative_filepath + ":" + normalized_code_snippet)
    
    Properties:
    - Stable when lines are inserted above or below the finding (line numbers excluded).
    - Changes when the vulnerable code content itself is modified.
    - Path separator independent (Windows vs Unix).
    """
    if isinstance(rule_id_or_issue, dict):
        rule_id = rule_id_or_issue.get("rule_id", "") or rule_id_or_issue.get("ruleId", "")
        filepath = rule_id_or_issue.get("filepath", "") or rule_id_or_issue.get("file", "")
        code_snippet = rule_id_or_issue.get("code_snippet", "") or rule_id_or_issue.get("snippet", "")
    else:
        rule_id = str(rule_id_or_issue or "")

    norm_rule = (rule_id or "").strip().lower()
    norm_path = normalize_filepath(filepath)
    norm_snippet = normalize_code_snippet(code_snippet)

    raw_payload = f"{norm_rule}:{norm_path}:{norm_snippet}".encode("utf-8")
    return hashlib.sha256(raw_payload).hexdigest()

