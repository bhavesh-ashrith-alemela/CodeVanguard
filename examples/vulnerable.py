import sqlite3
import subprocess
import hashlib
import pickle
import random
import os

# 1. Hardcoded Secret (Bandit B105)
API_SECRET_KEY = "sk_live_vanguard_5f3e9a4d8c7b6a5"
DATABASE_PASSWORD = "super_secret_db_pass_123!"

# 2. Bind to all interfaces (Bandit B104)
def start_server():
    host = "0.0.0.0"
    port = 8080
    print(f"Starting developer server on {host}:{port}")

# 3. SQL Injection (Bandit B608)
def get_user_profile(user_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # Vulnerable to SQL injection via format string interpolation
    query = "SELECT * FROM profiles WHERE id = '%s'" % user_id
    cursor.execute(query)
    return cursor.fetchone()

# 4. Process Command Injection (Bandit B602)
def ping_address(ip_address):
    # Vulnerable to command injection since shell=True is set
    cmd = f"ping -c 1 {ip_address}"
    subprocess.call(cmd, shell=True)

# 5. Unsafe Deserialization (Bandit B301)
def load_session_cache(serialized_data):
    # Vulnerable to RCE if serialized_data is untrusted
    session = pickle.loads(serialized_data)
    return session

# 6. Insecure Cryptographic Hash (Bandit B303)
def generate_user_md5_hash(user_email):
    # MD5 is broken and cryptographically weak
    m = hashlib.md5()
    m.update(user_email.encode('utf-8'))
    return m.hexdigest()

# 7. Weak Pseudo-Random Number Generator (Bandit B311)
def generate_reset_token():
    # random module is not cryptographically secure
    token = random.randint(100000, 999999)
    return str(token)

# 8. Assert statements (Bandit B101)
def check_admin_privileges(user):
    # Assert can be compiled away (optimized out) in python bytecode
    assert user.get("role") == "admin", "User must be an admin to access"
    print("Access granted!")
