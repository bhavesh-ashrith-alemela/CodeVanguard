# GitHub App Setup Guide for CodeVanguard

This guide provides step-by-step instructions for registering and configuring the official **CodeVanguard GitHub App**.

---

## 1. Create the GitHub App

1. Sign in to your GitHub account.
2. Navigate to:
   - **Personal Account**: `GitHub Settings` > `Developer settings` > `GitHub Apps` > `New GitHub App`.
   - **Organization Account** (recommended for production): `Organization Settings` > `Developer settings` > `GitHub Apps` > `New GitHub App`.

---

## 2. General Information

| Field | Production Value | Local Development Value | Description |
| :--- | :--- | :--- | :--- |
| **GitHub App name** | `CodeVanguard` (or `CodeVanguard-SAST`) | `CodeVanguard-Dev-<YourName>` | Must be globally unique across all GitHub. |
| **Homepage URL** | `https://code-vanguard.vercel.app` | `http://localhost:3000` | The primary landing page for CodeVanguard. |
| **Description** | Open-source SAST platform powered by Bandit & Semgrep. | Development instance | Displayed on GitHub Marketplace/App page. |

---

## 3. URLs and Authorization Flow

| Setting | Production Value | Local Development Value | Notes |
| :--- | :--- | :--- | :--- |
| **Callback URL** | `https://code-vanguard.vercel.app/api/auth/github/callback` | `http://localhost:3000/api/auth/github/callback` | Receives OAuth user authorization code. Proxied by Next.js to backend. |
| **Setup URL (optional)** | `https://code-vanguard.vercel.app/github/setup` | `http://localhost:3000/github/setup` | Redirect target after app installation. |
| **Request user authorization (OAuth) during installation** | **CHECKED** (Enabled) | **CHECKED** (Enabled) | **Critical**: Ensures installing users are simultaneously authenticated. |

---

## 4. Webhook Configuration

> [!IMPORTANT]
> The Webhook URL points **directly** at the Render backend (`/api/github/webhook`), completely bypassing Vercel. This prevents serverless function execution timeouts and proxy drops.

| Field | Production Value | Local Development Value |
| :--- | :--- | :--- |
| **Active** | **CHECKED** (Enabled) | **CHECKED** (Enabled) |
| **Webhook URL** | `https://codevanguard.onrender.com/api/github/webhook` | `https://<your-ngrok-or-smee-subdomain>/api/github/webhook` |
| **Webhook secret** | High-entropy random string (e.g. `openssl rand -hex 32`) | Same random string |
| **SSL verification** | **Enable SSL verification** | **Enable SSL verification** |

---

## 5. Permissions & Event Subscriptions

### Recommended Phase 1 Permissions
To minimize friction and maximize trust during public launch, declare strictly what CodeVanguard needs to analyze code:

| Type | Permission | Access | Purpose |
| :--- | :--- | :--- | :--- |
| **Repository permissions** | **Contents** | `Read-only` | Stream repository tarballs and resolve commit SHAs and branches. |
| **Repository permissions** | **Metadata** | `Read-only` | Mandatory for all GitHub Apps; reads repository names, default branch, visibility. |

> [!CAUTION]
> **Contents: write** must **NOT** be requested at this stage. CodeVanguard only proposes fixes within its own UI or drafts patches; write access to source code is never required in Phase 1.

### Tradeoff Analysis: Phase 2 Permissions
GitHub allows declaring additional permissions now or requesting an upgrade later:
- `Checks: write` (Create Check Runs and post inline status on commits/PRs)
- `Pull requests: write` (Comment security findings and fix suggestions on pull requests)
- `Security events: write` (Upload SARIF results to the GitHub Advanced Security tab)

#### Comparison:
- **Declaring Phase 2 Now**:
  - *Advantage*: When automated PR scanning and check runs are released in Phase 2, existing users will not be prompted to re-authorize. Integrations continue seamlessly.
  - *Disadvantage*: Security teams and open-source maintainers may hesitate to install an app asking for write access to PRs and Checks for an initial on-demand scanning tool.
- **Declaring Minimal Phase 1 Only (Recommended)**:
  - *Advantage*: Immediate user trust and fastest adoption. Users grant only read access to repository contents.
  - *Disadvantage*: When Phase 2 ships, every installed organization admin must review and approve the permission upgrade before PR check runs become active.

---

### Subscribe to Events
Check the following webhook event boxes:
- [x] **Installation** (`created`, `deleted`, `suspend`, `unsuspend`)
- [x] **Installation target** (`renamed`)
- [x] **Installation repositories** (`added`, `removed`)

*(For Phase 2, `Push` and `Pull request` events will be enabled).*

---

## 6. Where can this GitHub App be installed?
Select:
- **Any account** (Public GitHub App) to allow any GitHub user or organization to install CodeVanguard.

---

## 7. Generate Secrets & Private Key

After saving the GitHub App:

1. **Private Key**:
   - Scroll to the bottom of the App settings page to **Private keys**.
   - Click **Generate a private key**.
   - Download the `.pem` file.
   - Base64-encode the file contents for environment variable storage:
     ```bash
     base64 -i path/to/private-key.pem | tr -d '\n'
     ```
2. **Client Secrets**:
   - Under **Client secrets**, click **Generate a new client secret**.
   - Copy the generated client secret.
3. **App ID & Client ID**:
   - Note the numeric **App ID** (at the top of General settings).
   - Note the **Client ID** (`Iv1.xxx`).
   - Note the **App Slug** (e.g., `codevanguard-sast` from the public link `https://github.com/apps/<slug>`).
4. **Token Encryption Key**:
   - Generate a 32-byte urlsafe base64 key for encrypting user tokens with Fernet:
     ```bash
     python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```

---

## 8. Environment Variable Configuration

### Backend Service (Render):
```env
GITHUB_APP_ID=123456
GITHUB_APP_CLIENT_ID=Iv1.xxxxxxxxxxxx
GITHUB_APP_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GITHUB_APP_PRIVATE_KEY=LS0tLS1CRUdJTi... (Base64-encoded PEM)
GITHUB_WEBHOOK_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GITHUB_APP_SLUG=codevanguard-sast
TOKEN_ENCRYPTION_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx=
FRONTEND_URL=https://code-vanguard.vercel.app
```

### Frontend Service (Vercel):
```env
BACKEND_API_URL=https://codevanguard.onrender.com
NEXT_PUBLIC_GITHUB_APP_SLUG=codevanguard-sast
```
