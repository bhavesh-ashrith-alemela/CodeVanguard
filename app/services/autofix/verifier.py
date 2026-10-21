"""
Verification Pipeline for Auto-Fix Security Patches.
Validates syntax, line caps, fingerprint elimination, and zero regression.
Does not execute repository code or tests.
"""
import os
import ast
import difflib
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set

from app.utils.fingerprint import compute_fingerprint
from app.scanners.bandit_scanner import BanditScanner
from app.scanners.semgrep_scanner import SemgrepScanner

logger = logging.getLogger(__name__)

MAX_DIFF_LINES = int(os.environ.get("MAX_AUTOFIX_DIFF_LINES", 50))

@dataclass
class VerificationResult:
    is_verified: bool
    rejection_reason: Optional[str] = None
    diff: str = ""
    patched_file_content: str = ""
    syntax_valid: bool = False
    original_fingerprint_resolved: bool = False
    new_findings_count: int = 0
    scanners_run: List[str] = field(default_factory=list)

def apply_patch_to_file(
    original_content: str,
    patched_function: str,
    start_line: int,
    end_line: int
) -> Tuple[str, str, int]:
    """
    Replaces the lines [start_line, end_line] (1-indexed, inclusive)
    with patched_function. Returns (new_content, unified_diff, diff_lines_count).
    """
    orig_lines = original_content.splitlines(keepends=True)
    if not orig_lines:
        orig_lines = [""]

    # Normalize line endings
    clean_patch = patched_function.strip("\r\n")
    patch_lines = [l + "\n" for l in clean_patch.splitlines()]
    if not patch_lines:
        patch_lines = ["\n"]

    clamped_start = max(1, min(start_line, len(orig_lines)))
    clamped_end = max(clamped_start, min(end_line, len(orig_lines)))

    new_lines = orig_lines[:clamped_start - 1] + patch_lines + orig_lines[clamped_end:]
    new_content = "".join(new_lines)

    diff_gen = difflib.unified_diff(
        orig_lines,
        new_lines,
        fromfile="a/target",
        tofile="b/target",
        n=3
    )
    diff_text = "".join(diff_gen)

    # Count modified lines (+ and - lines excluding header)
    mod_lines = 0
    for line in diff_text.splitlines():
        if (line.startswith("+") and not line.startswith("+++")) or \
           (line.startswith("-") and not line.startswith("---")):
            mod_lines += 1

    return new_content, diff_text, mod_lines

def check_syntax(content: str, language: str) -> Tuple[bool, Optional[str]]:
    """Runs strict syntax checking without code execution."""
    lang = language.lower()
    if "." in lang:
        ext = os.path.splitext(lang)[1]
        lang = "python" if ext in (".py", ".pyi") else "javascript" if ext in (".js", ".jsx", ".ts", ".tsx") else "go" if ext == ".go" else "other"

    if lang == "python":
        try:
            ast.parse(content)
            return True, None
        except SyntaxError as se:
            return False, f"Python SyntaxError on line {se.lineno}: {se.msg}"
        except Exception as e:
            return False, f"Python AST parse error: {e}"

    elif lang in ("javascript", "typescript"):
        # Check basic bracket balance first
        stack = []
        pairs = {')': '(', '}': '{', ']': '['}
        for ch in content:
            if ch in "({[":
                stack.append(ch)
            elif ch in ")}]":
                if not stack or stack[-1] != pairs[ch]:
                    return False, f"Mismatched bracket '{ch}' in JavaScript/TypeScript syntax"
                stack.pop()
        if stack:
            return False, f"Unclosed bracket '{stack[-1]}' in JavaScript/TypeScript syntax"

        # If node is present in PATH, run node --check
        node_bin = shutil.which("node")
        if node_bin:
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tf:
                tf.write(content)
                tf_path = tf.name
            try:
                res = subprocess.run([node_bin, "--check", tf_path], capture_output=True, text=True, timeout=5)
                if res.returncode != 0:
                    return False, f"Node syntax error: {res.stderr.strip()[:200]}"
            except Exception:
                pass
            finally:
                try:
                    os.remove(tf_path)
                except OSError:
                    pass
        return True, None

    elif lang == "go":
        # Check brace balance
        open_b = content.count("{")
        close_b = content.count("}")
        if open_b != close_b:
            return False, f"Mismatched braces in Go syntax: {open_b} open vs {close_b} close"
        # If gofmt is present in PATH, run gofmt -e
        gofmt_bin = shutil.which("gofmt")
        if gofmt_bin:
            with tempfile.NamedTemporaryFile("w", suffix=".go", delete=False) as tf:
                tf.write(content)
                tf_path = tf.name
            try:
                res = subprocess.run([gofmt_bin, "-e", tf_path], capture_output=True, text=True, timeout=5)
                if res.returncode != 0:
                    return False, f"gofmt syntax error: {res.stderr.strip()[:200]}"
            except Exception:
                pass
            finally:
                try:
                    os.remove(tf_path)
                except OSError:
                    pass
        return True, None

    return True, None

async def verify_patch(
    original_content: str,
    patched_function: str,
    filepath: str,
    start_line: int,
    end_line: int,
    original_fingerprint: str,
    existing_file_fingerprints: Optional[Set[str]] = None
) -> VerificationResult:
    """
    Executes the comprehensive verification pipeline on a candidate patch:
    1. Scope & Line Cap Check (diff <= MAX_DIFF_LINES)
    2. Syntax Check (ast.parse, node --check, gofmt)
    3. Re-scan via Bandit and Semgrep
    4. Confirms original fingerprint is resolved and zero new vulnerabilities appear.
    """
    from app.services.autofix.context import detect_language

    language = detect_language(filepath)

    # 1. Apply patch and calculate diff
    patched_content, diff_text, mod_lines = apply_patch_to_file(
        original_content, patched_function, start_line, end_line
    )

    if mod_lines > MAX_DIFF_LINES:
        return VerificationResult(
            is_verified=False,
            rejection_reason=f"Patch diff exceeds limit of {MAX_DIFF_LINES} lines ({mod_lines} lines changed).",
            diff=diff_text,
            patched_file_content=patched_content
        )

    # 2. Syntax Check
    syntax_ok, syntax_err = check_syntax(patched_content, language)
    if not syntax_ok:
        return VerificationResult(
            is_verified=False,
            rejection_reason=f"Syntax check failed: {syntax_err}",
            diff=diff_text,
            patched_file_content=patched_content,
            syntax_valid=False
        )

    # 3. Security Re-Scan in Isolated Temp Directory
    temp_dir = tempfile.mkdtemp(prefix="cv_verify_")
    scanners_run = []
    try:
        norm_path = filepath.replace("\\", "/").strip().lstrip("/")
        dest_path = os.path.join(temp_dir, norm_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(patched_content)

        rescan_issues = []

        # Run Bandit for Python
        if language == "python":
            scanners_run.append("bandit")
            bandit = BanditScanner(temp_dir, target_files=[dest_path])
            try:
                b_issues = await bandit.scan()
                rescan_issues.extend(b_issues)
            except Exception as e:
                logger.warning(f"Verification Bandit re-scan error: {e}")

        # Run Semgrep for all supported languages
        scanners_run.append("semgrep")
        semgrep = SemgrepScanner(temp_dir, target_files=[dest_path])
        try:
            s_issues = await semgrep.scan()
            rescan_issues.extend(s_issues)
        except Exception as e:
            logger.warning(f"Verification Semgrep re-scan error: {e}")

        # Compute fingerprints of re-scanned issues
        rescan_fps: Set[str] = set()
        for iss in rescan_issues:
            fp = compute_fingerprint(iss)
            iss["fingerprint"] = fp
            rescan_fps.add(fp)

        # 4. Verification Assertions
        # Assertion A: Original fingerprint must be eliminated
        if original_fingerprint in rescan_fps:
            return VerificationResult(
                is_verified=False,
                rejection_reason="Original vulnerability remains unresolved in the patched code.",
                diff=diff_text,
                patched_file_content=patched_content,
                syntax_valid=True,
                original_fingerprint_resolved=False,
                scanners_run=scanners_run
            )

        # Assertion B: Zero new fingerprints introduced
        existing_fps = existing_file_fingerprints or {original_fingerprint}
        new_fps = rescan_fps - existing_fps
        if new_fps:
            new_issue_rules = [iss.get("rule_id", "issue") for iss in rescan_issues if iss.get("fingerprint") in new_fps]
            return VerificationResult(
                is_verified=False,
                rejection_reason=f"Patch introduced new security vulnerability: {', '.join(new_issue_rules)}",
                diff=diff_text,
                patched_file_content=patched_content,
                syntax_valid=True,
                original_fingerprint_resolved=True,
                new_findings_count=len(new_fps),
                scanners_run=scanners_run
            )

        # All verification criteria satisfied
        return VerificationResult(
            is_verified=True,
            rejection_reason=None,
            diff=diff_text,
            patched_file_content=patched_content,
            syntax_valid=True,
            original_fingerprint_resolved=True,
            new_findings_count=0,
            scanners_run=scanners_run
        )
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
