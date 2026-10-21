"""
Secret Scanner Module for CodeVanguard SAST.

Features:
- Stream-based parsing of git log -p and diff-tree (O(1) memory consumption).
- Provider regexes (AWS, GitHub, Stripe, Slack, Google API keys, Private Keys, JWTs, DB URLs).
- Shannon entropy detection with charset-specific thresholds (Hex > 3.0, Base64 > 4.5).
- Allowlist filtering (lockfiles, test fixtures, sample keys, hashes).
- Context heuristics (variable assignment names).
- Zero raw secrets stored: previews masked (first 4 + ... + last 2), salted SHA-256 hashes.
- Head vs History-Only classification (Critical if in HEAD, High if deleted in history).
- Offline validation only: zero calls to third-party APIs.
"""
import os
import re
import math
import hmac
import hashlib
import asyncio
import subprocess
from typing import List, Dict, Any, Optional, Set, Tuple

SECRET_SALT = os.environ.get("SECRET_SALT", "cv_default_secret_salt_2026_vanguard")

# Allowed / Decoy patterns that must NEVER be flagged
ALLOWLIST_PATTERNS = [
    re.compile(r"AKIAIOSFODNN7EXAMPLE", re.IGNORECASE),
    re.compile(r"wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", re.IGNORECASE),
    re.compile(r"(?:example|sample|fake|dummy|placeholder|replace_me|your_key_here)", re.IGNORECASE),
    re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE), # UUIDs
    re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE), # Git commit SHA alone
    re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE), # SHA-256 alone
]

# File extensions and paths to ignore during secret scanning
IGNORED_SECRET_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "go.sum",
    "Cargo.lock", "poetry.lock", "composer.lock", "Gemfile.lock",
    ".gitignore", "requirements.txt.lock"
}

IGNORED_SECRET_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pdf", ".mp4", ".mp3", ".mov", ".zip", ".tar", ".gz",
    ".map", ".min.js", ".min.css"
}

# Context keywords that indicate credentials on assignment lines
CONTEXT_KEYWORDS = re.compile(
    r"(?i)(?:secret|token|password|passwd|api_key|apikey|auth_token|access_token|private_key|credential|jwt_secret|client_secret)"
)

# Known Provider Signatures
PROVIDER_RULES = [
    {
        "id": "SECRET_AWS_KEY",
        "name": "AWS Access Key ID",
        "pattern": re.compile(r"(?<![A-Z0-9])(AKIA[0-9A-Z]{16})(?![A-Z0-9])"),
        "min_len": 20,
        "max_len": 20
    },
    {
        "id": "SECRET_GITHUB_PAT",
        "name": "GitHub Personal Access Token",
        "pattern": re.compile(r"(?<![a-zA-Z0-9])(ghp_[0-9a-zA-Z]{36})(?![a-zA-Z0-9])"),
        "min_len": 40,
        "max_len": 40
    },
    {
        "id": "SECRET_GITHUB_PAT_FINE",
        "name": "GitHub Fine-Grained Personal Access Token",
        "pattern": re.compile(r"(?<![a-zA-Z0-9])(github_pat_[0-9a-zA-Z_]{82})(?![a-zA-Z0-9])"),
        "min_len": 93,
        "max_len": 93
    },
    {
        "id": "SECRET_GITHUB_OAUTH",
        "name": "GitHub OAuth Access Token",
        "pattern": re.compile(r"(?<![a-zA-Z0-9])(gh[orisu]_[0-9a-zA-Z]{36})(?![a-zA-Z0-9])"),
        "min_len": 40,
        "max_len": 40
    },
    {
        "id": "SECRET_STRIPE_KEY",
        "name": "Stripe Live API Key",
        "pattern": re.compile(r"(?<![a-zA-Z0-9])((?:sk|rk)_live_[0-9a-zA-Z]{24,99})(?![a-zA-Z0-9])"),
        "min_len": 32,
        "max_len": 120
    },
    {
        "id": "SECRET_STRIPE_WEBHOOK",
        "name": "Stripe Webhook Secret",
        "pattern": re.compile(r"(?<![a-zA-Z0-9])(whsec_[0-9a-zA-Z]{32,64})(?![a-zA-Z0-9])"),
        "min_len": 38,
        "max_len": 70
    },
    {
        "id": "SECRET_SLACK_TOKEN",
        "name": "Slack API Token",
        "pattern": re.compile(r"(?<![a-zA-Z0-9])(xox[bpa]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24})(?![a-zA-Z0-9])"),
        "min_len": 48,
        "max_len": 60
    },
    {
        "id": "SECRET_SLACK_WEBHOOK",
        "name": "Slack Webhook URL",
        "pattern": re.compile(r"(https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+)"),
        "min_len": 45,
        "max_len": 120
    },
    {
        "id": "SECRET_GOOGLE_KEY",
        "name": "Google API Key",
        "pattern": re.compile(r"(?<![a-zA-Z0-9])(AIza[0-9A-Za-z\-_]{35})(?![a-zA-Z0-9])"),
        "min_len": 39,
        "max_len": 39
    },
    {
        "id": "SECRET_PRIVATE_KEY",
        "name": "Private Key Block",
        "pattern": re.compile(r"(-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----)"),
        "min_len": 28,
        "max_len": 64
    },
    {
        "id": "SECRET_JWT_TOKEN",
        "name": "JSON Web Token (JWT)",
        "pattern": re.compile(r"(?<![a-zA-Z0-9_-])(eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,})(?![a-zA-Z0-9_-])"),
        "min_len": 45,
        "max_len": 2048
    },
    {
        "id": "SECRET_DB_URL",
        "name": "Database Connection String with Credentials",
        "pattern": re.compile(r"((?:postgres|postgresql|mysql|mongodb|mongodb\+srv|redis|rediss)://[^:\s]+:[^@\s]{3,}@[a-zA-Z0-9\-\.]+:[0-9]+/[^?\s]+)"),
        "min_len": 20,
        "max_len": 256
    }
]

def calculate_shannon_entropy(data: str) -> float:
    """Calculates the Shannon entropy H(X) in bits per character."""
    if not data:
        return 0.0
    length = len(data)
    frequencies: Dict[str, int] = {}
    for char in data:
        frequencies[char] = frequencies.get(char, 0) + 1
    
    entropy = 0.0
    for count in frequencies.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy

def mask_secret(secret: str) -> str:
    """Returns safe masked preview: first 4 + ... + last 2 (or '***' if too short)."""
    s = secret.strip()
    if len(s) <= 6:
        return "***"
    return f"{s[:4]}...{s[-2:]}"

def hash_secret(secret: str, salt: str = SECRET_SALT) -> str:
    """Computes a salted HMAC-SHA256 for non-reversible deduplication and fingerprinting."""
    return hmac.new(salt.encode("utf-8"), secret.strip().encode("utf-8"), hashlib.sha256).hexdigest()

def is_allowlisted_secret(candidate: str, line_content: str, file_path: str) -> bool:
    """Checks if string matches any known test fixtures, dummy tokens, or lockfile artifacts."""
    norm_path = file_path.replace("\\", "/").lower()
    base_name = os.path.basename(norm_path)

    # Ignore lockfiles and binary assets
    if base_name in IGNORED_SECRET_FILES:
        return True
    _, ext = os.path.splitext(base_name)
    if ext in IGNORED_SECRET_EXTENSIONS:
        return True

    # Check allowlist regexes on candidate secret
    for pat in ALLOWLIST_PATTERNS:
        if pat.search(candidate):
            return True

    # Reject repetitive strings (e.g. 000000000000 or aaaaaaaaaaaa)
    if len(set(candidate)) <= 3:
        return True

    return False

def inspect_line_for_secrets(
    line: str,
    file_path: str,
    line_number: int,
    commit_sha: str = "",
    commit_date: str = ""
) -> List[Dict[str, Any]]:
    """
    Scans a single line for regex patterns and high-entropy secret tokens.
    Returns findings without persisting the raw secret.
    """
    findings = []
    seen_hashes: Set[str] = set()

    # 1. Provider Pattern Matching
    for rule in PROVIDER_RULES:
        for match in rule["pattern"].finditer(line):
            raw_secret = match.group(1)
            if not raw_secret or len(raw_secret) < rule["min_len"] or len(raw_secret) > rule["max_len"]:
                continue
            if is_allowlisted_secret(raw_secret, line, file_path):
                continue

            sec_hash = hash_secret(raw_secret)
            if sec_hash in seen_hashes:
                continue
            seen_hashes.add(sec_hash)

            masked = mask_secret(raw_secret)
            findings.append({
                "rule_id": rule["id"],
                "detector": rule["name"],
                "raw_secret": raw_secret,  # Used internally to check HEAD presence, stripped before output
                "masked_secret": masked,
                "secret_hash": sec_hash,
                "filepath": file_path,
                "line_number": line_number,
                "col_number": match.start(1) + 1,
                "commit_sha": commit_sha,
                "commit_date": commit_date,
                "line_content": line
            })

    # 2. Shannon Entropy Inspection (Context-Gated)
    # Require an assignment keyword on the line to avoid flagging UUIDs, commit hashes, or CSS hashes
    if CONTEXT_KEYWORDS.search(line):
        # Scan for hex strings (length >= 32, entropy > 3.0)
        hex_candidates = re.findall(r"(?<![0-9a-fA-F])([0-9a-fA-F]{32,64})(?![0-9a-fA-F])", line)
        for hex_cand in hex_candidates:
            if not is_allowlisted_secret(hex_cand, line, file_path):
                entropy = calculate_shannon_entropy(hex_cand)
                if entropy > 3.0:
                    sec_hash = hash_secret(hex_cand)
                    if sec_hash not in seen_hashes:
                        seen_hashes.add(sec_hash)
                        masked = mask_secret(hex_cand)
                        findings.append({
                            "rule_id": "SECRET_HIGH_ENTROPY",
                            "detector": f"High Entropy Hex Secret (H={entropy:.2f})",
                            "raw_secret": hex_cand,
                            "masked_secret": masked,
                            "secret_hash": sec_hash,
                            "filepath": file_path,
                            "line_number": line_number,
                            "col_number": line.find(hex_cand) + 1,
                            "commit_sha": commit_sha,
                            "commit_date": commit_date,
                            "line_content": line
                        })

        # Scan for base64 / alphanumeric strings (length >= 20, entropy > 4.5)
        b64_candidates = re.findall(r"['\"]([A-Za-z0-9+/=_-]{20,80})['\"]", line)
        for b64_cand in b64_candidates:
            if not is_allowlisted_secret(b64_cand, line, file_path):
                entropy = calculate_shannon_entropy(b64_cand)
                if entropy > 4.5:
                    sec_hash = hash_secret(b64_cand)
                    if sec_hash not in seen_hashes:
                        seen_hashes.add(sec_hash)
                        masked = mask_secret(b64_cand)
                        findings.append({
                            "rule_id": "SECRET_HIGH_ENTROPY",
                            "detector": f"High Entropy Base64 Secret (H={entropy:.2f})",
                            "raw_secret": b64_cand,
                            "masked_secret": masked,
                            "secret_hash": sec_hash,
                            "filepath": file_path,
                            "line_number": line_number,
                            "col_number": line.find(b64_cand) + 1,
                            "commit_sha": commit_sha,
                            "commit_date": commit_date,
                            "line_content": line
                        })

    return findings

class SecretScanner:
    """
    Scanner implementation adhering to the async scan() interface.
    Supports:
    - Bare git history scanning via streaming 'git log -p'
    - Incremental push range scanning ('git log -p before..after')
    - Working tree / extracted files scanning
    """
    def __init__(
        self,
        target_dir: str = "",
        git_dir: Optional[str] = None,
        commit_range: Optional[str] = None,
        target_files: Optional[List[str]] = None
    ):
        self.target_dir = os.path.abspath(target_dir) if target_dir else ""
        self.git_dir = os.path.abspath(git_dir) if git_dir else ""
        self.commit_range = commit_range
        self.target_files = target_files

    async def _stream_git_log_and_detect(self) -> List[Dict[str, Any]]:
        """
        Streams 'git log -p' line by line asynchronously to avoid
        buffering large repository histories into memory.
        """
        git_target = self.git_dir or (os.path.join(self.target_dir, ".git") if os.path.exists(os.path.join(self.target_dir, ".git")) else self.target_dir)
        if not os.path.exists(git_target):
            return []

        args = ["git"]
        if os.path.isdir(git_target) and git_target.endswith(".git"):
            args.extend(["--git-dir", git_target])
        else:
            args.extend(["-C", git_target])

        args.extend(["log", "-p", "--date=iso", "--no-color"])

        if self.commit_range:
            # Validate commit range to prevent flag injection (e.g. --output=...)
            if self.commit_range.startswith("-") or not re.match(r"^[a-zA-Z0-9_\-\.~^]+(\.\.[a-zA-Z0-9_\-\.~^]+)?$", self.commit_range):
                return []
            args.extend(["--", self.commit_range])
        else:
            args.extend(["--full-history", "-n", "500", "--"])

        env = {
            "GIT_TERMINAL_PROMPT": "0",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin")
        }

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,  # Prevent pipe buffer deadlock
                env=env
            )
        except Exception:
            return []

        findings: List[Dict[str, Any]] = []

        async def _read_stream():
            current_commit = ""
            current_date = ""
            current_file = ""
            current_line_no = 0

            while True:
                raw_line = await proc.stdout.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")

                if line.startswith("commit "):
                    current_commit = line.split(" ")[1]
                elif line.startswith("Date:   "):
                    current_date = line[8:].strip()
                elif line.startswith("diff --git "):
                    # Handle quoted and unquoted git diff file paths
                    m = re.search(r'b/("?[^"\n\r]+"?)$', line)
                    if m:
                        b_raw = m.group(1).strip('"')
                        current_file = b_raw
                    else:
                        parts = line.split(" ")
                        if len(parts) >= 4:
                            b_path = parts[3].strip('"')
                            current_file = b_path[2:] if b_path.startswith("b/") else b_path
                elif line.startswith("@@ "):
                    # Hunk header: @@ -l,s +new_line,new_size @@
                    hunk_match = re.search(r"\+([0-9]+)", line)
                    if hunk_match:
                        current_line_no = int(hunk_match.group(1)) - 1
                elif line.startswith("+") and not line.startswith("+++"):
                    current_line_no += 1
                    added_content = line[1:]
                    if current_file:
                        detected = inspect_line_for_secrets(
                            added_content,
                            file_path=current_file,
                            line_number=current_line_no,
                            commit_sha=current_commit,
                            commit_date=current_date
                        )
                        findings.extend(detected)
                elif not line.startswith("-"):
                    current_line_no += 1

        try:
            await asyncio.wait_for(_read_stream(), timeout=90.0)
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except (asyncio.TimeoutError, Exception):
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass

        return findings

    def _check_secret_presence_in_head(self, raw_secret: str, file_path: str) -> bool:
        """
        Determines whether a secret still exists at HEAD with:
        - Strict path traversal guards (anti-arbitrary file read)
        - Memory consumption cap (max 5MB file read)
        - Object size checks before 'git show' to prevent OOM
        - In-memory HEAD cache for duplicate finding efficiency
        """
        if not raw_secret or not file_path:
            return False

        # Guard against path traversal attacks in file_path
        norm_path = file_path.replace("\\", "/").strip().lstrip("/")
        if ".." in norm_path.split("/") or norm_path.startswith("/"):
            return False

        # 1. Physical target directory
        if self.target_dir and os.path.exists(self.target_dir):
            try:
                base_dir = os.path.realpath(self.target_dir)
                full_path = os.path.realpath(os.path.join(self.target_dir, norm_path))
                # Ensure resolved path is strictly within base_dir and not a symlink
                if (
                    full_path.startswith(base_dir + os.sep)
                    and os.path.isfile(full_path)
                    and not os.path.islink(full_path)
                ):
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read(5 * 1024 * 1024)
                        if raw_secret in content:
                            return True
            except Exception:
                pass

        # 2. Git bare repository inspection (cached)
        git_target = self.git_dir or (os.path.join(self.target_dir, ".git") if os.path.exists(os.path.join(self.target_dir, ".git")) else "")
        if git_target and os.path.exists(git_target):
            if not hasattr(self, "_head_cache"):
                self._head_cache: Dict[str, Optional[str]] = {}

            if norm_path not in self._head_cache:
                args = ["git"]
                if git_target.endswith(".git") and os.path.isdir(git_target):
                    args.extend(["--git-dir", git_target])
                else:
                    args.extend(["-C", git_target])

                env = {
                    "GIT_TERMINAL_PROMPT": "0",
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin")
                }

                # Check object size before reading to avoid OOM
                check_size_args = list(args) + ["cat-file", "-s", f"HEAD:{norm_path}"]
                try:
                    size_res = subprocess.run(
                        check_size_args,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        env=env,
                        text=True,
                        timeout=5
                    )
                    if size_res.returncode == 0:
                        size_bytes = int(size_res.stdout.strip())
                        if size_bytes > 5 * 1024 * 1024:
                            self._head_cache[norm_path] = None
                        else:
                            show_args = list(args) + ["show", f"HEAD:{norm_path}"]
                            show_res = subprocess.run(
                                show_args,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                env=env,
                                text=True,
                                timeout=10
                            )
                            if show_res.returncode == 0:
                                self._head_cache[norm_path] = show_res.stdout
                            else:
                                self._head_cache[norm_path] = None
                    else:
                        self._head_cache[norm_path] = None
                except Exception:
                    self._head_cache[norm_path] = None

            cached_content = self._head_cache.get(norm_path)
            if cached_content is not None and raw_secret in cached_content:
                return True

        return False

    async def _scan_disk_files(self) -> List[Dict[str, Any]]:
        """Scans extracted files on disk directly for secrets (e.g. for PR or tarball scans)."""
        findings = []
        if not self.target_dir or not os.path.exists(self.target_dir):
            return findings

        files_to_scan = []
        if self.target_files is not None:
            files_to_scan = [os.path.join(self.target_dir, f) for f in self.target_files]
        else:
            for root, dirs, files in os.walk(self.target_dir):
                # Ignore .git and node_modules
                dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".next", "venv", ".venv")]
                for file in files:
                    files_to_scan.append(os.path.join(root, file))

        for file_path in files_to_scan:
            rel_path = os.path.relpath(file_path, self.target_dir).replace("\\", "/")
            base_name = os.path.basename(rel_path).lower()
            if base_name in IGNORED_SECRET_FILES:
                continue
            _, ext = os.path.splitext(base_name)
            if ext in IGNORED_SECRET_EXTENSIONS:
                continue

            try:
                # Skip huge files (> 2MB)
                if os.path.getsize(file_path) > 2 * 1024 * 1024:
                    continue
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for line_idx, line in enumerate(f, start=1):
                        detected = inspect_line_for_secrets(
                            line=line,
                            file_path=rel_path,
                            line_number=line_idx
                        )
                        findings.extend(detected)
            except Exception:
                continue

        return findings

    async def scan(self) -> List[Dict[str, Any]]:
        """
        Executes secret scanning and returns standard issue dictionaries.
        Classifies severity:
        - Critical if secret is present at HEAD
        - High if secret only exists in history (deleted in HEAD)
        """
        raw_findings: List[Dict[str, Any]] = []

        # 1. Run git log stream if git_dir is provided or .git directory exists
        has_git = bool(self.git_dir) or (bool(self.target_dir) and os.path.exists(os.path.join(self.target_dir, ".git")))
        if has_git:
            git_findings = await self._stream_git_log_and_detect()
            raw_findings.extend(git_findings)

        # 2. Run disk file scan if target_dir has files
        if self.target_dir and os.path.exists(self.target_dir):
            disk_findings = await self._scan_disk_files()
            # Merge disk findings, keeping track of hashes
            seen_hashes = {f["secret_hash"] for f in raw_findings}
            for df in disk_findings:
                if df["secret_hash"] not in seen_hashes:
                    seen_hashes.add(df["secret_hash"])
                    raw_findings.append(df)

        # 3. Classify HEAD vs History-Only and format for standard issue schema
        final_issues: List[Dict[str, Any]] = []
        dedup_map: Dict[str, Dict[str, Any]] = {}

        for item in raw_findings:
            raw_secret = item.get("raw_secret", "")
            file_path = item.get("filepath", "")
            sec_hash = item.get("secret_hash", "")
            masked = item.get("masked_secret", "")
            detector = item.get("detector", "Exposed Secret")
            rule_id = item.get("rule_id", "SECRET_EXPOSED")
            commit_sha = item.get("commit_sha", "")
            commit_date = item.get("commit_date", "")
            line_no = item.get("line_number", 1)
            col_no = item.get("col_number", 0)

            # Determine whether the secret still exists in HEAD
            still_in_head = self._check_secret_presence_in_head(raw_secret, file_path)

            if still_in_head:
                severity = "critical"
                message = f"Active {detector} exposed at HEAD: {masked}"
            else:
                severity = "high"
                msg_commit = f" in commit {commit_sha[:8]}" if commit_sha else ""
                message = f"Leaked {detector}{msg_commit} (deleted in later commits): {masked}"

            # Create safe code snippet with the secret masked
            raw_line = item.get("line_content", "")
            safe_line = raw_line.replace(raw_secret, masked) if raw_secret else raw_line
            snippet = f"{line_no}: {safe_line.strip()}"

            issue_dict = {
                "scanner": "secret",
                "rule_id": rule_id,
                "severity": severity,
                "message": message,
                "filepath": file_path,
                "line_number": line_no,
                "col_number": col_no,
                "code_snippet": snippet,
                "fingerprint": sec_hash,
                "masked_secret": masked,
                "secret_hash": sec_hash,
                "detector": detector,
                "commit_sha": commit_sha,
                "commit_date": commit_date,
                "still_in_head": still_in_head,
                "is_secret": True
            }

            # Deduplicate by (filepath, secret_hash)
            dedup_key = f"{file_path}:{sec_hash}"
            if dedup_key not in dedup_map:
                dedup_map[dedup_key] = issue_dict
            else:
                # If seen before, escalate to critical if any occurrence is in HEAD
                if still_in_head and not dedup_map[dedup_key]["still_in_head"]:
                    dedup_map[dedup_key]["still_in_head"] = True
                    dedup_map[dedup_key]["severity"] = "critical"
                    dedup_map[dedup_key]["message"] = message

        final_issues = list(dedup_map.values())
        return final_issues
