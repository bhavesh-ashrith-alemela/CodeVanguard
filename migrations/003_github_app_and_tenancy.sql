-- Migration 003: GitHub App, Installations, Multi-Tenant Repositories & Scans
-- Target: PostgreSQL / Supabase & SQLite Adapter

-- 1. Users expansion for GitHub OAuth
ALTER TABLE users ADD COLUMN IF NOT EXISTS github_id BIGINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS github_login TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS encrypted_user_token TEXT;

-- 2. Installations table
CREATE TABLE IF NOT EXISTS installations (
    id TEXT PRIMARY KEY,
    github_installation_id BIGINT UNIQUE NOT NULL,
    account_login TEXT NOT NULL,
    account_type TEXT NOT NULL,
    account_avatar_url TEXT,
    suspended_at TEXT,
    deleted_at TEXT,
    created_at TEXT NOT NULL
);

-- 3. Installation Members table (who may access the installation)
CREATE TABLE IF NOT EXISTS installation_members (
    installation_id TEXT NOT NULL REFERENCES installations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',
    created_at TEXT NOT NULL,
    PRIMARY KEY (installation_id, user_id)
);

-- 4. Repositories table
CREATE TABLE IF NOT EXISTS repositories (
    id TEXT PRIMARY KEY,
    installation_id TEXT NOT NULL REFERENCES installations(id) ON DELETE CASCADE,
    github_repo_id BIGINT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    default_branch TEXT NOT NULL DEFAULT 'main',
    is_private BOOLEAN NOT NULL DEFAULT 0,
    scan_enabled BOOLEAN NOT NULL DEFAULT 1,
    settings TEXT NOT NULL DEFAULT '{}',
    last_scanned_at TEXT,
    deleted_at TEXT,
    created_at TEXT NOT NULL
);

-- 5. Scans linkage
ALTER TABLE scans ADD COLUMN IF NOT EXISTS repo_id TEXT REFERENCES repositories(id) ON DELETE SET NULL;
ALTER TABLE scans ADD COLUMN IF NOT EXISTS owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE scans ADD COLUMN IF NOT EXISTS trigger TEXT DEFAULT 'manual';
ALTER TABLE scans ADD COLUMN IF NOT EXISTS pr_number INTEGER;

-- 6. Indexes for multi-tenant queries & foreign keys
CREATE INDEX IF NOT EXISTS idx_users_github_id ON users (github_id);
CREATE INDEX IF NOT EXISTS idx_installations_gh_id ON installations (github_installation_id);
CREATE INDEX IF NOT EXISTS idx_inst_members_user ON installation_members (user_id);
CREATE INDEX IF NOT EXISTS idx_repos_installation_id ON repositories (installation_id);
CREATE INDEX IF NOT EXISTS idx_repos_gh_id ON repositories (github_repo_id);
CREATE INDEX IF NOT EXISTS idx_repos_full_name ON repositories (full_name);
CREATE INDEX IF NOT EXISTS idx_scans_repo_id ON scans (repo_id);
CREATE INDEX IF NOT EXISTS idx_scans_owner_user ON scans (owner_user_id);
