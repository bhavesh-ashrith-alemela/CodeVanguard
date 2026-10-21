"""
Demo Repository Generator for CodeVanguard.

Creates a local synthetic Git repository containing:
1. Commit 1: Planted vulnerabilities (SQL Injection B608, Command Injection B602, Leaked AWS Key).
2. Commit 2: Deletes the AWS Key, creating a historical secret (deleted from HEAD).
3. Branch 'feature/vulnerable-pr': Introduces a path traversal defect and dependency updates.
"""
import os
import shutil
import subprocess
import argparse

def create_demo_repository(output_dir: str = "demo_repo") -> str:
    target_path = os.path.abspath(output_dir)
    if os.path.exists(target_path):
        shutil.rmtree(target_path)
    os.makedirs(target_path, exist_ok=True)

    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
        "GIT_AUTHOR_NAME": "Demo Developer",
        "GIT_AUTHOR_EMAIL": "developer@demo.codevanguard.dev",
        "GIT_COMMITTER_NAME": "Demo Developer",
        "GIT_COMMITTER_EMAIL": "developer@demo.codevanguard.dev",
        "GIT_TERMINAL_PROMPT": "0"
    }

    # 1. Initialize git repo on default branch 'main'
    subprocess.run(["git", "init", "-b", "main"], cwd=target_path, env=env, check=True, stdout=subprocess.PIPE)

    # 2. Commit 1: Initial vulnerable codebase
    os.makedirs(os.path.join(target_path, "src"), exist_ok=True)

    db_code = '''import sqlite3

def get_user_records(username: str):
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    # VULNERABLE: B608 SQL Injection via f-string query formatting
    cursor.execute(f"SELECT * FROM users WHERE username = '{username}'")
    return cursor.fetchall()
'''
    with open(os.path.join(target_path, "src", "db.py"), "w", encoding="utf-8") as f:
        f.write(db_code)

    exporter_code = '''import subprocess

def generate_report(output_filename: str):
    # VULNERABLE: B602 Command Injection via shell=True
    subprocess.run(f"cat /tmp/data > {output_filename}", shell=True)
'''
    with open(os.path.join(target_path, "src", "exporter.py"), "w", encoding="utf-8") as f:
        f.write(exporter_code)

    config_code = '''# Application Configurations
APP_NAME = "Vulnerable Microservice"
DEBUG = False

# VULNERABLE: Leaked AWS Access Key committed directly into source code
AWS_ACCESS_KEY_ID = "AKIA1234567890ABCDEF"
AWS_REGION = "us-east-1"
'''
    with open(os.path.join(target_path, "src", "config.py"), "w", encoding="utf-8") as f:
        f.write(config_code)

    reqs_code = '''fastapi==0.110.0
uvicorn==0.28.0
requests==2.31.0
'''
    with open(os.path.join(target_path, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write(reqs_code)

    subprocess.run(["git", "add", "."], cwd=target_path, env=env, check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "commit", "-m", "Initial commit with database, exporter, and AWS config"], cwd=target_path, env=env, check=True, stdout=subprocess.PIPE)

    # 3. Commit 2: Delete AWS secret from config.py (creating historical secret)
    clean_config = '''# Application Configurations
import os

APP_NAME = "Vulnerable Microservice"
DEBUG = False

# Resolved: Load AWS credentials from environment variable
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_REGION = "us-east-1"
'''
    with open(os.path.join(target_path, "src", "config.py"), "w", encoding="utf-8") as f:
        f.write(clean_config)

    subprocess.run(["git", "add", "src/config.py"], cwd=target_path, env=env, check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "commit", "-m", "Refactor config: load AWS credentials from environment"], cwd=target_path, env=env, check=True, stdout=subprocess.PIPE)

    # 4. Create branch 'feature/vulnerable-pr' with new vulnerabilities and dependency changes
    subprocess.run(["git", "checkout", "-b", "feature/vulnerable-pr"], cwd=target_path, env=env, check=True, stdout=subprocess.PIPE)

    os.makedirs(os.path.join(target_path, "src", "api"), exist_ok=True)
    api_code = '''import os

def read_user_file(file_path: str):
    # VULNERABLE: Path Traversal
    full_path = os.path.join("/tmp/user_uploads", file_path)
    with open(full_path, "r") as f:
        return f.read()
'''
    with open(os.path.join(target_path, "src", "api", "files.py"), "w", encoding="utf-8") as f:
        f.write(api_code)

    updated_reqs = reqs_code + "pydantic==2.6.4\npyyaml==6.0.1\n"
    with open(os.path.join(target_path, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write(updated_reqs)

    subprocess.run(["git", "add", "."], cwd=target_path, env=env, check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "commit", "-m", "Add file viewer endpoint and update dependencies"], cwd=target_path, env=env, check=True, stdout=subprocess.PIPE)

    # Switch back to main
    subprocess.run(["git", "checkout", "main"], cwd=target_path, env=env, check=True, stdout=subprocess.PIPE)

    print(f"[CodeVanguard Demo] Successfully created synthetic repository at: {target_path}")
    print("  - Branch main: 2 commits (includes deleted historical secret AKIA...EF)")
    print("  - Branch feature/vulnerable-pr: 1 commit (adds Path Traversal & 2 dependencies)")
    return target_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create CodeVanguard demo Git repository.")
    parser.add_argument("--output", "-o", default="demo_repo", help="Output directory path")
    args = parser.parse_args()
    create_demo_repository(args.output)
