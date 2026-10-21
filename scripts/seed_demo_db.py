"""
Seed Demo Database Script for CodeVanguard.

Populates SQLite or Postgres with realistic data for live demonstration:
1. Demo GitHub App installation ('demo-org').
2. Repository 'demo-org/vulnerable-microservice'.
3. Default-branch baseline scan with 3 issues (SQL Injection, Command Injection, Historical Leaked Secret).
4. Pull Request #1 with deterministic PRSummaryFacts, touch categories, push delta, and reviewer action items.
5. Verified auto-fix attempt on the SQL Injection finding with verified diff preview.
"""
import os
import sys
import uuid
from datetime import datetime, timedelta

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.db import (
    init_db, get_db_connection, upsert_installation, upsert_repository,
    add_installation_member, create_scan, save_scan_results,
    upsert_baseline_findings, update_scan_pr_metrics, save_pr_summary,
    save_fix_attempt
)
from app.services.pr_summary.models import (
    PRSummaryFacts, PRDetails, FindingsGroup, FindingSummaryItem,
    DependencyChange, PushDelta, ActionItem
)

def seed_demo_environment():
    print("[CodeVanguard Seed] Initializing database tables...")
    init_db()

    now = datetime.now()
    now_iso = now.isoformat()
    yesterday_iso = (now - timedelta(days=1)).isoformat()
    two_days_ago_iso = (now - timedelta(days=2)).isoformat()

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Ensure a demo user exists
        cursor.execute("SELECT id FROM users WHERE username = 'demo_user' OR username = 'admin'")
        user_row = cursor.fetchone()
        if user_row:
            user_id = user_row["id"]
        else:
            from app.utils.db import hash_password
            cursor.execute("""
                INSERT INTO users (username, hashed_password, role, created_at, github_login)
                VALUES ('demo_user', ?, 'admin', ?, 'demo_user')
            """, (hash_password("DemoVanguard2026!"), now_iso))
            cursor.execute("SELECT id FROM users WHERE username = 'demo_user'")
            user_id = cursor.fetchone()["id"]

        # 2. Create demo installation
        inst = upsert_installation(
            github_installation_id=98765432,
            account_login="demo-org",
            account_type="Organization",
            account_avatar_url="https://avatars.githubusercontent.com/u/9919?s=200&v=4"
        )
        add_installation_member(inst["id"], user_id, role="admin")

        # 3. Create demo repository
        repo = upsert_repository(
            installation_id=inst["id"],
            github_repo_id=123456789,
            full_name="demo-org/vulnerable-microservice",
            default_branch="main",
            is_private=False
        )
        repo_id = repo["id"]

        # 4. Create Baseline Default-Branch Scan (Main)
        baseline_scan_id = uuid.uuid4().hex
        baseline_commit = "9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b"

        create_scan(
            scan_id=baseline_scan_id,
            filename="demo-org/vulnerable-microservice@main",
            file_size=154200,
            source_type="github_app",
            source_url="https://github.com/demo-org/vulnerable-microservice",
            branch="main",
            commit_sha=baseline_commit,
            repo_id=repo_id,
            owner_user_id=user_id,
            trigger="push"
        )

        # Baseline findings:
        # 1. SQL Injection (B608) in src/db.py
        # 2. Command Injection (B602) in src/exporter.py
        # 3. Historical Leaked Secret (AWS Key) in src/config.py (still_in_head=False)
        baseline_issues = [
            {
                "scanner": "bandit",
                "rule_id": "B608:hardcoded_sql_expressions",
                "severity": "high",
                "message": "Possible SQL injection vector through string formatting",
                "filepath": "src/db.py",
                "line_number": 8,
                "col_number": 5,
                "code_snippet": '8:     cursor.execute(f"SELECT * FROM users WHERE username = \'{username}\'")',
                "fingerprint": "fp_sql_injection_db_orders",
                "state": "open"
            },
            {
                "scanner": "bandit",
                "rule_id": "B602:subprocess_popen_with_shell_equals_true",
                "severity": "high",
                "message": "subprocess call with shell=True identified, security issue.",
                "filepath": "src/exporter.py",
                "line_number": 5,
                "col_number": 5,
                "code_snippet": '5:     subprocess.run(f"cat /tmp/data > {output_filename}", shell=True)',
                "fingerprint": "fp_command_injection_shell_true",
                "state": "open"
            },
            {
                "scanner": "secret",
                "rule_id": "SECRET_AWS_KEY",
                "severity": "high",
                "message": "Leaked AWS Access Key ID in commit 9a8b7c6d (deleted in later commits): AKIA...EF",
                "filepath": "src/config.py",
                "line_number": 6,
                "col_number": 1,
                "code_snippet": '6: AWS_ACCESS_KEY_ID = "AKIA...EF"',
                "fingerprint": "fp_secret_aws_key_leak_987",
                "masked_secret": "AKIA...EF",
                "secret_hash": "c0ffee1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                "detector": "AWS Access Key ID",
                "commit_sha": baseline_commit,
                "commit_date": two_days_ago_iso,
                "still_in_head": False,
                "is_secret": True,
                "state": "open"
            }
        ]

        save_scan_results(
            scan_id=baseline_scan_id,
            issues=baseline_issues,
            duration_ms=450,
            files_scanned=8,
            files_skipped=0
        )
        upsert_baseline_findings(repo_id, baseline_scan_id, baseline_commit, baseline_issues)

        # Retrieve the finding ID generated for SQL injection
        cursor.execute("SELECT id FROM findings WHERE repo_id = ? AND rule_id LIKE '%B608%'", (repo_id,))
        sql_finding_row = cursor.fetchone()
        sql_finding_id = sql_finding_row["id"] if sql_finding_row else "finding_sql_001"

        # 5. Create a Verified Auto-Fix record for the SQL injection finding
        fix_diff = """--- src/db.py
+++ src/db.py
@@ -6,3 +6,3 @@
-    cursor.execute(f"SELECT * FROM users WHERE username = '{username}'")
+    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
"""
        save_fix_attempt(
            attempt_id="fix_attempt_demo_sql_1",
            finding_id=sql_finding_id,
            repo_id=repo_id,
            status="verified",
            provider="gemini",
            model="gemini-1.5-flash",
            target_file="src/db.py",
            target_function="get_user_records",
            start_line=6,
            end_line=9,
            diff=fix_diff,
            patch_code='    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))',
            explanation="Replaced vulnerable Python f-string query formatting with parameterized query placeholder `?`.",
            verification_json={
                "syntax_valid": True,
                "issue_resolved": True,
                "zero_new_regressions": True,
                "diff_line_count": 2
            },
            pr_number=None,
            pr_url=None,
            branch_name=f"cv/fix-B608-{sql_finding_id[:8]}",
            tokens_in=380,
            tokens_out=95,
            cost_usd=0.0001
        )

        # 6. Create Pull Request Scan (PR #1: feature/vulnerable-pr)
        pr_scan_id = uuid.uuid4().hex
        pr_head_sha = "5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e"

        create_scan(
            scan_id=pr_scan_id,
            filename="demo-org/vulnerable-microservice@PR#1",
            file_size=158400,
            source_type="github_app",
            source_url="https://github.com/demo-org/vulnerable-microservice",
            branch="feature/vulnerable-pr",
            commit_sha=pr_head_sha,
            repo_id=repo_id,
            owner_user_id=user_id,
            trigger="pr",
            pr_number=1
        )

        # PR scan issues:
        # Existing from baseline: B608 (db.py), B602 (exporter.py)
        # New in PR: Path traversal (api/files.py)
        pr_issues = list(baseline_issues[:2]) + [
            {
                "scanner": "semgrep",
                "rule_id": "python.lang.security.audit.path-traversal",
                "severity": "critical",
                "message": "Path traversal via unsanitized user file parameter",
                "filepath": "src/api/files.py",
                "line_number": 6,
                "col_number": 5,
                "code_snippet": '6:     with open(full_path, "r") as f:',
                "fingerprint": "fp_path_traversal_api_files",
                "state": "open"
            }
        ]

        save_scan_results(
            scan_id=pr_scan_id,
            issues=pr_issues,
            duration_ms=520,
            files_scanned=3,
            files_skipped=6
        )

        update_scan_pr_metrics(
            scan_id=pr_scan_id,
            verdict="BLOCK",
            new_count=1,
            fixed_count=0,
            existing_count=2,
            check_run_id=5544332211
        )

        # Deterministic PRSummaryFacts for PR #1
        pr_facts = PRSummaryFacts(
            version=1,
            pr=PRDetails(
                number=1,
                head_sha=pr_head_sha,
                base_sha=baseline_commit,
                title="Add file viewer endpoint and dependency updates",
                author="demo_developer",
                files_changed=2,
                additions=14,
                deletions=2
            ),
            categories_touched=["auth", "dependency manifests"],
            findings=FindingsGroup(
                new=[
                    FindingSummaryItem(
                        finding_id="finding_path_trav_01",
                        fingerprint="fp_path_traversal_api_files",
                        severity="critical",
                        rule_id="python.lang.security.audit.path-traversal",
                        message="Path traversal via unsanitized user file parameter in src/api/files.py",
                        file="src/api/files.py",
                        line=6,
                        has_verified_fix=False
                    )
                ],
                fixed=[],
                existing_touched=[],
                hidden_existing_count=2
            ),
            dependency_changes=[
                DependencyChange(
                    ecosystem="pip",
                    name="pydantic",
                    change_type="added",
                    version="2.6.4",
                    manifest_file="requirements.txt"
                ),
                DependencyChange(
                    ecosystem="pip",
                    name="pyyaml",
                    change_type="added",
                    version="6.0.1",
                    manifest_file="requirements.txt"
                )
            ],
            delta_since_previous_push=PushDelta(
                new_count=1,
                fixed_count=0,
                delta_new=1,
                delta_fixed=0
            ),
            verdict="block",
            reasons=[
                "1 new finding(s) meet or exceed repository block threshold ('high').",
                "1 Critical severity vulnerability must be fixed before merge."
            ],
            actions=[
                ActionItem(
                    priority=1,
                    category="secrets_rotation",
                    title="Rotate this credential: Rotate leaked secret in src/config.py:6",
                    description="Rotate this credential immediately; removing it from code or history is secondary. Revoke in provider console and update secrets manager.",
                    file="src/config.py",
                    line=6
                ),
                ActionItem(
                    priority=2,
                    category="critical_finding",
                    title="[CRITICAL] Remediate python.lang.security.audit.path-traversal in src/api/files.py:6",
                    description="Path traversal via unsanitized user file parameter",
                    file="src/api/files.py",
                    line=6
                ),
                ActionItem(
                    priority=4,
                    category="dependency_audit",
                    title="Audit 2 dependency change(s)",
                    description="Inspect newly introduced packages (pydantic, pyyaml) for supply-chain risks and exact version pinning."
                )
            ]
        )

        save_pr_summary(
            repo_id=repo_id,
            pr_number=1,
            scan_id=pr_scan_id,
            head_sha=pr_head_sha,
            facts=pr_facts.model_dump() if hasattr(pr_facts, "model_dump") else pr_facts.dict(),
            narrative="CodeVanguard blocked Pull Request #1: 1 new Critical vulnerability (path traversal in src/api/files.py) and 2 new dependencies added.",
            narrative_source="template"
        )

        conn.commit()

    print("[CodeVanguard Seed] Demo data seeded successfully!")
    print(f"  - Repository ID: {repo_id} ('demo-org/vulnerable-microservice')")
    print(f"  - Baseline Scan ID: {baseline_scan_id}")
    print(f"  - Pull Request #1 Scan ID: {pr_scan_id}")
    print(f"  - Verified Auto-Fix Attempt ID: fix_attempt_demo_sql_1")
    print("Ready to explore at http://localhost:3000/repos/" + repo_id)

if __name__ == "__main__":
    seed_demo_environment()
