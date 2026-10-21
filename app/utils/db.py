import sqlite3
import json
import os
import hashlib
import secrets
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, List, Dict, Tuple, Any

# PostgreSQL imports (used if DATABASE_URL environment variable is set)
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2.pool import ThreadedConnectionPool
except ImportError:
    psycopg2 = None
    RealDictCursor = None
    ThreadedConnectionPool = None

DB_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
DB_PATH = os.path.join(DB_DIR, "codevanguard.db")

# Ensure database directory exists (useful for container volumes on Render)
os.makedirs(DB_DIR, exist_ok=True)

_pg_pool = None

def get_pg_pool():
    """Lazily initializes and returns the PostgreSQL ThreadedConnectionPool."""
    global _pg_pool
    if _pg_pool is None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            return None
        if psycopg2 is None:
            raise RuntimeError("DATABASE_URL is set but psycopg2 is not installed!")
        
        # Enforce sslmode=require for Supabase / production connection pooler
        if "sslmode=" not in database_url:
            sep = "&" if "?" in database_url else "?"
            database_url = f"{database_url}{sep}sslmode=require"
            
        min_conn = int(os.environ.get("DB_POOL_MIN", 1))
        max_conn = int(os.environ.get("DB_POOL_MAX", 5))
        _pg_pool = ThreadedConnectionPool(minconn=min_conn, maxconn=max_conn, dsn=database_url)
    return _pg_pool

class PostgresCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor
    
    def execute(self, query, params=None):
        # Translate SQLite primary key auto-increment to Postgres SERIAL
        query = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        # Translate SQLite ? placeholders to Postgres %s
        query = query.replace("?", "%s")
        if params:
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)

    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cursor.close()
            
    def __getattr__(self, name):
        return getattr(self.cursor, name)

class PostgresConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn
        
    def cursor(self):
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        return PostgresCursorWrapper(cursor)
        
    def commit(self):
        self.conn.commit()
        
    def rollback(self):
        self.conn.rollback()
        
    def close(self):
        self.conn.close()

@contextmanager
def get_db_connection():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        pool = get_pg_pool()
        conn = pool.getconn()
        try:
            yield PostgresConnectionWrapper(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            pool.putconn(conn)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

def _apply_sqlite_migration_002(cursor):
    """Applies schema additions for migration 002 onto SQLite safely."""
    cursor.execute("PRAGMA table_info(scans)")
    scan_cols = {row["name"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[1] for row in cursor.fetchall()}
    
    if "source_type" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN source_type TEXT DEFAULT 'paste'")
    if "source_url" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN source_url TEXT")
    if "branch" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN branch TEXT")
    if "commit_sha" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN commit_sha TEXT")
    if "duration_ms" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN duration_ms INTEGER DEFAULT 0")
    if "files_scanned" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN files_scanned INTEGER DEFAULT 0")
    if "files_skipped" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN files_skipped INTEGER DEFAULT 0")
    if "progress" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN progress TEXT DEFAULT 'queued'")

    cursor.execute("PRAGMA table_info(issues)")
    issue_cols = {row["name"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[1] for row in cursor.fetchall()}
    if "fingerprint" not in issue_cols:
        cursor.execute("ALTER TABLE issues ADD COLUMN fingerprint TEXT")
    if "state" not in issue_cols:
        cursor.execute("ALTER TABLE issues ADD COLUMN state TEXT DEFAULT 'open'")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_issues_fingerprint ON issues (fingerprint)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scans_status_timestamp ON scans (status, timestamp)")

def _apply_sqlite_migration_003(cursor):
    """Applies schema additions for migration 003 onto SQLite safely."""
    cursor.execute("PRAGMA table_info(users)")
    user_cols = {row["name"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[1] for row in cursor.fetchall()}
    if "github_id" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN github_id BIGINT")
    if "github_login" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN github_login TEXT")
    if "avatar_url" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
    if "encrypted_user_token" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN encrypted_user_token TEXT")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS installations (
            id TEXT PRIMARY KEY,
            github_installation_id BIGINT UNIQUE NOT NULL,
            account_login TEXT NOT NULL,
            account_type TEXT NOT NULL,
            account_avatar_url TEXT,
            suspended_at TEXT,
            deleted_at TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS installation_members (
            installation_id TEXT NOT NULL REFERENCES installations(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'member',
            created_at TEXT NOT NULL,
            PRIMARY KEY (installation_id, user_id)
        )
    """)

    cursor.execute("""
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
        )
    """)

    cursor.execute("PRAGMA table_info(scans)")
    scan_cols = {row["name"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[1] for row in cursor.fetchall()}
    if "repo_id" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN repo_id TEXT REFERENCES repositories(id) ON DELETE SET NULL")
    if "owner_user_id" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
    if "trigger" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN trigger TEXT DEFAULT 'manual'")
    if "pr_number" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN pr_number INTEGER")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_github_id ON users (github_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_installations_gh_id ON installations (github_installation_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inst_members_user ON installation_members (user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_repos_installation_id ON repositories (installation_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_repos_gh_id ON repositories (github_repo_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_repos_full_name ON repositories (full_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scans_repo_id ON scans (repo_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scans_owner_user ON scans (owner_user_id)")

def _apply_sqlite_migration_004(cursor):
    """Applies schema additions for migration 004 onto SQLite safely."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS webhook_deliveries (
            id TEXT PRIMARY KEY,
            event TEXT NOT NULL,
            action TEXT,
            repository_id TEXT REFERENCES repositories(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'received',
            error_message TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("PRAGMA table_info(repositories)")
    repo_cols = {row["name"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[1] for row in cursor.fetchall()}
    if "baseline_scan_id" not in repo_cols:
        cursor.execute("ALTER TABLE repositories ADD COLUMN baseline_scan_id TEXT REFERENCES scans(id) ON DELETE SET NULL")
    if "pr_comment_enabled" not in repo_cols:
        cursor.execute("ALTER TABLE repositories ADD COLUMN pr_comment_enabled BOOLEAN NOT NULL DEFAULT 1")
    if "sarif_upload_enabled" not in repo_cols:
        cursor.execute("ALTER TABLE repositories ADD COLUMN sarif_upload_enabled BOOLEAN NOT NULL DEFAULT 1")
    if "scan_on_pr" not in repo_cols:
        cursor.execute("ALTER TABLE repositories ADD COLUMN scan_on_pr BOOLEAN NOT NULL DEFAULT 1")
    if "scan_on_push" not in repo_cols:
        cursor.execute("ALTER TABLE repositories ADD COLUMN scan_on_push BOOLEAN NOT NULL DEFAULT 1")
    if "fail_on" not in repo_cols:
        cursor.execute("ALTER TABLE repositories ADD COLUMN fail_on TEXT NOT NULL DEFAULT 'high'")
    if "scan_drafts" not in repo_cols:
        cursor.execute("ALTER TABLE repositories ADD COLUMN scan_drafts BOOLEAN NOT NULL DEFAULT 0")
    if "ignore_globs" not in repo_cols:
        cursor.execute("ALTER TABLE repositories ADD COLUMN ignore_globs TEXT DEFAULT ''")

    cursor.execute("""
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
        )
    """)

    cursor.execute("PRAGMA table_info(issues)")
    issue_cols = {row["name"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[1] for row in cursor.fetchall()}
    if "finding_id" not in issue_cols:
        cursor.execute("ALTER TABLE issues ADD COLUMN finding_id TEXT REFERENCES findings(id) ON DELETE SET NULL")
    if "is_new" not in issue_cols:
        cursor.execute("ALTER TABLE issues ADD COLUMN is_new BOOLEAN NOT NULL DEFAULT 1")

    cursor.execute("PRAGMA table_info(scans)")
    scan_cols = {row["name"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[1] for row in cursor.fetchall()}
    if "verdict" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN verdict TEXT")
    if "check_run_id" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN check_run_id BIGINT")
    if "new_findings_count" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN new_findings_count INTEGER DEFAULT 0")
    if "fixed_findings_count" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN fixed_findings_count INTEGER DEFAULT 0")
    if "existing_findings_count" not in scan_cols:
        cursor.execute("ALTER TABLE scans ADD COLUMN existing_findings_count INTEGER DEFAULT 0")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_created ON webhook_deliveries (created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_repo ON webhook_deliveries (repository_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_repo_state ON findings (repo_id, state)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_repo_pr ON findings (repo_id, introduced_by_pr)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_issues_finding ON issues (finding_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scans_repo_pr ON scans (repo_id, pr_number)")

def _apply_sqlite_migration_005(cursor):
    """Applies schema additions for migration 005 onto SQLite safely."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pr_summaries (
            id TEXT PRIMARY KEY,
            repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            pr_number INTEGER NOT NULL,
            scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
            head_sha TEXT NOT NULL,
            facts TEXT NOT NULL,
            narrative TEXT,
            narrative_source TEXT NOT NULL DEFAULT 'template',
            model TEXT,
            summary_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            UNIQUE (repo_id, pr_number, head_sha)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pr_summaries_repo_pr ON pr_summaries (repo_id, pr_number, created_at DESC)")

    cursor.execute("PRAGMA table_info(repositories)")
    repo_cols = {row["name"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[1] for row in cursor.fetchall()}
    if "narrative_enabled" not in repo_cols:
        cursor.execute("ALTER TABLE repositories ADD COLUMN narrative_enabled BOOLEAN NOT NULL DEFAULT 0")

def _apply_sqlite_migration_006(cursor):
    """Applies schema additions for migration 006 onto SQLite safely."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fix_attempts (
            id TEXT PRIMARY KEY,
            finding_id TEXT NOT NULL,
            repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'queued',
            provider TEXT NOT NULL,
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
            verification_json TEXT,
            rejection_reason TEXT,
            pr_number INTEGER,
            pr_url TEXT,
            branch_name TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fix_attempts_finding ON fix_attempts (finding_id, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fix_attempts_repo_created ON fix_attempts (repo_id, created_at DESC)")

    cursor.execute("PRAGMA table_info(repositories)")
    repo_cols = {row["name"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[1] for row in cursor.fetchall()}
    if "autofix_enabled" not in repo_cols:
        cursor.execute("ALTER TABLE repositories ADD COLUMN autofix_enabled BOOLEAN NOT NULL DEFAULT 0")
    if "autofix_daily_quota" not in repo_cols:
        cursor.execute("ALTER TABLE repositories ADD COLUMN autofix_daily_quota INTEGER NOT NULL DEFAULT 20")

def _apply_sqlite_migration_007(cursor):
    """Applies schema additions for migration 007 (secret scanning) onto SQLite safely."""
    cursor.execute("PRAGMA table_info(findings)")
    finding_cols = {row["name"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[1] for row in cursor.fetchall()}
    if "masked_secret" not in finding_cols:
        cursor.execute("ALTER TABLE findings ADD COLUMN masked_secret TEXT")
    if "secret_hash" not in finding_cols:
        cursor.execute("ALTER TABLE findings ADD COLUMN secret_hash TEXT")
    if "detector" not in finding_cols:
        cursor.execute("ALTER TABLE findings ADD COLUMN detector TEXT")
    if "commit_sha" not in finding_cols:
        cursor.execute("ALTER TABLE findings ADD COLUMN commit_sha TEXT")
    if "commit_date" not in finding_cols:
        cursor.execute("ALTER TABLE findings ADD COLUMN commit_date TEXT")
    if "still_in_head" not in finding_cols:
        cursor.execute("ALTER TABLE findings ADD COLUMN still_in_head BOOLEAN DEFAULT 1")
    if "is_secret" not in finding_cols:
        cursor.execute("ALTER TABLE findings ADD COLUMN is_secret BOOLEAN DEFAULT 0")

    cursor.execute("PRAGMA table_info(issues)")
    issue_cols = {row["name"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[1] for row in cursor.fetchall()}
    if "masked_secret" not in issue_cols:
        cursor.execute("ALTER TABLE issues ADD COLUMN masked_secret TEXT")
    if "secret_hash" not in issue_cols:
        cursor.execute("ALTER TABLE issues ADD COLUMN secret_hash TEXT")
    if "detector" not in issue_cols:
        cursor.execute("ALTER TABLE issues ADD COLUMN detector TEXT")
    if "commit_sha" not in issue_cols:
        cursor.execute("ALTER TABLE issues ADD COLUMN commit_sha TEXT")
    if "commit_date" not in issue_cols:
        cursor.execute("ALTER TABLE issues ADD COLUMN commit_date TEXT")
    if "still_in_head" not in issue_cols:
        cursor.execute("ALTER TABLE issues ADD COLUMN still_in_head BOOLEAN DEFAULT 1")
    if "is_secret" not in issue_cols:
        cursor.execute("ALTER TABLE issues ADD COLUMN is_secret BOOLEAN DEFAULT 0")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_repo_secret ON findings (repo_id, is_secret)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_repo_secret_hash ON findings (repo_id, secret_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_issues_secret ON issues (is_secret)")

def apply_migrations(conn):
    """
    Applies versioned SQL migrations located in the migrations/ directory.
    Uses schema_migrations table to track applied versions.
    """
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)
    conn.commit()

    migrations_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "migrations")
    if not os.path.exists(migrations_dir):
        return

    cursor.execute("SELECT version FROM schema_migrations")
    applied = {row["version"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[0] for row in cursor.fetchall()}

    is_postgres = bool(os.environ.get("DATABASE_URL"))
    migration_files = sorted([f for f in os.listdir(migrations_dir) if f.endswith(".sql")])

    for mig_file in migration_files:
        version = os.path.splitext(mig_file)[0]
        if version in applied:
            continue

        file_path = os.path.join(migrations_dir, mig_file)
        with open(file_path, "r", encoding="utf-8") as f:
            sql_content = f.read()

        if is_postgres:
            for statement in sql_content.split(";"):
                stmt = statement.strip()
                if stmt:
                    cursor.execute(stmt)
        else:
            if version == "002_github_ingestion_and_fingerprint":
                _apply_sqlite_migration_002(cursor)
            elif version == "003_github_app_and_tenancy":
                _apply_sqlite_migration_003(cursor)
            elif version == "004_pr_scanning_and_findings":
                _apply_sqlite_migration_004(cursor)
            elif version == "005_pr_summaries":
                _apply_sqlite_migration_005(cursor)
            elif version == "006_autofix":
                _apply_sqlite_migration_006(cursor)
            elif version == "007_secret_scanning":
                _apply_sqlite_migration_007(cursor)

        cursor.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (version, datetime.now().isoformat()))
        conn.commit()
        print(f"CodeVanguard: Applied database migration {version}")

def init_db():
    """Initializes the database schema and default admin account."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Baseline Scans table (all columns)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                total_issues INTEGER DEFAULT 0,
                critical_count INTEGER DEFAULT 0,
                high_count INTEGER DEFAULT 0,
                medium_count INTEGER DEFAULT 0,
                low_count INTEGER DEFAULT 0,
                source_type TEXT DEFAULT 'paste',
                source_url TEXT,
                branch TEXT,
                commit_sha TEXT,
                duration_ms INTEGER DEFAULT 0,
                files_scanned INTEGER DEFAULT 0,
                files_skipped INTEGER DEFAULT 0,
                progress TEXT DEFAULT 'queued'
            )
        """)
        
        # Baseline Issues table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id TEXT NOT NULL,
                scanner TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                filepath TEXT NOT NULL,
                line_number INTEGER,
                col_number INTEGER,
                code_snippet TEXT,
                fingerprint TEXT,
                state TEXT DEFAULT 'open',
                FOREIGN KEY (scan_id) REFERENCES scans (id) ON DELETE CASCADE
            )
        """)
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL
            )
        """)
        
        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        
        # Audit Logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        
        # Base Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_issues_scan_id ON issues (scan_id)")
        
        # Run versioned migrations
        apply_migrations(conn)

        # Enable Row Level Security (RLS) on PostgreSQL tables (for Supabase security compliance)
        if os.environ.get("DATABASE_URL"):
            cursor.execute("ALTER TABLE scans ENABLE ROW LEVEL SECURITY;")
            cursor.execute("ALTER TABLE issues ENABLE ROW LEVEL SECURITY;")
            cursor.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY;")
            cursor.execute("ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;")
            cursor.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;")
            cursor.execute("ALTER TABLE installations ENABLE ROW LEVEL SECURITY;")
            cursor.execute("ALTER TABLE installation_members ENABLE ROW LEVEL SECURITY;")
            cursor.execute("ALTER TABLE repositories ENABLE ROW LEVEL SECURITY;")

        conn.commit()
        
        # Auto-create default admin account if users table is empty
        cursor.execute("SELECT COUNT(*) as count FROM users")
        if cursor.fetchone()["count"] == 0:
            default_admin_user = os.environ.get("DEFAULT_ADMIN_USER", "admin")
            default_admin_pass = os.environ.get("DEFAULT_ADMIN_PASS")
            
            is_prod = os.environ.get("ENV", "development").lower() == "production"
            if not default_admin_pass:
                if is_prod:
                    raise RuntimeError("SECURITY ERROR: DEFAULT_ADMIN_PASS environment variable MUST be defined in production mode!")
                default_admin_pass = "VanguardAdmin2026!"
                
            hashed = hash_password(default_admin_pass)
            cursor.execute("""
                INSERT INTO users (username, hashed_password, role, created_at)
                VALUES (?, ?, 'admin', ?)
            """, (default_admin_user, hashed, datetime.now().isoformat()))
            conn.commit()
            is_default = default_admin_pass == "VanguardAdmin2026!"
            mask_pass = default_admin_pass if is_default else "********"
            print(f"CodeVanguard: Created default admin account (username: '{default_admin_user}', password: '{mask_pass}')")

def create_scan(
    scan_id: str,
    filename: str,
    file_size: int,
    source_type: str = "paste",
    source_url: str = None,
    branch: str = None,
    commit_sha: str = None,
    repo_id: str = None,
    owner_user_id: int = None,
    trigger: str = "manual",
    pr_number: int = None
) -> dict:
    """Inserts a new scan with status 'pending' and progress 'queued'."""
    timestamp = datetime.now().isoformat()
    status = "pending"
    progress = "queued"
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO scans (
                id, timestamp, filename, file_size, status, progress,
                source_type, source_url, branch, commit_sha,
                repo_id, owner_user_id, trigger, pr_number
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            scan_id, timestamp, filename, file_size, status, progress,
            source_type, source_url, branch, commit_sha,
            repo_id, owner_user_id, trigger, pr_number
        ))
        conn.commit()
        
    return {
        "id": scan_id,
        "timestamp": timestamp,
        "filename": filename,
        "file_size": file_size,
        "status": status,
        "progress": progress,
        "source_type": source_type,
        "source_url": source_url,
        "branch": branch,
        "commit_sha": commit_sha,
        "repo_id": repo_id,
        "owner_user_id": owner_user_id,
        "trigger": trigger,
        "pr_number": pr_number,
        "error_message": None,
        "total_issues": 0,
        "critical_count": 0,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 0,
        "duration_ms": 0,
        "files_scanned": 0,
        "files_skipped": 0
    }

def update_scan_status(scan_id: str, status: str, error_message: str = None) -> bool:
    """Updates the status and optional error message of a scan."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if status == "running":
            cursor.execute("""
                UPDATE scans
                SET status = ?, error_message = ?
                WHERE id = ? AND status NOT IN ('failed', 'completed', 'cancelled')
            """, (status, error_message, scan_id))
            conn.commit()
            return cursor.rowcount > 0
        else:
            cursor.execute("""
                UPDATE scans
                SET status = ?, error_message = ?
                WHERE id = ?
            """, (status, error_message, scan_id))
            conn.commit()
            return cursor.rowcount > 0

def update_scan_progress(scan_id: str, progress: str, status: str = None):
    """Updates the progress string and optional status of a scan."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute("""
                UPDATE scans
                SET progress = ?, status = ?
                WHERE id = ?
            """, (progress, status, scan_id))
        else:
            cursor.execute("""
                UPDATE scans
                SET progress = ?
                WHERE id = ?
            """, (progress, scan_id))
        conn.commit()

def update_scan_metrics(scan_id: str, duration_ms: int = 0, files_scanned: int = 0, files_skipped: int = 0):
    """Updates execution duration and file count metrics."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE scans
            SET duration_ms = ?, files_scanned = ?, files_skipped = ?
            WHERE id = ?
        """, (duration_ms, files_scanned, files_skipped, scan_id))
        conn.commit()

def save_scan_results(
    scan_id: str,
    issues: list,
    duration_ms: int = 0,
    files_scanned: int = 0,
    files_skipped: int = 0
):
    """
    Saves parsed issues to the database, computes fingerprints,
    and updates scan statistics/status to 'completed'.
    """
    from app.utils.fingerprint import compute_fingerprint

    total_issues = len(issues)
    critical_count = 0
    high_count = 0
    medium_count = 0
    low_count = 0

    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM issues WHERE scan_id = ?", (scan_id,))
        
        for issue in issues:
            severity = issue.get("severity", "low").lower()
            if severity == "critical":
                critical_count += 1
            elif severity == "high":
                high_count += 1
            elif severity == "medium":
                medium_count += 1
            else:
                low_count += 1

            fp = issue.get("fingerprint") or compute_fingerprint(
                issue.get("rule_id", ""),
                issue.get("filepath", ""),
                issue.get("code_snippet", "")
            )
            state = issue.get("state", "open")
                
            is_secret = 1 if (issue.get("is_secret") or issue.get("scanner") == "secret") else 0
            cursor.execute("""
                INSERT INTO issues (
                    scan_id, scanner, rule_id, severity, message, filepath,
                    line_number, col_number, code_snippet, fingerprint, state,
                    masked_secret, secret_hash, detector, commit_sha, commit_date,
                    still_in_head, is_secret
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                scan_id,
                issue.get("scanner"),
                issue.get("rule_id"),
                severity,
                issue.get("message"),
                issue.get("filepath"),
                issue.get("line_number"),
                issue.get("col_number"),
                issue.get("code_snippet"),
                fp,
                state,
                issue.get("masked_secret"),
                issue.get("secret_hash"),
                issue.get("detector"),
                issue.get("commit_sha"),
                issue.get("commit_date"),
                1 if issue.get("still_in_head", True) else 0,
                is_secret
            ))
            
        cursor.execute("""
            UPDATE scans
            SET status = 'completed',
                progress = 'completed',
                total_issues = ?,
                critical_count = ?,
                high_count = ?,
                medium_count = ?,
                low_count = ?,
                duration_ms = ?,
                files_scanned = ?,
                files_skipped = ?
            WHERE id = ?
        """, (
            total_issues, critical_count, high_count, medium_count, low_count,
            duration_ms, files_scanned, files_skipped, scan_id
        ))
        conn.commit()

def get_scan(scan_id: str) -> dict:
    """Fetches a scan by its ID. Returns None if not found."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scans WHERE id = ?", (scan_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_scan_issues(scan_id: str) -> list:
    """Fetches all issues for a scan."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM issues WHERE scan_id = ? ORDER BY id ASC", (scan_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_scan_history(user_id: int = None, repo_id: str = None, limit: int = 100) -> list:
    """
    Fetches scan records ordered by timestamp descending.
    If repo_id is supplied, restricts to that repository.
    If user_id is supplied, restricts to scans owned by the user or belonging to installations they are a member of.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if repo_id:
            cursor.execute("""
                SELECT * FROM scans 
                WHERE repo_id = ? 
                ORDER BY timestamp DESC LIMIT ?
            """, (repo_id, limit))
        elif user_id is not None:
            cursor.execute("""
                SELECT s.* FROM scans s
                WHERE s.owner_user_id = ?
                   OR s.repo_id IN (
                       SELECT r.id FROM repositories r
                       JOIN installation_members im ON r.installation_id = im.installation_id
                       WHERE im.user_id = ?
                   )
                ORDER BY s.timestamp DESC LIMIT ?
            """, (user_id, user_id, limit))
        else:
            cursor.execute("SELECT * FROM scans ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def delete_scan(scan_id: str):
    """Deletes a scan and its associated issues."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM issues WHERE scan_id = ?", (scan_id,))
        cursor.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
        conn.commit()

# --- Password Security & Authentication ---

def hash_password(password: str) -> str:
    """Hashes a password using PBKDF2-SHA256 with 100,000 iterations."""
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        100000
    )
    return f"{salt.hex()}:{key.hex()}"

def verify_password(stored_password: str, provided_password: str) -> bool:
    """Verifies a password against its PBKDF2 hash using timing-attack resistant comparison."""
    try:
        salt_hex, key_hex = stored_password.split(':')
        salt = bytes.fromhex(salt_hex)
        key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac(
            'sha256',
            provided_password.encode('utf-8'),
            salt,
            100000
        )
        return secrets.compare_digest(key, new_key)
    except Exception:
        return False

def authenticate_user(username, password) -> dict:
    """Verifies credentials. Returns the user dict if valid, else None."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row:
            user = dict(row)
            if verify_password(user["hashed_password"], password):
                return user
    return None

def create_session(user_id: int) -> str:
    """Generates a new secure session token and inserts it into DB."""
    token = secrets.token_hex(32)
    from datetime import timedelta
    expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sessions (token, user_id, expires_at)
            VALUES (?, ?, ?)
        """, (token, user_id, expires_at))
        conn.commit()
    return token

def get_user_by_session(token: str) -> dict:
    """Retrieves the user associated with a valid session token."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.*, s.expires_at FROM users u
            JOIN sessions s ON u.id = s.user_id
            WHERE s.token = ?
        """, (token,))
        row = cursor.fetchone()
        if row:
            session = dict(row)
            expires_at = datetime.fromisoformat(session["expires_at"])
            if expires_at > datetime.now():
                return session
            else:
                cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
    return None

def delete_session(token: str):
    """Deletes a session token."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()

def create_audit_log(user_id: int, action: str, details: str = None, ip_address: str = None):
    """Inserts a new audit log entry."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_logs (timestamp, user_id, action, details, ip_address)
            VALUES (?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), user_id, action, details, ip_address))
        conn.commit()

def get_audit_logs() -> list:
    """Fetches the 50 most recent audit logs with usernames."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, u.username FROM audit_logs a
            JOIN users u ON a.user_id = u.id
            ORDER BY a.timestamp DESC LIMIT 50
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_db_stats() -> dict:
    """Aggregates DB stats for the admin dashboard."""
    stats = {}
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM scans")
        stats["total_scans"] = cursor.fetchone()["count"]
        
        cursor.execute("SELECT status, COUNT(*) as count FROM scans GROUP BY status")
        rows = cursor.fetchall()
        status_counts = {"completed": 0, "pending": 0, "running": 0, "failed": 0}
        for r in rows:
            status_counts[r["status"]] = r["count"]
        stats["status_counts"] = status_counts
        
        cursor.execute("""
            SELECT SUM(critical_count) as crit, SUM(high_count) as high,
                   SUM(medium_count) as med, SUM(low_count) as low,
                   SUM(total_issues) as total
            FROM scans
        """)
        row = cursor.fetchone()
        stats["issue_sums"] = {
            "critical": row["crit"] if row and row["crit"] else 0,
            "high": row["high"] if row and row["high"] else 0,
            "medium": row["med"] if row and row["med"] else 0,
            "low": row["low"] if row and row["low"] else 0,
            "total": row["total"] if row and row["total"] else 0
        }
        
        try:
            stats["db_size_kb"] = round(os.path.getsize(DB_PATH) / 1024, 1)
        except Exception:
            stats["db_size_kb"] = 0.0
            
    return stats

def wipe_all_data():
    """Wipes all scans, issues, sessions, and audit logs (keeps users), and clears temp directories."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM issues")
        cursor.execute("DELETE FROM scans")
        cursor.execute("DELETE FROM sessions")
        cursor.execute("DELETE FROM audit_logs")
        conn.commit()
        
    try:
        import shutil
        temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "temp")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)
    except Exception as e:
        print(f"Error cleaning up temp directory on wipe: {e}")

# --- GitHub Users, Installations & Tenancy Database Helpers ---

def get_user_by_github_id(github_id: int) -> Optional[dict]:
    """Retrieves a user by their unique GitHub account ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE github_id = ?", (github_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id: int) -> Optional[dict]:
    """Retrieves a user by their local primary key ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def upsert_github_user(
    github_id: int,
    github_login: str,
    avatar_url: str = None,
    encrypted_user_token: str = None
) -> dict:
    """
    Creates or updates a user record upon GitHub OAuth authentication.
    Returns the updated or created user record.
    """
    existing = get_user_by_github_id(github_id)
    timestamp = datetime.now().isoformat()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if existing:
            cursor.execute("""
                UPDATE users
                SET github_login = ?, avatar_url = ?, encrypted_user_token = ?
                WHERE id = ?
            """, (github_login, avatar_url, encrypted_user_token, existing["id"]))
            user_id = existing["id"]
        else:
            # Check if username exists (e.g. admin or existing name collision)
            cursor.execute("SELECT id FROM users WHERE username = ?", (github_login,))
            username = github_login
            if cursor.fetchone():
                username = f"{github_login}_{github_id}"
                
            cursor.execute("""
                INSERT INTO users (username, hashed_password, role, created_at, github_id, github_login, avatar_url, encrypted_user_token)
                VALUES (?, '', 'user', ?, ?, ?, ?, ?)
            """, (username, timestamp, github_id, github_login, avatar_url, encrypted_user_token))
            cursor.execute("SELECT id FROM users WHERE github_id = ?", (github_id,))
            user_id = cursor.fetchone()["id"]
            
        conn.commit()

    return get_user_by_id(user_id)

def update_user_token(user_id: int, encrypted_token: str):
    """Updates the encrypted OAuth token for a user."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET encrypted_user_token = ? WHERE id = ?", (encrypted_token, user_id))
        conn.commit()

# --- Installations & Memberships ---

def upsert_installation(
    github_installation_id: int,
    account_login: str,
    account_type: str,
    account_avatar_url: str = None
) -> dict:
    """Creates or updates a GitHub App installation record."""
    timestamp = datetime.now().isoformat()
    existing = get_installation_by_github_id(github_installation_id)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if existing:
            cursor.execute("""
                UPDATE installations
                SET account_login = ?, account_type = ?, account_avatar_url = ?, deleted_at = NULL
                WHERE github_installation_id = ?
            """, (account_login, account_type, account_avatar_url, github_installation_id))
            inst_id = existing["id"]
        else:
            import uuid
            inst_id = uuid.uuid4().hex
            cursor.execute("""
                INSERT INTO installations (
                    id, github_installation_id, account_login, account_type, account_avatar_url, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (inst_id, github_installation_id, account_login, account_type, account_avatar_url, timestamp))
        conn.commit()

    return get_installation(inst_id)

def get_installation(installation_id: str) -> Optional[dict]:
    """Retrieves an installation record by local UUID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM installations WHERE id = ?", (installation_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_installation_by_github_id(github_installation_id: int) -> Optional[dict]:
    """Retrieves an installation record by GitHub installation ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM installations WHERE github_installation_id = ?", (github_installation_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def set_installation_suspension(github_installation_id: int, suspended: bool):
    """Updates suspended_at status on an installation."""
    val = datetime.now().isoformat() if suspended else None
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE installations SET suspended_at = ? WHERE github_installation_id = ?", (val, github_installation_id))
        conn.commit()

def soft_delete_installation(github_installation_id: int):
    """Soft-deletes an installation and its associated repositories upon uninstallation."""
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE installations SET deleted_at = ? WHERE github_installation_id = ?", (now, github_installation_id))
        inst = get_installation_by_github_id(github_installation_id)
        if inst:
            cursor.execute("UPDATE repositories SET deleted_at = ? WHERE installation_id = ?", (now, inst["id"]))
        conn.commit()

def add_installation_member(installation_id: str, user_id: int, role: str = 'member'):
    """Adds a user as an authorized member of an installation."""
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO installation_members (installation_id, user_id, role, created_at)
            VALUES (?, ?, ?, ?)
        """, (installation_id, user_id, role, now))
        conn.commit()

def is_user_installation_member(installation_id: str, user_id: int) -> bool:
    """Checks whether a user is an authorized member of an installation."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM installation_members 
            WHERE installation_id = ? AND user_id = ?
        """, (installation_id, user_id))
        return cursor.fetchone() is not None

def get_user_installations(user_id: int) -> list:
    """Retrieves all non-deleted installations accessible by the specified user."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.* FROM installations i
            JOIN installation_members im ON i.id = im.installation_id
            WHERE im.user_id = ? AND i.deleted_at IS NULL
            ORDER BY i.account_login ASC
        """, (user_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

# --- Repositories ---

def upsert_repository(
    installation_id: str,
    github_repo_id: int,
    full_name: str,
    default_branch: str = "main",
    is_private: bool = False
) -> dict:
    """Creates or updates an installed repository."""
    now = datetime.now().isoformat()
    existing = get_repository_by_github_id(github_repo_id)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        if existing:
            cursor.execute("""
                UPDATE repositories
                SET installation_id = ?, full_name = ?, default_branch = ?, is_private = ?, deleted_at = NULL
                WHERE github_repo_id = ?
            """, (installation_id, full_name, default_branch, int(is_private), github_repo_id))
            repo_id = existing["id"]
        else:
            import uuid
            repo_id = uuid.uuid4().hex
            cursor.execute("""
                INSERT INTO repositories (
                    id, installation_id, github_repo_id, full_name, default_branch, is_private, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (repo_id, installation_id, github_repo_id, full_name, default_branch, int(is_private), now))
        conn.commit()

    return get_repository(repo_id)

def get_repository(repo_id: str) -> Optional[dict]:
    """Retrieves an active repository by local UUID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM repositories WHERE id = ? AND deleted_at IS NULL", (repo_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_repository_by_github_id(github_repo_id: int) -> Optional[dict]:
    """Retrieves a repository by GitHub repository ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM repositories WHERE github_repo_id = ?", (github_repo_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_user_repositories(user_id: int, search: Optional[str] = None) -> list:
    """
    Retrieves all active repositories belonging to installations the user is a member of.
    Attaches latest scan summary metadata.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT r.*, i.account_login, i.account_type, i.suspended_at as installation_suspended_at
            FROM repositories r
            JOIN installations i ON r.installation_id = i.id
            JOIN installation_members im ON i.id = im.installation_id
            WHERE im.user_id = ? AND r.deleted_at IS NULL AND i.deleted_at IS NULL
        """
        params = [user_id]
        if search and search.strip():
            query += " AND r.full_name LIKE ?"
            params.append(f"%{search.strip()}%")

        query += " ORDER BY r.full_name ASC"
        cursor.execute(query, tuple(params))
        repos = [dict(row) for row in cursor.fetchall()]

        # Attach latest scan info for each repo
        for repo in repos:
            cursor.execute("""
                SELECT id, status, progress, total_issues, critical_count, high_count, medium_count, low_count, timestamp
                FROM scans
                WHERE repo_id = ?
                ORDER BY timestamp DESC LIMIT 1
            """, (repo["id"],))
            latest_scan = cursor.fetchone()
            repo["latest_scan"] = dict(latest_scan) if latest_scan else None

        return repos

def is_user_repo_member(repo_id: str, user_id: int) -> bool:
    """Verifies that a user has authorized membership access to a repository."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM repositories r
            JOIN installation_members im ON r.installation_id = im.installation_id
            WHERE r.id = ? AND im.user_id = ? AND r.deleted_at IS NULL
        """, (repo_id, user_id))
        return cursor.fetchone() is not None

def update_repo_last_scanned(repo_id: str):
    """Sets last_scanned_at to current timestamp."""
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE repositories SET last_scanned_at = ? WHERE id = ?", (now, repo_id))
        conn.commit()

def soft_delete_repository(github_repo_id: int):
    """Soft-deletes a single repository upon removal from an installation."""
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE repositories SET deleted_at = ?, scan_enabled = 0 WHERE github_repo_id = ?", (now, github_repo_id))
        conn.commit()

# --- Data Lifecycle & Retention ---

def purge_deleted_installations(retention_days: int = 30) -> int:
    """Permanently purges installations and associated repos/scans soft-deleted beyond retention threshold."""
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Find installations deleted before cutoff
        cursor.execute("SELECT id FROM installations WHERE deleted_at IS NOT NULL AND deleted_at < ?", (cutoff,))
        expired_ids = [row["id"] for row in cursor.fetchall()]
        
        purged = 0
        for inst_id in expired_ids:
            # Delete scans linked to repos in this installation
            cursor.execute("""
                DELETE FROM issues WHERE scan_id IN (
                    SELECT s.id FROM scans s
                    JOIN repositories r ON s.repo_id = r.id
                    WHERE r.installation_id = ?
                )
            """, (inst_id,))
            cursor.execute("""
                DELETE FROM scans WHERE repo_id IN (
                    SELECT id FROM repositories WHERE installation_id = ?
                )
            """, (inst_id,))
            cursor.execute("DELETE FROM repositories WHERE installation_id = ?", (inst_id,))
            cursor.execute("DELETE FROM installation_members WHERE installation_id = ?", (inst_id,))
            cursor.execute("DELETE FROM installations WHERE id = ?", (inst_id,))
            purged += 1
            
        conn.commit()
        return purged

def delete_user_data(user_id: int) -> dict:
    """Permanently deletes a user's personal scans, memberships, sessions, and clears encrypted OAuth tokens."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Delete issues for scans owned by this user
        cursor.execute("""
            DELETE FROM issues WHERE scan_id IN (
                SELECT id FROM scans WHERE owner_user_id = ?
            )
        """, (user_id,))
        # Delete user-owned scans
        cursor.execute("DELETE FROM scans WHERE owner_user_id = ?", (user_id,))
        # Remove installation memberships
        cursor.execute("DELETE FROM installation_members WHERE user_id = ?", (user_id,))
        # Clear sessions
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        # Redact token from user row
        cursor.execute("UPDATE users SET encrypted_user_token = NULL WHERE id = ?", (user_id,))
        conn.commit()
    return {"status": "success", "message": "User personal data successfully purged."}

# ==========================================
# Webhook Deliveries Helpers
# ==========================================

def record_webhook_delivery(
    delivery_id: str,
    event: str,
    action: Optional[str] = None,
    repository_id: Optional[str] = None,
    status: str = "received",
    error_message: Optional[str] = None
) -> None:
    """Logs an incoming GitHub webhook delivery for auditability, replay detection, and reliability reconcile."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        if bool(os.environ.get("DATABASE_URL")):
            cursor.execute("""
                INSERT INTO webhook_deliveries (id, event, action, repository_id, status, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING
            """, (delivery_id, event, action, repository_id, status, error_message, now))
        else:
            cursor.execute("""
                INSERT OR IGNORE INTO webhook_deliveries (id, event, action, repository_id, status, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (delivery_id, event, action, repository_id, status, error_message, now))
        conn.commit()

def update_webhook_delivery_status(delivery_id: str, status: str, error_message: Optional[str] = None) -> None:
    """Updates the processing status of a webhook delivery."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE webhook_deliveries SET status = ?, error_message = ? WHERE id = ?
        """, (status, error_message, delivery_id))
        conn.commit()

def get_failed_webhook_deliveries(limit: int = 50) -> List[dict]:
    """Retrieves recent failed webhook deliveries for automated reconciliation."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, event, action, repository_id, status, error_message, created_at
            FROM webhook_deliveries
            WHERE status = 'failed'
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(r) for r in cursor.fetchall()]

# ==========================================
# Findings Lifecycle & Baseline Tracking
# ==========================================

def get_repository_baseline_findings(repo_id: str) -> Dict[str, dict]:
    """Returns a mapping of fingerprint -> finding dictionary for all active (non-fixed) findings in a repo."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, repo_id, fingerprint, rule_id, severity, title, filepath, line_number,
                   first_seen_commit, first_seen_at, last_seen_at, introduced_by_pr, state,
                   suppressed_by, suppressed_at, reason
            FROM findings
            WHERE repo_id = ? AND state != 'fixed'
        """, (repo_id,))
        return {r["fingerprint"]: dict(r) for r in cursor.fetchall()}

def upsert_baseline_findings(repo_id: str, scan_id: str, commit_sha: str, issues: List[dict]) -> None:
    """
    Synchronizes the repository baseline against a default-branch scan:
    1. Upserts findings by fingerprint.
    2. Marks findings that no longer appear as 'fixed'.
    3. Re-opens findings if they reappear after being marked 'fixed'.
    4. Links each scan issue to its persistent finding_id.
    5. Sets repositories.baseline_scan_id.
    """
    now = datetime.now().isoformat()
    current_fps = set()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Fetch existing findings for repo
        cursor.execute("SELECT id, fingerprint, state FROM findings WHERE repo_id = ?", (repo_id,))
        existing_findings = {r["fingerprint"]: dict(r) for r in cursor.fetchall()}

        for issue in issues:
            fp = issue.get("fingerprint")
            if not fp:
                continue
            current_fps.add(fp)

            is_secret = 1 if (issue.get("is_secret") or issue.get("scanner") == "secret") else 0
            still_head = 1 if issue.get("still_in_head", True) else 0

            if fp in existing_findings:
                existing = existing_findings[fp]
                finding_id = existing["id"]
                # If was fixed, re-open unless suppressed
                new_state = "open" if existing["state"] == "fixed" else existing["state"]
                # Update still_in_head and adjust severity if secret
                if is_secret:
                    new_sev = "critical" if still_head else "high"
                    cursor.execute("""
                        UPDATE findings 
                        SET last_seen_at = ?, state = ?, still_in_head = ?, severity = ?
                        WHERE id = ?
                    """, (now, new_state, still_head, new_sev, finding_id))
                else:
                    cursor.execute("""
                        UPDATE findings SET last_seen_at = ?, state = ? WHERE id = ?
                    """, (now, new_state, finding_id))
            else:
                finding_id = secrets.token_hex(16)
                title = issue.get("fix_title") or issue.get("rule_id", "Security Issue")
                cursor.execute("""
                    INSERT INTO findings (
                        id, repo_id, fingerprint, rule_id, severity, title, filepath,
                        line_number, first_seen_commit, first_seen_at, last_seen_at, state,
                        masked_secret, secret_hash, detector, commit_sha, commit_date,
                        still_in_head, is_secret
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?)
                """, (
                    finding_id, repo_id, fp, issue.get("rule_id", ""),
                    issue.get("severity", "medium"), title, issue.get("filepath", ""),
                    issue.get("line_number", 0), commit_sha, now, now,
                    issue.get("masked_secret"), issue.get("secret_hash"),
                    issue.get("detector"), issue.get("commit_sha") or commit_sha,
                    issue.get("commit_date"), still_head, is_secret
                ))

            # Link issue row
            if "id" in issue:
                cursor.execute("""
                    UPDATE issues SET finding_id = ?, is_new = 0 WHERE id = ?
                """, (finding_id, issue["id"]))

        # Mark findings that disappeared from baseline as 'fixed'
        for fp, existing in existing_findings.items():
            if fp not in current_fps and existing["state"] == "open":
                cursor.execute("UPDATE findings SET state = 'fixed', last_seen_at = ? WHERE id = ?", (now, existing["id"]))

        # Update repository baseline_scan_id
        cursor.execute("UPDATE repositories SET baseline_scan_id = ? WHERE id = ?", (scan_id, repo_id))
        conn.commit()

def get_repository_findings(
    repo_id: str,
    severity: Optional[str] = None,
    state: Optional[str] = None,
    scanner: Optional[str] = None,
    is_secret: Optional[bool] = None,
    introduced_by_pr: Optional[int] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 20
) -> Tuple[List[dict], int]:
    """Retrieves paginated findings for a repository with flexible filtering."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT f.* FROM findings f WHERE f.repo_id = ?"
        params: List[any] = [repo_id]

        if severity and severity != "all":
            query += " AND f.severity = ?"
            params.append(severity)
        if state and state != "all":
            query += " AND f.state = ?"
            params.append(state)
        if is_secret is True or (scanner and scanner.lower() == "secret"):
            query += " AND (f.is_secret = 1 OR f.detector IS NOT NULL OR f.rule_id LIKE 'SECRET_%')"
        elif scanner and scanner != "all":
            query += " AND f.id IN (SELECT finding_id FROM issues WHERE scanner = ? AND finding_id IS NOT NULL)"
            params.append(scanner)
        if introduced_by_pr is not None:
            query += " AND f.introduced_by_pr = ?"
            params.append(introduced_by_pr)
        if search:
            query += " AND (f.title LIKE ? OR f.filepath LIKE ? OR f.rule_id LIKE ? OR f.masked_secret LIKE ?)"
            s_param = f"%{search}%"
            params.extend([s_param, s_param, s_param, s_param])

        count_query = f"SELECT COUNT(*) as cnt FROM ({query}) as filtered"
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()["cnt"]

        query += " ORDER BY CASE f.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, f.last_seen_at DESC"
        query += " LIMIT ? OFFSET ?"
        params.extend([per_page, (page - 1) * per_page])

        cursor.execute(query, params)
        findings = [dict(r) for r in cursor.fetchall()]

        # Attach sample remediation / snippet for each finding from its latest issue
        from app.utils.fix_suggestions import get_fix_suggestion
        for f in findings:
            cursor.execute("""
                SELECT code_snippet, scanner, message
                FROM issues
                WHERE finding_id = ?
                ORDER BY id DESC LIMIT 1
            """, (f["id"],))
            iss = cursor.fetchone()
            if iss:
                iss_dict = dict(iss)
                f.update(iss_dict)
                fix = get_fix_suggestion(f.get("rule_id", ""), iss_dict.get("message", ""))
                f.update({
                    "fix_title": fix["title"],
                    "fix_description": fix["description"],
                    "fix_before": fix["before"],
                    "fix_after": fix["after"],
                    "doc_url": fix["doc_url"]
                })
            if f.get("is_secret") or f.get("detector") or (f.get("rule_id") and str(f.get("rule_id")).startswith("SECRET_")):
                f["is_secret"] = True
                f["still_in_head"] = bool(f.get("still_in_head", 1))

        return findings, total_count

def get_finding_by_id(repo_id: str, finding_id: str) -> Optional[dict]:
    """Retrieves a single finding with rich remediation metadata."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT f.*, u.username as suppressed_by_username
            FROM findings f
            LEFT JOIN users u ON f.suppressed_by = u.id
            WHERE f.repo_id = ? AND f.id = ?
        """, (repo_id, finding_id))
        row = cursor.fetchone()
        if not row:
            return None
        finding = dict(row)

        cursor.execute("""
            SELECT code_snippet, scanner, message
            FROM issues
            WHERE finding_id = ?
            ORDER BY id DESC LIMIT 1
        """, (finding_id,))
        iss = cursor.fetchone()
        if iss:
            iss_dict = dict(iss)
            finding.update(iss_dict)
            from app.utils.fix_suggestions import get_fix_suggestion
            fix = get_fix_suggestion(finding.get("rule_id", ""), iss_dict.get("message", ""))
            finding.update({
                "fix_title": fix["title"],
                "fix_description": fix["description"],
                "fix_before": fix["before"],
                "fix_after": fix["after"],
                "doc_url": fix["doc_url"]
            })
        if finding.get("is_secret") or finding.get("detector") or (finding.get("rule_id") and str(finding.get("rule_id")).startswith("SECRET_")):
            finding["is_secret"] = True
            finding["still_in_head"] = bool(finding.get("still_in_head", 1))
        return finding

def suppress_finding(repo_id: str, finding_id: str, user_id: int, state: str = "suppressed", reason: str = "") -> dict:
    """Marks a finding as suppressed or false_positive and records an audit log entry."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            UPDATE findings
            SET state = ?, suppressed_by = ?, suppressed_at = ?, reason = ?
            WHERE id = ? AND repo_id = ?
        """, (state, user_id, now, reason, finding_id, repo_id))

        # Record audit log
        cursor.execute("""
            INSERT INTO audit_logs (timestamp, user_id, action, details)
            VALUES (?, ?, 'finding_suppress', ?)
        """, (now, user_id, f"Suppressed finding {finding_id} as {state}: {reason}"))
        conn.commit()
    return {"status": "success", "finding_id": finding_id, "state": state}

def unsuppress_finding(repo_id: str, finding_id: str, user_id: int) -> dict:
    """Restores a suppressed finding back to open status."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            UPDATE findings
            SET state = 'open', suppressed_by = NULL, suppressed_at = NULL, reason = NULL
            WHERE id = ? AND repo_id = ?
        """, (finding_id, repo_id))

        cursor.execute("""
            INSERT INTO audit_logs (timestamp, user_id, action, details)
            VALUES (?, ?, 'finding_unsuppress', ?)
        """, (now, user_id, f"Restored finding {finding_id} to open status"))
        conn.commit()
    return {"status": "success", "finding_id": finding_id, "state": "open"}

# ==========================================
# Pull Request Scans & Metrics Helpers
# ==========================================

def update_scan_pr_metrics(
    scan_id: str,
    verdict: str,
    new_count: int,
    fixed_count: int,
    existing_count: int,
    check_run_id: Optional[int] = None
) -> None:
    """Updates PR comparison metrics and conclusion verdict on a scan record."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE scans
            SET verdict = ?, new_findings_count = ?, fixed_findings_count = ?,
                existing_findings_count = ?, check_run_id = COALESCE(?, check_run_id)
            WHERE id = ?
        """, (verdict, new_count, fixed_count, existing_count, check_run_id, scan_id))
        conn.commit()

def get_repository_pull_requests(repo_id: str) -> List[dict]:
    """Returns the most recent scan per pull request for a repository."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Find distinct PR numbers for repo
        cursor.execute("""
            SELECT pr_number, MAX(timestamp) as latest_ts
            FROM scans
            WHERE repo_id = ? AND pr_number IS NOT NULL
            GROUP BY pr_number
            ORDER BY latest_ts DESC
        """, (repo_id,))
        prs = cursor.fetchall()

        results = []
        for pr_row in prs:
            pr_num = pr_row["pr_number"]
            cursor.execute("""
                SELECT id, repo_id, branch, commit_sha, status, verdict,
                       new_findings_count, fixed_findings_count, existing_findings_count,
                       timestamp, filename
                FROM scans
                WHERE repo_id = ? AND pr_number = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (repo_id, pr_num))
            latest_scan = cursor.fetchone()
            if latest_scan:
                results.append({
                    "pr_number": pr_num,
                    "title": latest_scan["filename"] or f"Pull Request #{pr_num}",
                    "branch": latest_scan["branch"],
                    "commit_sha": latest_scan["commit_sha"],
                    "status": latest_scan["status"],
                    "verdict": latest_scan["verdict"] or "SAFE",
                    "new_findings_count": latest_scan["new_findings_count"] or 0,
                    "fixed_findings_count": latest_scan["fixed_findings_count"] or 0,
                    "existing_findings_count": latest_scan["existing_findings_count"] or 0,
                    "timestamp": latest_scan["timestamp"],
                    "latest_scan_id": latest_scan["id"]
                })
        return results

def get_pull_request_scans(repo_id: str, pr_number: int) -> List[dict]:
    """Retrieves all historical scans for a specific pull request (push-by-push timeline)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, branch, commit_sha, status, verdict, progress,
                   new_findings_count, fixed_findings_count, existing_findings_count,
                   duration_ms, files_scanned, files_skipped, timestamp
            FROM scans
            WHERE repo_id = ? AND pr_number = ?
            ORDER BY timestamp DESC
        """, (repo_id, pr_number))
        return [dict(r) for r in cursor.fetchall()]

def get_repository_score_trend(repo_id: str, limit: int = 20) -> List[dict]:
    """
    Computes security score per default-branch commit:
    Score = max(0, 100 - (critical * 15 + high * 8 + medium * 3 + low * 1))
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, commit_sha, branch, timestamp,
                   critical_count, high_count, medium_count, low_count, total_issues
            FROM scans
            WHERE repo_id = ? AND (trigger = 'push' OR trigger = 'manual') AND status = 'completed'
            ORDER BY timestamp ASC
            LIMIT ?
        """, (repo_id, limit))
        rows = cursor.fetchall()
        trend = []
        for r in rows:
            crit = r["critical_count"] or 0
            high = r["high_count"] or 0
            med = r["medium_count"] or 0
            low = r["low_count"] or 0
            score = max(0, 100 - (crit * 15 + high * 8 + med * 3 + low * 1))
            trend.append({
                "scan_id": r["id"],
                "commit_sha": r["commit_sha"],
                "timestamp": r["timestamp"],
                "score": score,
                "critical": crit,
                "high": high,
                "medium": med,
                "low": low,
                "total": r["total_issues"] or 0
            })
        return trend

# ==========================================
# Pull Request Summaries Storage & Retrieval
# ==========================================

def save_pr_summary(
    repo_id: str,
    pr_number: int,
    scan_id: str,
    head_sha: str,
    facts: dict,
    narrative: Optional[str] = None,
    narrative_source: str = "template",
    model: Optional[str] = None,
    summary_version: int = 1
) -> dict:
    """
    Saves or updates a pull request summary record.
    Idempotent on (repo_id, pr_number, head_sha).
    """
    summary_id = secrets.token_hex(16)
    now = datetime.now().isoformat()
    facts_json = json.dumps(facts) if isinstance(facts, dict) else str(facts)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        if bool(os.environ.get("DATABASE_URL")):
            cursor.execute("""
                INSERT INTO pr_summaries (
                    id, repo_id, pr_number, scan_id, head_sha, facts,
                    narrative, narrative_source, model, summary_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (repo_id, pr_number, head_sha) DO UPDATE SET
                    scan_id = EXCLUDED.scan_id,
                    facts = EXCLUDED.facts,
                    narrative = EXCLUDED.narrative,
                    narrative_source = EXCLUDED.narrative_source,
                    model = EXCLUDED.model,
                    summary_version = EXCLUDED.summary_version,
                    created_at = EXCLUDED.created_at
            """, (
                summary_id, repo_id, pr_number, scan_id, head_sha, facts_json,
                narrative, narrative_source, model, summary_version, now
            ))
        else:
            cursor.execute("""
                INSERT INTO pr_summaries (
                    id, repo_id, pr_number, scan_id, head_sha, facts,
                    narrative, narrative_source, model, summary_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (repo_id, pr_number, head_sha) DO UPDATE SET
                    scan_id = excluded.scan_id,
                    facts = excluded.facts,
                    narrative = excluded.narrative,
                    narrative_source = excluded.narrative_source,
                    model = excluded.model,
                    summary_version = excluded.summary_version,
                    created_at = excluded.created_at
            """, (
                summary_id, repo_id, pr_number, scan_id, head_sha, facts_json,
                narrative, narrative_source, model, summary_version, now
            ))
        conn.commit()

    return {
        "id": summary_id,
        "repo_id": repo_id,
        "pr_number": pr_number,
        "scan_id": scan_id,
        "head_sha": head_sha,
        "facts": facts if isinstance(facts, dict) else json.loads(facts_json),
        "narrative": narrative,
        "narrative_source": narrative_source,
        "model": model,
        "summary_version": summary_version,
        "created_at": now
    }

def get_latest_pr_summary(repo_id: str, pr_number: int) -> Optional[dict]:
    """Retrieves the latest summary for a specific pull request."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM pr_summaries
            WHERE repo_id = ? AND pr_number = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (repo_id, pr_number))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        if isinstance(res.get("facts"), str):
            try:
                res["facts"] = json.loads(res["facts"])
            except Exception:
                pass
        return res

def get_pr_summaries_history(repo_id: str, pr_number: int, limit: int = 50) -> List[dict]:
    """Retrieves all historical summary records for a specific pull request."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM pr_summaries
            WHERE repo_id = ? AND pr_number = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (repo_id, pr_number, limit))
        rows = cursor.fetchall()
        summaries = []
        for r in rows:
            item = dict(r)
            if isinstance(item.get("facts"), str):
                try:
                    item["facts"] = json.loads(item["facts"])
                except Exception:
                    pass
            summaries.append(item)
        return summaries

# --- Auto-Fix and Verified Patch Persistence ---

def save_fix_attempt(
    attempt_id: str,
    finding_id: str,
    repo_id: str,
    status: str,
    provider: str,
    model: str,
    target_file: str,
    target_function: Optional[str] = None,
    start_line: int = 1,
    end_line: int = 1,
    diff: Optional[str] = None,
    patch_code: Optional[str] = None,
    explanation: Optional[str] = None,
    verification_json: Optional[Any] = None,
    rejection_reason: Optional[str] = None,
    pr_number: Optional[int] = None,
    pr_url: Optional[str] = None,
    branch_name: Optional[str] = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0
) -> dict:
    """Saves or updates an auto-fix attempt record."""
    now = datetime.now().isoformat()
    v_json = json.dumps(verification_json) if isinstance(verification_json, (dict, list)) else verification_json

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO fix_attempts (
                id, finding_id, repo_id, status, provider, model, tokens_in, tokens_out, cost_usd,
                target_file, target_function, start_line, end_line, diff, patch_code, explanation,
                verification_json, rejection_reason, pr_number, pr_url, branch_name, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                status = excluded.status,
                diff = excluded.diff,
                patch_code = excluded.patch_code,
                explanation = excluded.explanation,
                verification_json = excluded.verification_json,
                rejection_reason = excluded.rejection_reason,
                pr_number = excluded.pr_number,
                pr_url = excluded.pr_url,
                branch_name = excluded.branch_name,
                tokens_in = excluded.tokens_in,
                tokens_out = excluded.tokens_out,
                cost_usd = excluded.cost_usd,
                updated_at = excluded.updated_at
        """, (
            attempt_id, finding_id, repo_id, status, provider, model, tokens_in, tokens_out, cost_usd,
            target_file, target_function, start_line, end_line, diff, patch_code, explanation,
            v_json, rejection_reason, pr_number, pr_url, branch_name, now, now
        ))
        conn.commit()

    return {
        "id": attempt_id,
        "finding_id": finding_id,
        "repo_id": repo_id,
        "status": status,
        "provider": provider,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "target_file": target_file,
        "target_function": target_function,
        "start_line": start_line,
        "end_line": end_line,
        "diff": diff,
        "patch_code": patch_code,
        "explanation": explanation,
        "verification_json": verification_json,
        "rejection_reason": rejection_reason,
        "pr_number": pr_number,
        "pr_url": pr_url,
        "branch_name": branch_name,
        "created_at": now,
        "updated_at": now
    }

def get_fix_attempt(attempt_id: str) -> Optional[dict]:
    """Retrieves a single fix attempt by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fix_attempts WHERE id = ?", (attempt_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        if isinstance(res.get("verification_json"), str):
            try:
                res["verification_json"] = json.loads(res["verification_json"])
            except Exception:
                pass
        return res

def get_latest_fix_attempt_for_finding(finding_id: str, repo_id: Optional[str] = None) -> Optional[dict]:
    """Retrieves the most recent fix attempt for a finding (optionally scoped to a repository)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if repo_id:
            cursor.execute("""
                SELECT * FROM fix_attempts
                WHERE repo_id = ? AND finding_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (repo_id, finding_id))
        else:
            cursor.execute("""
                SELECT * FROM fix_attempts
                WHERE finding_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (finding_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        if isinstance(res.get("verification_json"), str):
            try:
                res["verification_json"] = json.loads(res["verification_json"])
            except Exception:
                pass
        return res

def update_fix_attempt_status(attempt_id: str, status: str, **kwargs):
    """Updates status and additional fields for a fix attempt."""
    now = datetime.now().isoformat()
    updates = ["status = ?", "updated_at = ?"]
    params = [status, now]

    for key, val in kwargs.items():
        if key == "verification_json" and isinstance(val, (dict, list)):
            val = json.dumps(val)
        updates.append(f"{key} = ?")
        params.append(val)

    params.append(attempt_id)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE fix_attempts SET {', '.join(updates)} WHERE id = ?", tuple(params))
        conn.commit()

def get_repo_daily_fix_count(repo_id: str, date_prefix: Optional[str] = None) -> int:
    """Returns the total number of fix attempts initiated today for quota enforcement."""
    prefix = date_prefix or datetime.now().strftime("%Y-%m-%d")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM fix_attempts
            WHERE repo_id = ? AND created_at LIKE ?
        """, (repo_id, f"{prefix}%"))
        row = cursor.fetchone()
        return row[0] if row else 0



