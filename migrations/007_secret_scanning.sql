-- Migration 007: Secret Detection in Git History and Source Files
-- Supports masked previews, salted hashes for deduplication, and HEAD vs History-Only classification.

ALTER TABLE findings ADD COLUMN IF NOT EXISTS masked_secret TEXT;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS secret_hash TEXT;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS detector TEXT;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS commit_sha TEXT;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS commit_date TEXT;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS still_in_head BOOLEAN DEFAULT TRUE;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS is_secret BOOLEAN DEFAULT FALSE;

ALTER TABLE issues ADD COLUMN IF NOT EXISTS masked_secret TEXT;
ALTER TABLE issues ADD COLUMN IF NOT EXISTS secret_hash TEXT;
ALTER TABLE issues ADD COLUMN IF NOT EXISTS detector TEXT;
ALTER TABLE issues ADD COLUMN IF NOT EXISTS commit_sha TEXT;
ALTER TABLE issues ADD COLUMN IF NOT EXISTS commit_date TEXT;
ALTER TABLE issues ADD COLUMN IF NOT EXISTS still_in_head BOOLEAN DEFAULT TRUE;
ALTER TABLE issues ADD COLUMN IF NOT EXISTS is_secret BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_findings_repo_secret ON findings (repo_id, is_secret);
CREATE INDEX IF NOT EXISTS idx_findings_repo_secret_hash ON findings (repo_id, secret_hash);
CREATE INDEX IF NOT EXISTS idx_issues_secret ON issues (is_secret);
