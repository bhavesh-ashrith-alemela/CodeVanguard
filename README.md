# CodeVanguard

> **Secure your codebases in seconds.**
> **Live Application:** [https://code-vanguard.vercel.app/](https://code-vanguard.vercel.app/)

CodeVanguard is a high-performance, developer-focused Static Application Security Testing (SAST) application designed to analyze Python, JavaScript, TypeScript, and Go source code or compressed ZIP codebases for bugs, security weaknesses, and configuration errors.

The project is structured in a **decoupled architecture**:
1. **FastAPI REST API Backend**: Serves endpoints for asynchronous scanning execution, report generation, and system administration metrics.
2. **Next.js App Router Frontend**: Offers a highly polished, responsive Neo-Brutalist dashboard tracking scan progress, severity groupings, and side-by-side remediation patches.

---

## Tech Stack

- **Frontend**: Next.js (React App Router), TypeScript, Tailwind CSS, Lucide React
- **Backend**: FastAPI, Uvicorn, Python, Pydantic, Jinja2
- **Security Scanners**: Bandit (AST parsing) & Semgrep (pattern matching)
- **Database**: SQLite (local development fallback) & PostgreSQL / Supabase (production)
- **Report Exporters**: xhtml2pdf / WeasyPrint (PDF generation), Pandas (CSV/JSON/HTML generation)


---

## Key Features

- **Double-Engine SAST Scanner**: Concurrently executes **Bandit** (AST syntax tree inspections) and **Semgrep** (rule-based pattern checks) locally and offline.
- **Instant Local Performance**: Utilizes a pre-packaged offline ruleset and optimized process parameters to run scans instantly without registry downloads or telemetry transmissions.
- **Remediation Blueprints**: Displays context-rich vulnerable code snippets paired with secure, copy-pasteable repair recommendations.
- **Multi-Format Reports**: Export scan details as PDF (with an automated fallback renderer), HTML, JSON, or CSV formats.
- **Secure File Ingestion**: Restricts uploads by size (Max 10MB) and extension (`.py`, `.zip`), implementing directory traversal (Zip Slip) security validation.
- **Admin Control Room**: Secure dashboard displaying scan history logs, threat counters, audit trails, and data purge controls.
- **Production Hardened**: Features proxy-aware rate limiters, HttpOnly secure cookies, non-root Docker builds, and scoped CORS mappings.

---

## Directory Structure

```text
├── app/                  # FastAPI Backend Source
│   ├── routers/          # API route controllers (scan.py, admin.py)
│   ├── scanners/         # Scan orchestration (rules.yaml, bandit, semgrep)
│   ├── utils/            # Utilities (db.py, rate_limiter.py, report_generator.py)
│   └── main.py           # Application entry point
├── frontend/             # Next.js React Frontend
│   ├── src/
│   │   ├── app/          # App Router pages and styling stylesheets
│   │   └── components/   # UI components (Navbar, ToastProvider)
│   └── package.json      # Node configurations
├── tests/                # QA integration and security test suites
├── Dockerfile            # hardened production Docker container blueprint
└── requirements.txt      # Backend Python dependencies
```

---

## Local Development & Setup

### Part A: Booting the FastAPI Backend

1. **Activate the Virtual Environment**:
   * **Windows (PowerShell)**:
     ```powershell
     .venv\Scripts\Activate.ps1
     ```
   * **macOS / Linux**:
     ```bash
     source .venv/bin/activate
     ```

2. **Install Python Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Create a `.env` file in the root directory (refer to [.env.example](file:///.env.example) for options):
   ```text
   ENV=development
   PORT=8000
   DEFAULT_ADMIN_USER=admin
   DEFAULT_ADMIN_PASS=ChooseAStrongPassword123!
   ```

4. **Launch the Server**:
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   *The REST API will be active at `http://127.0.0.1:8000`.*

---

### Part B: Booting the Next.js Frontend

1. **Navigate to the frontend folder**:
   ```bash
   cd frontend
   ```

2. **Install Package Dependencies**:
   ```bash
   npm install
   ```

3. **Start the Dev Server**:
   ```bash
   npm run dev
   ```
   *The Next.js UI will be active at `http://localhost:3000`.*

---

## Hardened Production Deployment (100% Free Stack)

### 1. Provisioning a Database (Supabase)

To avoid data loss on Render's Free tier (which has an ephemeral filesystem), you must use an external database:
* Sign up for a free PostgreSQL database on **Supabase** (`https://supabase.com`).
* **CRITICAL**: Click the **Connect** button at the top of the Supabase project dashboard, choose **Connection Pooler**, set the mode to **Session** (uses port `5432`), and copy the connection URI. Do **NOT** use the **Direct Connection** URI, as it is IPv6-only and will fail with `Network is unreachable` on Render's IPv4 network.
* Replace the password placeholder in the copied URI.


### 2. Deploying the Backend (Render / Docker)

Render automatically builds and deploys the backend container on the Free tier.

* **Instance Type**: Docker Web Service (Free tier).
* **Environment Variables**:
  * `ENV` = `production`
  * `PORT` = `8000`
  * `DATABASE_URL` = `postgresql://postgres.[username]:[password]@...` *(Your Supabase connection string)*
  * `DEFAULT_ADMIN_USER` = `<your-admin-user>`
  * `DEFAULT_ADMIN_PASS` = `<strong-admin-pass>` (Required in production, will error if missing)
  * `ALLOWED_ORIGINS` = `https://your-frontend.vercel.app` (CORS whitelisting)

### 3. Deploying the Frontend (Vercel)

* **Framework Preset**: Next.js
* **Root Directory**: `frontend/`
* **Environment Variables**:
  * `NEXT_PUBLIC_API_URL` = `https://your-backend-subdomain.onrender.com` (Your Render URL)


---

## Running Quality & Security Audits

Execute tests against your running local server (`http://127.0.0.1:8000`):

```bash
# Run scan pipeline integration checks
python tests/test_scan.py

# Verify rate-limiting, CORS, and cookie security controls
python tests/test_security.py
```
