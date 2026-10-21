-- Migration 006: Auto-Fix Attempts, Quotas & Repository Settings
-- Target: PostgreSQL / Supabase & SQLite Adapter

CREATE TABLE IF NOT EXISTS fix_attempts (
    id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued', -- queued | generated | verified | rejected | pr_opened | merged | closed
    provider TEXT NOT NULL,                -- gemini | anthropic | openai | ollama
    model TEXT NOT NULL,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    target_file TEXT NOT NULL,
    target_function TEXT,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    diff TEXT,
    patch_code TEXT,
    explanation TEXT,
    verification_json JSONB,
    rejection_reason TEXT,
    pr_number INTEGER,
    pr_url TEXT,
    branch_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fix_attempts_finding ON fix_attempts (finding_id, status);
CREATE INDEX IF NOT EXISTS idx_fix_attempts_repo_created ON fix_attempts (repo_id, created_at DESC);

ALTER TABLE repositories ADD COLUMN IF NOT EXISTS autofix_enabled BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE repositories ADD COLUMN IF NOT EXISTS autofix_daily_quota INTEGER NOT NULL DEFAULT 20;
