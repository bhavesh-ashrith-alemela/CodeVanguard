import re

# Specific fix catalog
FIX_CATALOG = {
    # SQL Injection
    "B608": {
        "title": "SQL Injection vulnerability",
        "description": "Raw SQL queries constructed with string formatting or interpolation allow attackers to inject malicious SQL commands and bypass security controls.",
        "before": """# VULNERABLE: Direct string interpolation into query
query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
cursor.execute(query)""",
        "after": """# SECURED: Parameterized query (placeholders)
query = "SELECT * FROM users WHERE username = ? AND password = ?"
cursor.execute(query, (username, password))""",
        "doc_url": "https://owasp.org/www-community/attacks/SQL_Injection"
    },
    
    # Hardcoded Bind to 0.0.0.0
    "B104": {
        "title": "Bind to all interfaces (0.0.0.0)",
        "description": "Binding an application to 0.0.0.0 exposes it to all network interfaces, including public networks, increasing the attack surface.",
        "before": """# VULNERABLE: Binds to all network interfaces
app.run(host='0.0.0.0', port=8080)""",
        "after": """# SECURED: Bind to localhost (or private interfaces only)
app.run(host='127.0.0.1', port=8080)""",
        "doc_url": "https://cwe.mitre.org/data/definitions/200.html"
    },
    
    # Insecure Cryptographic Hash
    "B303": {
        "title": "Use of MD5 or SHA-1 (Insecure Hash)",
        "description": "MD5 and SHA-1 have known cryptographic weaknesses and are susceptible to collision attacks. Use SHA-256 or stronger algorithms for cryptographic operations.",
        "before": """# VULNERABLE: Insecure hash algorithm
import hashlib
hashed = hashlib.md5(password.encode()).hexdigest()""",
        "after": """# SECURED: Secure SHA-256 hash algorithm (or pbkdf2/bcrypt for passwords)
import hashlib
hashed = hashlib.sha256(password.encode()).hexdigest()""",
        "doc_url": "https://cwe.mitre.org/data/definitions/328.html"
    },
    
    # Insecure Deserialization (Pickle)
    "B301": {
        "title": "Use of unsafe deserialization (pickle)",
        "description": "Deserializing untrusted data with `pickle` can lead to arbitrary code execution. Use safer formats like JSON or Protocol Buffers.",
        "before": """# VULNERABLE: Loading untrusted pickle data
import pickle
data = pickle.loads(user_input)""",
        "after": """# SECURED: Use safe data serialization format like JSON
import json
data = json.loads(user_input)""",
        "doc_url": "https://owasp.org/www-community/vulnerabilities/Deserialization_of_untrusted_data"
    },
    
    # Insecure Deserialization (Marshal)
    "B302": {
        "title": "Use of unsafe deserialization (marshal)",
        "description": "Like pickle, `marshal` is intended for Python internal serialization and is not secure against crafted inputs. Avoid using it for user data.",
        "before": """# VULNERABLE: Loading marshal byte stream
import marshal
data = marshal.loads(raw_bytes)""",
        "after": """# SECURED: Use JSON, Protocol Buffers, or MessagePack
import json
data = json.loads(raw_bytes.decode('utf-8'))""",
        "doc_url": "https://cwe.mitre.org/data/definitions/502.html"
    },
    
    # Process Spawning / Command Injection
    "B602": {
        "title": "Subprocess execution with shell=True",
        "description": "Spawning subprocesses with `shell=True` enables command injection if the arguments are unchecked. Pass arguments as a list and disable shell execution.",
        "before": """# VULNERABLE: Execution using shell environment
import subprocess
subprocess.run(f"ls -l {directory}", shell=True)""",
        "after": """# SECURED: Arguments passed as list, shell=False (default)
import subprocess
subprocess.run(["ls", "-l", directory], shell=False)""",
        "doc_url": "https://owasp.org/www-community/attacks/Command_Injection"
    },
    "B603": {
        "title": "Subprocess execution without validation",
        "description": "Using subprocess with untrusted input can be dangerous if the binary name or parameters are controlled by the user. Sanitize inputs and restrict executing paths.",
        "before": """# VULNERABLE: Subprocess call with potential unsafe input
import subprocess
subprocess.call([binary_name, arg1, arg2])""",
        "after": """# SECURED: Strict validation / static whitelist of binaries
import subprocess
ALLOWED_BINARIES = {"/bin/ls", "/bin/df"}
if binary_name in ALLOWED_BINARIES:
    subprocess.call([binary_name, arg1, arg2])
else:
    raise ValueError("Forbidden binary execution")""",
        "doc_url": "https://cwe.mitre.org/data/definitions/78.html"
    },
    
    # Weak Pseudo-Random Number Generator
    "B311": {
        "title": "Weak pseudo-random generator (random)",
        "description": "The standard `random` module is not cryptographically secure. Use the `secrets` module for tokens, passwords, and security-sensitive identifiers.",
        "before": """# VULNERABLE: Using random for secure token generation
import random
token = str(random.randint(100000, 999999))""",
        "after": """# SECURED: Cryptographically secure random number generator
import secrets
token = str(secrets.randbelow(900000) + 100000)""",
        "doc_url": "https://cwe.mitre.org/data/definitions/330.html"
    },
    
    # Assert Statements in Production
    "B101": {
        "title": "Use of assert statements in application code",
        "description": "Assertions can be stripped when compiling Python to bytecode with optimizations (`python -O`). Use explicit conditional checks and raise appropriate exceptions.",
        "before": """# VULNERABLE: Assertions can be optimized away in production
assert user.is_authenticated, "User must be logged in"
grant_access(user)""",
        "after": """# SECURED: Explicit check and exception raising
if not user.is_authenticated:
    raise PermissionError("User must be logged in")
grant_access(user)""",
        "doc_url": "https://cwe.mitre.org/data/definitions/617.html"
    },
    
    # Hardcoded Secrets
    "B105": {
        "title": "Hardcoded password string",
        "description": "Hardcoding credentials or API keys directly in source code exposes them to leaks via version control. Use environment variables or secret managers.",
        "before": """# VULNERABLE: Hardcoded credential
API_KEY = "sk-live-5f3e9a4d8c7b6a5"
db_password = "super_secret_db_pass" """,
        "after": """# SECURED: Loaded from environment variables
import os
API_KEY = os.environ.get("API_KEY")
db_password = os.environ.get("DB_PASSWORD")""",
        "doc_url": "https://cwe.mitre.org/data/definitions/798.html"
    },
    
    # Insecure HTTP
    "B310": {
        "title": "Audit urllib opening of local files",
        "description": "Using `urllib` to open URLs can allow opening local files (e.g. `file://`) if input is uncontrolled, leading to local file inclusion.",
        "before": """# VULNERABLE: Can read file:// URLs
import urllib.request
response = urllib.request.urlopen(user_provided_url)""",
        "after": """# SECURED: Validate schema before fetching
import urllib.request
if user_provided_url.startswith(("http://", "https://")):
    response = urllib.request.urlopen(user_provided_url)
else:
    raise ValueError("Invalid protocol")""",
        "doc_url": "https://cwe.mitre.org/data/definitions/73.html"
    }
}

# Add matching alias mappings for Semgrep rules
SEMGREP_MAPPINGS = {
    "python.sqlite.security.audit.sqlite-execute-format": "B608",
    "python.lang.security.audit.sql.sqlite-execute-format": "B608",
    "python.lang.security.audit.sql.sqlite-execute-format-string": "B608",
    "python.lang.security.audit.sql.sqlite-execute-string": "B608",
    "python.lang.security.audit.sql.sqlalchemy-execute-format": "B608",
    "python.lang.security.audit.sql.mysql-execute-format": "B608",
    "python.lang.security.audit.sql.psycopg2-execute-format": "B608",
    "python.lang.security.deserialization.pickle.avoid-pickle": "B301",
    "python.lang.security.audit.md5.avoid-md5": "B303",
    "python.lang.security.audit.sha1.avoid-sha1": "B303",
    "python.lang.security.audit.subprocess.subprocess-shell-true": "B602",
    "python.lang.security.audit.subprocess.subprocess-shell-true.subprocess-shell-true": "B602",
    "python.lang.security.audit.random.weak-random.weak-random": "B311",
    "python.lang.security.audit.crypto.weak-symmetric-cipher": "B303",
    "python.lang.security.audit.network.bind-all-interfaces.bind-all-interfaces": "B104",
    "python.lang.security.audit.network.bind.bind-all-interfaces": "B104",
    "python.lang.security.audit.assert.use-of-assert": "B101",
    "python.lang.security.audit.hardcoded-password": "B105",
}

def get_fix_suggestion(rule_id: str, message: str) -> dict:
    """
    Finds a fix suggestion (before/after snippet + description) based on rule_id or message keywords.
    """
    normalized_rule = rule_id.strip()
    
    # Try looking up direct match or alias
    target_rule = normalized_rule
    if target_rule in SEMGREP_MAPPINGS:
        target_rule = SEMGREP_MAPPINGS[target_rule]
        
    if target_rule in FIX_CATALOG:
        return FIX_CATALOG[target_rule]
        
    # If no direct match, apply regex/keyword matching logic to provide contextual fallbacks
    rule_lower = rule_id.lower()
    msg_lower = message.lower()
    
    # 1. SQL Injection
    if "sql" in rule_lower or "injection" in rule_lower or "query" in rule_lower or "cursor.execute" in msg_lower:
        return {
            "title": "SQL Parameterization",
            "description": "Constructing SQL queries using string formatting permits SQL injection. Parameterize your variables using query placeholders.",
            "before": """# VULNERABLE: Variable interpolation in SQL query
query = "SELECT * FROM items WHERE category = '%s'" % category_name
cursor.execute(query)""",
            "after": """# SECURED: Use parameter binding
query = "SELECT * FROM items WHERE category = ?"
cursor.execute(query, (category_name,))""",
            "doc_url": "https://owasp.org/www-community/attacks/SQL_Injection"
        }
        
    # 2. Command Injection / Subprocess
    if "subprocess" in rule_lower or "shell" in rule_lower or "popen" in rule_lower or "system(" in msg_lower:
        return {
            "title": "Avoid Shell Execution",
            "description": "Running shell commands with raw variables exposes the environment to Command Injection. Disable shell execution and supply arguments as a list.",
            "before": """# VULNERABLE: Spawning shell command
import os, subprocess
subprocess.run(f"ping -c 1 {user_ip}", shell=True)""",
            "after": """# SECURED: Run without shell, pass args as list
import subprocess
subprocess.run(["ping", "-c", "1", user_ip], shell=False)""",
            "doc_url": "https://owasp.org/www-community/attacks/Command_Injection"
        }
        
    # 3. Hardcoded secrets
    if "secret" in rule_lower or "password" in rule_lower or "key" in rule_lower or "token" in rule_lower or "credentials" in msg_lower:
        return {
            "title": "Extract Hardcoded Secrets",
            "description": "Storing plaintext credentials, keys, or tokens in source code poses a critical leakage risk. Load secrets from environment variables or a configuration manager.",
            "before": """# VULNERABLE: Secret embedded in code
SECRET_KEY = "xyz123_prod_apikey"
DB_PASS = "admin_password" """,
            "after": """# SECURED: Fetch from environment variables
import os
SECRET_KEY = os.getenv("SECRET_KEY")
DB_PASS = os.getenv("DB_PASSWORD")""",
            "doc_url": "https://cwe.mitre.org/data/definitions/798.html"
        }
        
    # 4. Insecure Hash
    if "md5" in rule_lower or "sha1" in rule_lower or "hash" in rule_lower:
        return {
            "title": "Secure Hashing Algorithms",
            "description": "Weak hashing algorithms like MD5/SHA-1 are mathematically broken. Transition to strong hashing algorithms (e.g. SHA-256) or salt-based password hashes (e.g. bcrypt).",
            "before": """# VULNERABLE: Weak hash algorithm
import hashlib
digest = hashlib.md5(data).hexdigest()""",
            "after": """# SECURED: SHA-256 hash algorithm
import hashlib
digest = hashlib.sha256(data).hexdigest()""",
            "doc_url": "https://cwe.mitre.org/data/definitions/328.html"
        }
        
    # 5. Deserialization
    if "pickle" in rule_lower or "yaml" in rule_lower or "load" in rule_lower or "deserialize" in msg_lower:
        return {
            "title": "Safe Serialization",
            "description": "Loading serialized binary payloads can prompt remote code execution. Exchange data using secure formats like JSON, XML, or YAML's safe loaders.",
            "before": """# VULNERABLE: Loading unsafe serialize data
import yaml
parsed = yaml.load(user_content) # Unsafe Loader""",
            "after": """# SECURED: Safe YAML parsing
import yaml
parsed = yaml.safe_load(user_content)""",
            "doc_url": "https://owasp.org/www-community/vulnerabilities/Deserialization_of_untrusted_data"
        }
        
    # 6. Default generic fallback
    return {
        "title": f"Fix suggestion for rule {rule_id}",
        "description": f"Ensure your code aligns with secure standards. Review context around rule {rule_id}: {message}",
        "before": """# VULNERABLE / UNSECURE PATTERN
# Review vulnerability reports for recommendations.""",
        "after": """# SECURED PATTERN
# Implement validation, access controls, or safer libraries.""",
        "doc_url": "https://owasp.org"
    }
