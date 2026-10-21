# Git History Secret Detection: Tuning, Limits & Remediation Guide

CodeVanguard provides deep, high-performance secret scanning across git commit history and source code trees without storing plaintext secrets or risking credential leaks in system logs.

---

## 1. History Access & Resource Limits

Because standard tarballs do not contain commit history, CodeVanguard executes shallow bare git clones to inspect historical commits.

### Configurable Limits

| Environment Variable | Default Value | Description |
| :--- | :--- | :--- |
| `HISTORY_MAX_COMMITS` | `500` | Maximum number of historical commits inspected per repository. |
| `HISTORY_MAX_DAYS` | `90` | Maximum commit age in days considered during shallow clones (`--shallow-since`). |
| `MAX_GIT_DIR_BYTES` | `209715200` (200MB) | Ephemeral disk budget cap. If the bare clone exceeds this limit, the scan aborts immediately to protect Render's container disk. |
| `SECRET_SALT` | `cv_default_secret_salt_2026_vanguard` | Salt used for non-reversible HMAC-SHA256 deduplication and fingerprinting. |

### Process & Token Security (`ps aux` Isolation)

Passing authentication tokens in CLI flags (e.g. `-c http.extraheader="Authorization: Bearer <token>"`) exposes tokens to all system users and processes via `ps aux` or `/proc`.

CodeVanguard isolates credentials by generating a temporary configuration file with strict `0600` permissions:
```ini
[http "https://github.com/"]
    extraHeader = Authorization: Bearer <installation_token>
```
Git commands are invoked with `GIT_CONFIG_GLOBAL=<temp_config_path>`. The command line executed is strictly `git clone --bare ...` with zero token exposure. The configuration and bare repository directories are purged in `finally` blocks.

---

## 2. Detection Engine & False-Positive Tuning

CodeVanguard employs a hybrid detection engine combining known provider signatures with Shannon entropy calculations.

### Supported Providers
- **AWS**: Access Key ID (`AKIA...`), Secret Access Key context
- **GitHub**: Classic PATs (`ghp_`), Fine-grained PATs (`github_pat_`), OAuth tokens (`gho_`), App installation tokens (`ghs_`), Refresh tokens (`ghr_`)
- **Stripe**: Live API keys (`sk_live_`, `rk_live_`), Webhook secrets (`whsec_`)
- **Slack**: Bot tokens (`xoxb-`), User tokens (`xoxp-`), Webhooks (`https://hooks.slack.com/services/...`)
- **Google API**: API keys (`AIza...`)
- **Private Key Blocks**: RSA, EC, DSA, OPENSSH, and PGP blocks
- **JWTs**: High-entropy 3-segment Base64URL tokens
- **Database URLs**: PostgreSQL, MySQL, MongoDB, Redis connection URIs with embedded passwords

### Shannon Entropy Thresholds
Entropy is calculated as:
$$H(X) = -\sum_{i} P(x_i) \log_2 P(x_i)$$

- **Hex Charset** (`[0-9a-fA-F]`): Minimum length 32 characters, $H > 3.0$.
- **Base64 Charset** (`[0-9a-zA-Z+/=]`): Minimum length 20 characters, $H > 4.5$.

### Context Gating (Mitigating False Positives)
To prevent flagging UUIDs, commit SHAs, CSS hash prefixes, or random test data, generic high-entropy strings are only evaluated if the line contains an assignment to a credential context keyword:
```
(?i)(?:secret|token|password|passwd|api_key|apikey|auth_token|access_token|private_key|credential|jwt_secret)
```

### Automatic Allowlists & Exclusions
The scanner automatically bypasses:
1. **Lockfiles**: `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `go.sum`, `Cargo.lock`, `poetry.lock`.
2. **Binary Assets & Maps**: Images, fonts, archives, audio/video, `.min.js`, `.min.css`, and `.map` files.
3. **Known Sample Placeholders**: `AKIAIOSFODNN7EXAMPLE`, `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`, `example`, `dummy`, `sample`, `fake`, `placeholder`, `<api_key>`.
4. **Repetitive Strings**: Strings with $\le 3$ distinct characters.

---

## 3. Safe Storage Guarantees

CodeVanguard enforces strict privacy rules for detected secrets:
- **Zero Plaintext Persistence**: Full secret values are **never** stored in the database, included in logs, or returned in API responses.
- **Masked Previews**: Previews are masked as `first 4 + ... + last 2` (e.g. `AKIA...2A`, `ghp_...56`). Strings $\le 6$ characters are masked as `***`.
- **Salted Deduplication**: Fingerprints use `HMAC-SHA256(secret, SECRET_SALT)` to ensure deduplication across commits without storing reversible plaintext.
- **HEAD vs History-Only Tracking**:
  - `CRITICAL`: Secret is actively present in the repository `HEAD`.
  - `HIGH`: Secret was deleted in later commits but remains accessible in git history.

---

## 4. Remediation & The `git filter-repo` Warning

> [!CAUTION]
> **Rotate First, Rewrite Second**
> Once a secret has been pushed to a remote repository, consider it permanently compromised. Simply deleting the line or file in a new commit does **NOT** invalidate the credential with your service provider.

### Immediate Remediation Checklist:
1. **Revoke the Credential**: Invalidate the key in the provider console (AWS IAM, GitHub Developer Settings, Stripe Dashboard, etc.) immediately.
2. **Update Production Secrets**: Generate a replacement credential and inject it into your application via environment variables or a secrets manager (AWS Secrets Manager, HashiCorp Vault, Supabase Secrets).
3. **Audit Access Logs**: Check access logs in your provider account for unauthorized operations executed during the exposure window.

### Optional: Purging Sensitive Files from Git History
If you wish to remove the leaked secret from git commit history to prevent cloning:

```bash
# Install git-filter-repo (recommended over BFG or git filter-branch)
pip install git-filter-repo

# Remove the sensitive file from all commits across all branches
git filter-repo --invert-paths --path <path/to/compromised_file>

# Force-push all rewritten branches to GitHub
git push origin --force --all
```

> [!WARNING]
> **Explicit Force-Push Warning**
> Running `git filter-repo` rewrites git commit SHAs throughout your entire repository history. 
> Pushing these changes requires `git push origin --force --all`, which **will invalidate open pull requests, detach collaborator commit bases, and disrupt active team branches**. 
> Ensure team members are informed and pull fresh clones after history rewriting.
