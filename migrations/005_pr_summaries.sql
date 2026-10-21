-- Migration 005: Pull Request Summaries, Facts & Reviewer Needs
-- Target: PostgreSQL / Supabase & SQLite Adapter

CREATE TABLE IF NOT EXISTS pr_summaries (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    pr_number INTEGER NOT NULL,
    scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    head_sha TEXT NOT NULL,
    facts JSONB NOT NULL,
    narrative TEXT,
    narrative_source TEXT NOT NULL DEFAULT 'template',
    model TEXT,
    summary_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE (repo_id, pr_number, head_sha)
);

CREATE INDEX IF NOT EXISTS idx_pr_summaries_repo_pr ON pr_summaries (repo_id, pr_number, created_at DESC);

ALTER TABLE repositories ADD COLUMN IF NOT EXISTS narrative_enabled BOOLEAN NOT NULL DEFAULT 0;
