"""
Minimal Context Extraction and Secret Redaction for Auto-Fix.
Extracts only enclosing function AST nodes and relevant imports. Never sends whole repositories.
"""
import ast
import re
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

SECRET_PATTERNS = [
    # AWS Access Key ID
    (re.compile(r'\b(AKIA[0-9A-Z]{16})\b'), '[REDACTED_AWS_KEY]'),
    # GitHub Personal Access Token
    (re.compile(r'\b(ghp_[a-zA-Z0-9]{36})\b'), '[REDACTED_GITHUB_TOKEN]'),
    (re.compile(r'\b(github_pat_[a-zA-Z0-9_]{82})\b'), '[REDACTED_GITHUB_PAT]'),
    # Stripe Secret Key
    (re.compile(r'\b(sk_(?:live|test)_[0-9a-zA-Z]{24,})\b'), '[REDACTED_STRIPE_KEY]'),
    # Private Key blocks
    (re.compile(r'-----BEGIN (?:[A-Z ]+)PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z ]+)PRIVATE KEY-----'), '[REDACTED_PRIVATE_KEY]'),
    # Generic password / token / secret assignments
    (re.compile(r'((?:password|passwd|secret|api_key|apikey|bearer_token|auth_token)\s*[:=]\s*["\'])([^"\']{8,})(["\'])', re.IGNORECASE), r'\1[REDACTED_SECRET]\3')
]

def redact_secrets(text: str) -> str:
    """Detects and redacts secrets in text before passing to LLM."""
    redacted = text
    for pattern, repl in SECRET_PATTERNS:
        redacted = pattern.sub(repl, redacted)
    return redacted

@dataclass
class MinimalContext:
    filepath: str
    language: str
    function_name: str
    start_line: int
    end_line: int
    function_code: str
    redacted_code: str
    imports: List[str] = field(default_factory=list)
    delimited_prompt_block: str = ""

def detect_language(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".py":
        return "python"
    elif ext in (".js", ".jsx", ".mjs", ".cjs"):
        return "javascript"
    elif ext in (".ts", ".tsx"):
        return "typescript"
    elif ext == ".go":
        return "go"
    return "unknown"

def extract_minimal_context(file_content: str, filepath: str, line_number: int) -> MinimalContext:
    """
    Extracts only the enclosing function range, relevant imports, and applies secret redaction.
    Falls back gracefully if the code is not enclosed in a standard function.
    """
    lang = detect_language(filepath)
    lines = file_content.splitlines()
    total_lines = len(lines)
    clamped_line = max(1, min(line_number, total_lines))

    if lang == "python":
        context = _extract_python_context(file_content, lines, filepath, clamped_line)
    elif lang in ("javascript", "typescript"):
        context = _extract_c_style_context(lines, filepath, clamped_line, lang, is_go=False)
    elif lang == "go":
        context = _extract_c_style_context(lines, filepath, clamped_line, lang, is_go=True)
    else:
        context = _extract_fallback_window(lines, filepath, clamped_line, lang)

    redacted = redact_secrets(context.function_code)
    context.redacted_code = redacted

    context.delimited_prompt_block = (
        f'<untrusted_code_to_fix language="{lang}" file="{filepath}" '
        f'function="{context.function_name}" start_line="{context.start_line}" end_line="{context.end_line}">\n'
        f'{redacted}\n'
        f'</untrusted_code_to_fix>'
    )
    return context

def _extract_python_context(content: str, lines: List[str], filepath: str, line_no: int) -> MinimalContext:
    imports: List[str] = []
    try:
        tree = ast.parse(content)
        # 1. Collect top-level imports
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imp_str = ast.get_source_segment(content, node)
                if imp_str:
                    imports.append(imp_str.strip())

        # 2. Find target enclosing function
        best_node = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = getattr(node, "lineno", 1)
                end = getattr(node, "end_lineno", start)
                if start <= line_no <= end:
                    if best_node is None:
                        best_node = node
                    else:
                        # Pick deepest (smallest range) enclosing function
                        curr_span = getattr(best_node, "end_lineno", 1) - getattr(best_node, "lineno", 1)
                        new_span = end - start
                        if new_span < curr_span:
                            best_node = node

        if best_node:
            start = best_node.lineno
            end = best_node.end_lineno
            fn_code = "\n".join(lines[start - 1 : end])
            return MinimalContext(
                filepath=filepath,
                language="python",
                function_name=best_node.name,
                start_line=start,
                end_line=end,
                function_code=fn_code,
                redacted_code=fn_code,
                imports=imports
            )
    except Exception:
        pass

    return _extract_fallback_window(lines, filepath, line_no, "python", imports=imports)

def _extract_c_style_context(
    lines: List[str],
    filepath: str,
    line_no: int,
    lang: str,
    is_go: bool = False
) -> MinimalContext:
    """
    Extracts enclosing function for C-style syntaxes (JS/TS and Go) using block balance.
    """
    imports: List[str] = []
    for line in lines[:30]: # First 30 lines for top-level imports
        sline = line.strip()
        if is_go:
            if sline.startswith("import") or sline.startswith("package"):
                imports.append(sline)
        else:
            if sline.startswith("import ") or sline.startswith("const ") and "require(" in sline:
                imports.append(sline)

    fn_pattern = re.compile(r'^\s*(?:async\s+)?(?:export\s+)?(?:default\s+)?(?:function\s+([a-zA-Z0-9_$]+)|(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\()') if not is_go else re.compile(r'^\s*func\s+(?:\([^)]+\)\s+)?([a-zA-Z0-9_]+)\s*\(')

    # Scan upwards from target line to find function declaration
    start_line = None
    fn_name = "anonymous"
    for i in range(line_no - 1, -1, -1):
        line_text = lines[i]
        m = fn_pattern.search(line_text)
        if m:
            start_line = i + 1
            fn_name = m.group(1) or m.group(2) or "enclosing_function"
            break

    if start_line is not None:
        # Scan forward from start_line matching braces '{' and '}'
        brace_count = 0
        end_line = start_line
        found_open = False
        for i in range(start_line - 1, len(lines)):
            line_text = lines[i]
            for ch in line_text:
                if ch == '{':
                    brace_count += 1
                    found_open = True
                elif ch == '}':
                    brace_count -= 1
                    if found_open and brace_count <= 0:
                        end_line = i + 1
                        break
            if found_open and brace_count <= 0:
                break

        if end_line >= line_no:
            fn_code = "\n".join(lines[start_line - 1 : end_line])
            return MinimalContext(
                filepath=filepath,
                language=lang,
                function_name=fn_name,
                start_line=start_line,
                end_line=end_line,
                function_code=fn_code,
                redacted_code=fn_code,
                imports=imports
            )

    return _extract_fallback_window(lines, filepath, line_no, lang, imports=imports)

def _extract_fallback_window(
    lines: List[str],
    filepath: str,
    line_no: int,
    lang: str,
    imports: Optional[List[str]] = None
) -> MinimalContext:
    """Window fallback when no formal enclosing function definition was identified."""
    total = len(lines)
    start = max(1, line_no - 10)
    end = min(total, line_no + 10)
    code = "\n".join(lines[start - 1 : end])
    return MinimalContext(
        filepath=filepath,
        language=lang,
        function_name=f"scope_line_{line_no}",
        start_line=start,
        end_line=end,
        function_code=code,
        redacted_code=code,
        imports=imports or []
    )
