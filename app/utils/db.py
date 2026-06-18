import sqlite3
import json
import os
import hashlib
import secrets
from datetime import datetime

DB_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
DB_PATH = os.path.join(DB_DIR, "codevanguard.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema if it doesn't already exist."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Scans table
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
                low_count INTEGER DEFAULT 0
            )
        """)
        
        # Issues table
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
        
        # Index for issues foreign key
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_issues_scan_id ON issues (scan_id)")
        
        conn.commit()
        
        # Auto-create default admin account
        cursor.execute("SELECT COUNT(*) as count FROM users")
        if cursor.fetchone()["count"] == 0:
            default_admin_user = "admin"
            default_admin_pass = "VanguardAdmin2026!"
            hashed = hash_password(default_admin_pass)
            cursor.execute("""
                INSERT INTO users (username, hashed_password, role, created_at)
                VALUES (?, ?, 'admin', ?)
            """, (default_admin_user, hashed, datetime.now().isoformat()))
            conn.commit()
            print(f"CodeVanguard: Created default admin account (username: '{default_admin_user}', password: '{default_admin_pass}')")

def create_scan(scan_id: str, filename: str, file_size: int) -> dict:
    """Inserts a new scan with status 'pending'."""
    timestamp = datetime.now().isoformat()
    status = "pending"
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO scans (id, timestamp, filename, file_size, status)
            VALUES (?, ?, ?, ?, ?)
        """, (scan_id, timestamp, filename, file_size, status))
        conn.commit()
        
    return {
        "id": scan_id,
        "timestamp": timestamp,
        "filename": filename,
        "file_size": file_size,
        "status": status,
        "error_message": None,
        "total_issues": 0,
        "critical_count": 0,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 0
    }

def update_scan_status(scan_id: str, status: str, error_message: str = None):
    """Updates the status and optional error message of a scan."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE scans
            SET status = ?, error_message = ?
            WHERE id = ?
        """, (status, error_message, scan_id))
        conn.commit()

def save_scan_results(scan_id: str, issues: list):
    """
    Saves parsed issues to the database and updates scan statistics/status to 'completed'.
    Each issue in the list is expected to be a dictionary or object with:
    scanner, rule_id, severity, message, filepath, line_number, col_number, code_snippet
    """
    total_issues = len(issues)
    critical_count = 0
    high_count = 0
    medium_count = 0
    low_count = 0

    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Delete any existing issues for safety (if re-running, though scans have unique IDs)
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
                
            cursor.execute("""
                INSERT INTO issues (scan_id, scanner, rule_id, severity, message, filepath, line_number, col_number, code_snippet)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                scan_id,
                issue.get("scanner"),
                issue.get("rule_id"),
                severity,
                issue.get("message"),
                issue.get("filepath"),
                issue.get("line_number"),
                issue.get("col_number"),
                issue.get("code_snippet")
            ))
            
        cursor.execute("""
            UPDATE scans
            SET status = 'completed',
                total_issues = ?,
                critical_count = ?,
                high_count = ?,
                medium_count = ?,
                low_count = ?
            WHERE id = ?
        """, (total_issues, critical_count, high_count, medium_count, low_count, scan_id))
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

def get_scan_history() -> list:
    """Fetches scan records ordered by timestamp descending."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scans ORDER BY timestamp DESC")
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
    """Wipes all scans, issues, sessions, and audit logs (keeps users)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM issues")
        cursor.execute("DELETE FROM scans")
        cursor.execute("DELETE FROM sessions")
        cursor.execute("DELETE FROM audit_logs")
        conn.commit()
