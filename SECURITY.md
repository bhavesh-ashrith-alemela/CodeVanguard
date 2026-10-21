# CodeVanguard Security Policy

CodeVanguard is an open-source Static Application Security Testing (SAST) and secret detection platform. Because CodeVanguard analyzes sensitive source code and git repositories, our architecture is designed around strict defense-in-depth principles.

---

## 1. Supported Versions

We provide security patches and updates for the following releases:

| Version | Supported | Notes |
| :--- | :--- | :--- |
| `1.0.x` | :white_check_mark: | Current stable release |
| `< 1.0.0` | :x: | Deprecated preview builds |

---

## 2. Reporting a Vulnerability

We welcome responsible security reports from security researchers, contributors, and users.

> [!IMPORTANT]
> **Please do not report security vulnerabilities via public GitHub issues, discussions, or pull requests.**

### Reporting Process
1. **Private Advisory**: Use [GitHub Security Advisories](https://github.com/codevanguard/codevanguard/security/advisories/new) to submit a confidential report.
2. **Alternative Contact**: If GitHub Advisories are unavailable, email **`security@codevanguard.dev`**.
3. **What to Include**:
   - Vulnerability type (e.g., IDOR, SSRF, command injection, path traversal, token leak).
   - Exact steps or proof-of-concept (PoC) script to reproduce.
   - Affected files and line numbers.
   - Assessment of impact (e.g., cross-tenant exposure, remote code execution).
4. **Response Timelines**:
   - **Initial Response**: Within 24 hours acknowledging receipt.
   - **Triage & Reproduction**: Within 72 hours with severity classification.
   - **Patch Release**: High and critical issues patched within 7 calendar days.
   - **Public Disclosure**: Coordinated disclosure after the patch has been released.

---

## 3. Core Architectural Security Guarantees

CodeVanguard enforces strict guarantees across the entire scanning, auto-fixing, and storage lifecycle:

### A. Zero Source Code Persistence
- Repositories and diffs are downloaded into an isolated ephemeral workspace.
- Once static analysis and secret detection complete, the temporary workspace is permanently deleted in a mandatory `finally` block.
- We never store entire source trees, unedited files, or zip/tar archives in database tables, object stores, or persistent volumes.
- Finding records retain only file path, line numbers, normalized rule IDs, and SHA-256 fingerprints.

### B. Safe Secret Detection
- Candidate secrets detected in git history or HEAD commits are **never** stored in plaintext.
- The database stores only a masked preview (`first 4` and `last 2` characters) and a salted SHA-256 hash for deduplication.
- CodeVanguard **never** executes live validation calls against third-party provider APIs (e.g., AWS, Stripe, GitHub) to check if a secret is live.

### C. Bounded LLM Context & Verification
- Auto-fix requires an explicit, per-repository opt-in in Settings.
- Repositories are never uploaded in bulk to LLMs. Tree-sitter bounds context strictly to the enclosing function and necessary imports.
- All candidate credentials, tokens, and authorization headers are scrubbed from the context before inference.
- Ollama is supported as a 100% on-premises, zero-network LLM provider.
- LLM patches are re-scanned in an isolated syntax and SAST sandbox before being presented. Only patches that eliminate the target finding without introducing new findings are accepted.
- Auto-fix creates dedicated branches (`cv/fix-<rule>-<fingerprint8>`) and opens pull requests only; it never pushes to default branches.

### D. Multi-Tenant Authorization & IDOR Defense
- Every API endpoint that touches scans, findings, summaries, or repositories validates the caller's GitHub user identity against installation memberships.
- Cross-tenant lookups (e.g., querying another organization's scan ID) return `404 Not Found` to prevent account enumeration.

### E. Secure Token Storage & Logging
- GitHub App tokens and installation keys are encrypted at rest using Fernet symmetric encryption (`TOKEN_ENCRYPTION_KEY`).
- Application-wide logging filters actively scrub token prefixes (`ghp_`, `ghs_`, `ghu_`, `Bearer `, AWS keys, Stripe keys) before messages are written to stdout or Sentry.
- Git operations pass authentication via `http.extraheader` with credential helpers—tokens never appear in process lists, clone URLs, or `.git/config`.

---

## 4. Bounty & Recognition

We publicly credit researchers who responsibly disclose vulnerabilities in our release notes and Hall of Fame (unless anonymity is requested).
