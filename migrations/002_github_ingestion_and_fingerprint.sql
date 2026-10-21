-- Migration 002: GitHub Ingestion, Scanning Metrics, and Fingerprinting
-- Target: PostgreSQL / Supabase

-- Add GitHub intake, metrics, and progress columns to scans table
ALTER TABLE scans ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'paste';
ALTER TABLE scans ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE scans ADD COLUMN IF NOT EXISTS branch TEXT;
ALTER TABLE scans ADD COLUMN IF NOT EXISTS commit_sha TEXT;
ALTER TABLE scans ADD COLUMN IF NOT EXISTS duration_ms INTEGER DEFAULT 0;
ALTER TABLE scans ADD COLUMN IF NOT EXISTS files_scanned INTEGER DEFAULT 0;
ALTER TABLE scans ADD COLUMN IF NOT EXISTS files_skipped INTEGER DEFAULT 0;
ALTER TABLE scans ADD COLUMN IF NOT EXISTS progress TEXT DEFAULT 'queued';

-- Add fingerprint and issue state to issues table
ALTER TABLE issues ADD COLUMN IF NOT EXISTS fingerprint TEXT;
ALTER TABLE issues ADD COLUMN IF NOT EXISTS state TEXT DEFAULT 'open';

-- Indexes for performance & deduplication
CREATE INDEX IF NOT EXISTS idx_issues_fingerprint ON issues (fingerprint);
CREATE INDEX IF NOT EXISTS idx_scans_status_timestamp ON scans (status, timestamp);
