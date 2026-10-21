# Contributing to CodeVanguard

Thank you for your interest in contributing to CodeVanguard! We are building a modern, reviewer-focused Static Application Security Testing (SAST) and secret detection platform that makes security feedback deterministic, actionable, and non-blocking.

---

## 1. Principles & Non-Negotiables

Before writing code, please review our core architectural invariants:
- **Zero Source Code Persistence**: Never store source files, raw archives, or code snippets longer than ~7 context lines in databases or persistent storage.
- **Safe Secret Handling**: Never store raw secrets. Only store masked previews (`first 4 + last 2 chars`) and salted SHA-256 hashes. Never validate secrets against 3rd-party provider APIs.
- **Deterministic Facts**: Security facts (severities, lines, verdicts, actions) are computed deterministically. LLMs only format or suggest fixes.
- **UI Guidelines (`docs/ui-guidelines.md`)**: Follow Neo-Brutalist Minimalism (`#F5F4EE` canvas, `#14141A` borders, hard offset shadows). Reuse `components/ui` primitives. Never repeat facts on the same screen. Ensure mobile responsiveness (360px) and clean accessibility.
- **Test All Security Controls**: Every parser, extraction logic, permission check, or IDOR guard must have automated unit tests.

---

## 2. Local Development Setup

### Prerequisites
- Python 3.11+
- Node.js 18+ and `npm`
- Git 2.30+
- Optional: Docker and Docker Compose (for PostgreSQL and Redis)

### Backend Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/codevanguard/codevanguard.git
   cd codevanguard
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate    # On Windows: .venv\Scripts\activate
   ```
3. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
5. Run database migrations and start the backend:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   The backend API will be available at `http://localhost:8000`.

### Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Copy environment configuration:
   ```bash
   cp .env.local.example .env.local    # Ensure NEXT_PUBLIC_API_URL=http://localhost:8000
   ```
4. Start the Next.js development server:
   ```bash
   npm run dev
   ```
   Open `http://localhost:3000` in your browser.

---

## 3. Running Tests & Quality Checks

All pull requests must pass the test suites before merging:

### Backend Unit & Security Tests
Run the comprehensive test suite (including IDOR, archive safety, secret scanning, and PR summary golden tests):
```bash
python3 -m unittest discover tests
```

### Frontend TypeScript & Lint Checks
```bash
cd frontend
npx tsc --noEmit
npm run lint
```

### End-to-End Tests (Playwright)
```bash
cd frontend
npx playwright test
```

---

## 4. UI Design Rules

When making changes to the web dashboard:
- **Colors**: Canvas `#F5F4EE`, Ink Black `#14141A`, Card borders `2px solid #14141A`, Accent Lime `#D6F25B`, Accent Purple `#B8A2FF`, Critical `#FF6B3D`, High `#FFC93C`.
- **Card Primitives**: Reusable components from `components/ui` (`Chip`, `Button`, `StatusCard`, `SeverityBar`, `RepoSwitcher`, `EmptyState`, `Skeleton`, `ErrorState`).
- **No Duplicate Facts**: Ensure no metric, commit SHA, or severity count is repeated twice on the same screen.
- **Accessibility**: All buttons and interactive elements must have visible focus rings, ARIA labels, and contrast ratios compliant with WCAG AA.

---

## 5. Submitting a Pull Request

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/my-enhancement
   ```
2. Make small, focused commits with clear messages.
3. Ensure all tests pass locally.
4. Open a pull request against `main` with:
   - Clear summary of changes and motivation.
   - Verification steps or screenshots (if UI was touched).
   - Confirmation that no secrets or code persistence invariants were violated.
