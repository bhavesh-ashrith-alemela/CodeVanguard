-- Migration 004: Pull Request Scanning, Baseline Tracking & Finding Lifecycle
-- Target: PostgreSQL / Supabase & SQLite Adapter

-- 1. Webhook deliveries table for auditability and idempotency
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id TEXT PRIMARY KEY,
    event TEXT NOT NULL,
    action TEXT,
    repository_id TEXT REFERENCES repositories(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'received',
    error_message TEXT,
    created_at TEXT NOT NULL
);

-- 2. Repositories expansion for PR baseline and scan settings
ALTER TABLE repositories ADD COLUMN IF NOT EXISTS baseline_scan_id TEXT REFERENCES scans(id) ON DELETE SET NULL;
ALTER TABLE repositories ADD COLUMN IF NOT EXISTS pr_comment_enabled BOOLEAN NOT NULL DEFAULT 1;
ALTER TABLE repositories ADD COLUMN IF NOT EXISTS sarif_upload_enabled BOOLEAN NOT NULL DEFAULT 1;
ALTER TABLE repositories ADD COLUMN IF NOT EXISTS scan_on_pr BOOLEAN NOT NULL DEFAULT 1;
ALTER TABLE repositories ADD COLUMN IF NOT EXISTS scan_on_push BOOLEAN NOT NULL DEFAULT 1;
ALTER TABLE repositories ADD COLUMN IF NOT EXISTS fail_on TEXT NOT NULL DEFAULT 'high';
ALTER TABLE repositories ADD COLUMN IF NOT EXISTS scan_drafts BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE repositories ADD COLUMN IF NOT EXISTS ignore_globs TEXT DEFAULT '';

-- 3. Findings table for repository baseline and lifecycle tracking
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    filepath TEXT NOT NULL,
    line_number INTEGER,
    first_seen_commit TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    introduced_by_pr INTEGER,
    state TEXT NOT NULL DEFAULT 'open',
    suppressed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    suppressed_at TEXT,
    reason TEXT,
    UNIQUE (repo_id, fingerprint)
);

-- 4. Issues linkage to findings
ALTER TABLE issues ADD COLUMN IF NOT EXISTS finding_id TEXT REFERENCES findings(id) ON DELETE SET NULL;
ALTER TABLE issues ADD COLUMN IF NOT EXISTS is_new BOOLEAN NOT NULL DEFAULT 1;

-- 5. Scans verdict and PR metrics
ALTER TABLE scans ADD COLUMN IF NOT EXISTS verdict TEXT;
ALTER TABLE scans ADD COLUMN IF NOT EXISTS check_run_id BIGINT;
ALTER TABLE scans ADD COLUMN IF NOT EXISTS new_findings_count INTEGER DEFAULT 0;
ALTER TABLE scans ADD COLUMN IF NOT EXISTS fixed_findings_count INTEGER DEFAULT 0;
ALTER TABLE scans ADD COLUMN IF NOT EXISTS existing_findings_count INTEGER DEFAULT 0;

-- 6. Indexes
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_created ON webhook_deliveries (created_at);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_repo ON webhook_deliveries (repository_id);
CREATE INDEX IF NOT EXISTS idx_findings_repo_state ON findings (repo_id, state);
CREATE INDEX IF NOT EXISTS idx_findings_repo_pr ON findings (repo_id, introduced_by_pr);
CREATE INDEX IF NOT EXISTS idx_issues_finding ON issues (finding_id);
CREATE INDEX IF NOT EXISTS idx_scans_repo_pr ON scans (repo_id, pr_number);
