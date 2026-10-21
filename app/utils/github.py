import os
import re
import json
import urllib.request
import urllib.error
from urllib.parse import urlsplit
from dataclasses import dataclass
from typing import Optional, Tuple

MAX_REPO_KB: int = int(os.environ.get("MAX_REPO_KB", 51200))                       # 50 MB
MAX_DOWNLOAD_BYTES: int = int(os.environ.get("MAX_DOWNLOAD_BYTES", 52428800))       # 50 MB
DOWNLOAD_TIMEOUT_SECONDS: int = int(os.environ.get("DOWNLOAD_TIMEOUT_SECONDS", 60))

# Exact pattern for owner and repository names on GitHub
# Valid: alphanumeric, hyphen, underscore, dot. Must not start with dot/hyphen.
REPO_PATH_REGEX = re.compile(r'^/([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+?)(?:\.git)?/?$')

# Safe charset for branch names
BRANCH_REGEX = re.compile(r'^[a-zA-Z0-9_\-\./]+$')

# Valid commit SHA: exactly 40 hexadecimal characters
COMMIT_SHA_REGEX = re.compile(r'^[0-9a-fA-F]{40}$')

@dataclass
class GitHubRepoInfo:
    owner: str
    repo: str
    resolved_branch: str
    commit_sha: str
    size_kb: int

class SafeGitHubRedirectHandler(urllib.request.HTTPRedirectHandler):
    """
    SSRF Protection: Restricts all HTTP redirects strictly to verified GitHub hosts
    over HTTPS. Any redirect to private IPs, loopback, cloud metadata, or other domains is blocked.
    Also strips sensitive Authorization headers if redirected to the codeload CDN.
    """
    ALLOWED_HOSTS = {"api.github.com", "codeload.github.com", "github.com"}

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme.lower() != "https":
            raise ValueError(f"SSRF Blocked: Insecure redirect scheme '{parsed.scheme}'.")
        if not parsed.hostname or parsed.hostname.lower() not in self.ALLOWED_HOSTS:
            raise ValueError(f"SSRF Blocked: Redirect to untrusted host '{parsed.hostname}'.")
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req and parsed.hostname.lower() == "codeload.github.com":
            # Strip Authorization header when redirecting to codeload CDN to avoid token leakage
            for header_name in list(new_req.headers.keys()):
                if header_name.lower() == "authorization":
                    del new_req.headers[header_name]
            for header_name in list(getattr(new_req, "unredirected_hdrs", {}).keys()):
                if header_name.lower() == "authorization":
                    del new_req.unredirected_hdrs[header_name]
        return new_req

def get_safe_opener() -> urllib.request.OpenerDirector:
    """Builds a urllib opener equipped with SSRF-safe redirect validation."""
    return urllib.request.build_opener(SafeGitHubRedirectHandler())

def validate_github_url(raw_url: str) -> Tuple[str, str]:
    """
    Strictly validates a public GitHub repository URL:
    - Scheme must be strictly 'https'
    - Host must be strictly 'github.com' (no port, no credentials)
    - Path must match exactly 'owner/repo' with restricted character set
    - No query parameters or fragments
    Returns: (owner, repo)
    """
    if not raw_url or not isinstance(raw_url, str):
        raise ValueError("Repository URL must be provided.")

    url = raw_url.strip()
    parsed = urlsplit(url)

    if parsed.scheme.lower() != "https":
        raise ValueError("Only secure HTTPS URLs are permitted (https://github.com/owner/repo).")

    # Disallow custom ports, credentials, query parameters, or fragments
    if parsed.username or parsed.password:
        raise ValueError("Credentials in repository URL are prohibited.")

    if parsed.port and parsed.port != 443:
        raise ValueError("Custom ports in repository URL are prohibited.")

    if parsed.netloc.lower() != "github.com":
        raise ValueError("Repository host must be exactly 'github.com'.")

    if parsed.query or parsed.fragment:
        raise ValueError("Query strings and fragments are prohibited in repository URLs.")

    match = REPO_PATH_REGEX.match(parsed.path)
    if not match:
        raise ValueError("Invalid GitHub repository path. Expected format: https://github.com/owner/repo")

    owner, repo = match.group(1), match.group(2)

    # Reject traversal, leading dots or hyphens
    if ".." in owner or ".." in repo:
        raise ValueError("Path traversal sequences in repository identifiers are prohibited.")
    if owner.startswith(".") or repo.startswith("."):
        raise ValueError("Repository identifiers cannot begin with a dot.")

    return owner, repo

def validate_branch_name(branch: Optional[str]) -> Optional[str]:
    """Validates an optional branch name against a safe character set."""
    if not branch:
        return None
    b = branch.strip()
    if not b:
        return None

    if ".." in b or b.startswith("/") or b.endswith("/") or b.endswith(".lock"):
        raise ValueError("Invalid branch name sequence.")

    if not BRANCH_REGEX.match(b):
        raise ValueError("Branch name contains forbidden characters.")

    return b

def get_github_headers(auth_token: Optional[str] = None) -> dict:
    """Constructs API headers with optional authorization token."""
    headers = {
        "User-Agent": "CodeVanguard-SAST/1.0",
        "Accept": "application/vnd.github+json"
    }
    token = auth_token or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token.strip()}"
    return headers

def resolve_github_repo(owner: str, repo: str, branch: Optional[str] = None, auth_token: Optional[str] = None) -> GitHubRepoInfo:
    """
    Queries GitHub REST API to:
    1. Verify repository existence and public accessibility.
    2. Enforce MAX_REPO_KB repository size limit.
    3. Resolve the target branch (or default branch).
    4. Resolve the exact commit SHA for deterministic scanning.
    """
    opener = get_safe_opener()
    headers = get_github_headers(auth_token)

    # 1. Fetch Repository Metadata
    repo_api_url = f"https://api.github.com/repos/{owner}/{repo}"
    req = urllib.request.Request(repo_api_url, headers=headers)

    try:
        with opener.open(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as he:
        if he.code == 404:
            raise ValueError(f"GitHub repository '{owner}/{repo}' not found or is private.")
        elif he.code in (403, 429):
            raise ValueError("GitHub API rate limit reached. Configure GITHUB_TOKEN to raise limit.")
        raise ValueError(f"GitHub API error ({he.code}): {he.reason}")
    except Exception as e:
        raise ValueError(f"Failed to connect to GitHub API: {e}")

    # Check reported repo size in KB
    size_kb = data.get("size", 0)
    if size_kb > MAX_REPO_KB:
        raise ValueError(f"Repository size ({size_kb} KB) exceeds maximum allowed limit of {MAX_REPO_KB} KB.")

    default_branch = data.get("default_branch", "main")
    target_branch = branch if branch else default_branch

    # 2. Resolve Commit SHA
    commits_api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{target_branch}"
    req_commit = urllib.request.Request(commits_api_url, headers=headers)

    try:
        with opener.open(req_commit, timeout=15) as resp:
            commit_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as he:
        if he.code == 404:
            raise ValueError(f"Branch or reference '{target_branch}' not found in repository.")
        elif he.code in (403, 429):
            raise ValueError("GitHub API rate limit reached. Configure GITHUB_TOKEN to raise limit.")
        raise ValueError(f"GitHub API error resolving branch ({he.code}): {he.reason}")
    except Exception as e:
        raise ValueError(f"Failed to resolve commit for branch '{target_branch}': {e}")

    commit_sha = commit_data.get("sha")
    if not commit_sha or not isinstance(commit_sha, str) or not COMMIT_SHA_REGEX.match(commit_sha):
        raise ValueError(f"Could not determine valid 40-character commit SHA for branch '{target_branch}'.")
    clean_sha = commit_sha

    return GitHubRepoInfo(
        owner=owner,
        repo=repo,
        resolved_branch=target_branch,
        commit_sha=clean_sha,
        size_kb=size_kb
    )

def download_github_tarball(
    owner: str,
    repo: str,
    commit_sha: str,
    dest_file_path: str,
    max_download_bytes: int = MAX_DOWNLOAD_BYTES,
    timeout: int = DOWNLOAD_TIMEOUT_SECONDS,
    auth_token: Optional[str] = None
) -> int:
    """
    Streams the repository tarball for the specified commit SHA directly to disk.
    - Never loads the tarball into memory.
    - Enforces hard byte cap while streaming to prevent disk exhaustion.
    - SSRF-safe redirect handling strictly to *.github.com.
    - Passes authentication token strictly in Authorization header, never in URLs.
    """
    if not commit_sha or not isinstance(commit_sha, str) or not COMMIT_SHA_REGEX.match(commit_sha):
        raise ValueError(f"Invalid commit SHA '{commit_sha}'. Must be exactly 40 hexadecimal characters.")
    clean_sha = commit_sha

    opener = get_safe_opener()
    headers = get_github_headers()
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    tarball_url = f"https://api.github.com/repos/{owner}/{repo}/tarball/{clean_sha}"
    req = urllib.request.Request(tarball_url, headers=headers)

    os.makedirs(os.path.dirname(dest_file_path), exist_ok=True)
    downloaded_bytes = 0

    try:
        with opener.open(req, timeout=timeout) as resp:
            with open(dest_file_path, "wb") as f_out:
                while True:
                    chunk = resp.read(64 * 1024) # 64 KB chunks
                    if not chunk:
                        break
                    downloaded_bytes += len(chunk)
                    if downloaded_bytes > max_download_bytes:
                        raise ValueError(f"Repository tarball exceeded download cap of {max_download_bytes} bytes.")
                    f_out.write(chunk)
    except Exception as e:
        # Purge partial download
        if os.path.exists(dest_file_path):
            try:
                os.remove(dest_file_path)
            except OSError:
                pass
        raise

    return downloaded_bytes

def fetch_file_content_from_github(
    owner: str,
    repo: str,
    filepath: str,
    ref: str = "main",
    auth_token: Optional[str] = None
) -> str:
    """
    Fetches raw text content of a single file from GitHub Contents API.
    Caps read size at 5MB to avoid memory exhaustion.
    """
    import base64
    clean_path = filepath.replace("\\", "/").strip().lstrip("/")
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{clean_path}?ref={ref}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "CodeVanguard-SAST/1.0"
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    opener = get_safe_opener()
    req = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(req, timeout=15) as resp:
            data = json.loads(resp.read(5 * 1024 * 1024).decode("utf-8"))
            if "content" in data:
                raw_bytes = base64.b64decode(data["content"].encode("ascii"))
                return raw_bytes.decode("utf-8", errors="replace")
            raise ValueError(f"Content field missing in GitHub response for {clean_path}")
    except Exception as e:
        raise ValueError(f"Failed to fetch {clean_path} from GitHub repository: {e}")
