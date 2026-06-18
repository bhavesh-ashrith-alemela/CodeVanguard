# CodeVanguard

> **Scan. Detect. Secure. In Seconds.**

CodeVanguard is a modern, high-performance Static Application Security Testing (SAST) mini-tool designed to help developers inspect Python codebases for bugs, vulnerabilities, and code-quality issues. It integrates industry-standard analysis engines (**Bandit** and **Semgrep**) executing in parallel to provide immediate security insights, clear severities, side-by-side fix recommendations, and exports in multiple compliant formats (HTML, PDF, JSON, CSV).

---

## Key Features

- **Upload & Scan Options**: Drag-and-drop a single `.py` file or a compressed `.zip` codebase (up to 10MB). Pasting raw Python code directly is also supported.
- **Secure File Handlers**: Includes path validation (Zip Slip mitigation) to prevent arbitrary path traversal during archive extraction.
- **Parallel Analysis Engine**: Bandit (syntax-tree security checks) and Semgrep (rule-based scanner) execute concurrently for fast completion.
- **Interactive Dark-themed Dashboard**: Responsive UI styled with Tailwind CSS + DaisyUI.
  - Live progress tracking using HTMX status polling.
  - Instant client-side filters for scanner type, severities, and filename search.
- **Actionable Fix Recommendations**: Common vulnerabilities map directly to side-by-side "Before/After" secure code patches.
- **Compliance Reports**: Download assessment results in standalone HTML, print-ready PDF (using an auto-fallback engine), spreadsheet-ready CSV, or machine JSON.
- **Persistent Scan History**: Re-verify previous reports and purge outdated scans via an SQLite database.
- **Vulnerable Gallery**: Provides pre-configured code templates (SQL Injection, Command Injection, Secrets Leak, Deserialization) to demo the scanner instantly.

---

## Architecture Flow

```
              ┌────────────────────────┐
              │  Jinja2 / HTMX Web UI  │
              └───────────┬────────────┘
                          │ (ZIP upload, py, or pasted text)
                          ▼
              ┌────────────────────────┐
              │   FastAPI Web Server   │
              └───────────┬────────────┘
                          │ (Safe file extraction & validation)
                          ▼
              ┌────────────────────────┐
              │    SQLite Database     │ ◄─── (Stores metadata / status)
              └───────────┬────────────┘
                          │ (Async background task)
                          ▼
              ┌────────────────────────┐
              │   Parallel Orchestrate │
              └─────┬────────────┬─────┘
                    │            │
                    ▼            ▼
             ┌────────────┐┌────────────┐
             │   Bandit   ││  Semgrep   │ (Subprocess execution)
             └──────┬─────┘└─────┬──────
                    │            │
                    └─────┬──────┘
                          │ (Aggregates and normalizes findings)
                          ▼
              ┌────────────────────────┐
              │   Report Generators    │ ───► (HTML / PDF / JSON / CSV)
              └────────────────────────┘
```

---

## Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Frontend**: Jinja2 + Tailwind CSS (via CDN) + DaisyUI + HTMX
- **Scanners**: Bandit, Semgrep
- **Storage**: SQLite3 (persistent history)
- **PDF Compiler**: WeasyPrint with a pure-Python `xhtml2pdf` fallback
- **Container**: Docker (multi-stage-ready debian-slim)

---

## Quick Start (Local Setup)

This project is optimized for speed using [uv](https://github.com/astral-sh/uv), a fast Python package installer.

### Prerequisites

Ensure you have Python 3.11+ installed.

### 1. Clone & Initialize Environment

```bash
# Clone the repository
cd CodeVanguard

# Create a virtual environment
python -m venv .venv
# OR using uv (much faster)
uv venv
```

### 2. Activate Virtual Environment

- **Windows (PowerShell)**:
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
- **Linux / macOS**:
  ```bash
  source .venv/bin/activate
  ```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
# OR using uv
uv pip install -r requirements.txt
```

### 4. Run the Server

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Docker Deployment (One-Command)

The Dockerfile is preconfigured with all Cairo/Pango system libraries to enable full WeasyPrint PDF compilation out-of-the-box.

### 1. Build the Image
```bash
docker build -t codevanguard .
```

### 2. Run the Container
```bash
docker run -d -p 8000:8000 --name codevanguard-app codevanguard
```
Open [http://localhost:8000](http://localhost:8000) to view the live app.

---

## Demo Testing

1. Go to the **Gallery** page.
2. Select any vulnerability example (e.g. **SQL Injection**).
3. Click **Analyze Snippet**.
4. The scanner will poll, execute, and load the dashboard demonstrating the issue and showing the parameterized SQL query fix.
