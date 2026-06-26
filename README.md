# Fabric OBO — Backend + MCP Architecture

This guide covers the complete setup for running the active architecture in this repository:
- **Backend API**: `backend_gh/main.py` — FastAPI orchestrator via Copilot SDK
- **OBO MCP Server**: `mcp_server_obo/server.py` — Tool executor for Power BI/Fabric
- **Frontend**: `frontend/index.html` — MSAL-authenticated SPA

---

## Quick Start (Local)

1. Copy `.env.example` to `.env` and fill in your values (see [Environment Configuration](#environment-configuration))
2. Create and activate venv:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Start three services in separate terminals (see [Running Locally](#running-locally))
4. Open `http://localhost:5500/frontend/index.html` and sign in
5. Ask a chat question to verify end-to-end flow

---

## Architecture Overview

**How it works:**

1. Browser signs in with MSAL → gets user access token for backend API scope
2. Browser calls backend `/chat` → `Authorization: Bearer <user-token>`
3. Backend validates token → forwards header only to configured MCP server
4. MCP validates token → performs OBO for Power BI/Fabric
5. MCP executes DAX → returns results

**Active approach:** Copilot SDK + header-forwarded OBO (Approach B)
- Fail-closed user-delegated authentication
- Confused-deputy mitigation via allowlist routing
- No secrets passed in arguments; tokens only in headers

**Reference:** [comparison.md](comparison.md) — detailed architecture history. Approach A (MAF + Foundry + argument injection) is archived in `archive/approach-a/` for reference only.

---

## Prerequisites

- Python 3.11+
- Azure tenant with ability to create app registrations and managed identities
- Power BI/Fabric workspace + dataset
- GitHub token for Copilot SDK (`GITHUB_TOKEN`)

Optional: VS Code Live Server extension (or use Python's built-in http.server)

---

## Azure Identity Setup

Create three Azure identity objects:

1. **Frontend app registration (SPA)**
   - Used by browser MSAL for user sign-in
   - Redirect URIs: local dev and cloud frontend URLs

2. **Backend app registration (Web/API)**
   - API audience for frontend tokens (backend scope)
   - Confidential client for OBO credential creation
   - Client ID becomes `AZURE_CLIENT_ID`

3. **User-assigned managed identity (UAMI)**
   - Attached to cloud MCP service runtime
   - Client ID becomes `UAMI_CLIENT_ID`
   - Federated with backend app registration for secretless OBO in production

### Configuring Backend App (Web/API)

In Azure Portal → Microsoft Entra ID → App registrations → your backend app:

1. **Expose an API**
   - Set Application ID URI: `api://<backend-client-id>`
   - Add scope: `access_as_user`

2. **API permissions**
   - Add delegated permissions for Power BI API
   - Grant admin consent for your tenant

3. **Federated credentials** (for cloud production)
   - Go to: Certificates and secrets → Federated credentials → Add credential
   - Scenario: Managed identity
   - Select your UAMI
   - Audience: `api://AzureADTokenExchange`

### Configuring Frontend App (SPA)

In your frontend app registration:

1. **Authentication**
   - Platform: Single-page application
   - Redirect URIs:
     - Local: `http://localhost:5500/frontend/index.html`
     - Cloud: `https://<frontend-host>/index.html`

2. **API permissions**
   - Add delegated permission: `api://<backend-client-id>/access_as_user`
   - Grant/admin-consent if required

---

## Local Development

### Environment Configuration

Copy `.env.example` to `.env` and populate values:

**Essential for local:**
```
AZURE_CLIENT_ID=<backend-app-client-id>
AZURE_TENANT_ID=<tenant-id>
ENVIRONMENT=local
OBO_CLIENT_SECRET=<backend-app-client-secret>
FABRIC_WORKSPACE_ID=<workspace-id>
FABRIC_DATASET_ID=<dataset-id>
GITHUB_TOKEN=<github-token>
OBO_MCP_SERVER_URL=http://localhost:8002/mcp
FRONTEND_ORIGIN=http://localhost:5500
FRONTEND_BACKEND_URL=http://localhost:8000
FRONTEND_MSAL_CLIENT_ID=<frontend-app-client-id>
FRONTEND_MSAL_AUTHORITY=https://login.microsoftonline.com/<tenant-id>
FRONTEND_MSAL_REDIRECT_URI=http://localhost:5500/frontend/index.html
FRONTEND_API_SCOPE=api://<backend-app-client-id>/access_as_user
```

See `.env.example` for complete list with inline documentation.

### Running Locally

**Terminal 1 — MCP server:**
```powershell
.\.venv\Scripts\python mcp_server_obo/server.py
```

**Terminal 2 — Backend API:**
```powershell
.\.venv\Scripts\python -m uvicorn backend_gh.main:app --host 127.0.0.1 --port 8000
```

**Terminal 3 — Frontend (static file server):**
```powershell
.\.venv\Scripts\python -m http.server 5500
```

Then open: `http://localhost:5500/frontend/index.html`

### Health Checks

```powershell
# Backend client config endpoint
curl http://localhost:8000/client-config

# MCP endpoint reachable
curl http://localhost:8002/mcp
```

In the browser, sign in and ask a question to verify end-to-end flow works.

---

## Cloud Deployment

Deploy backend and MCP as separate services. Reference topology:
- **Service A (Backend)**: `backend_gh.main:app` on port 8000
- **Service B (MCP)**: `mcp_server_obo.server` on port 8002
- **UAMI**: attached to Service B (MCP service)

Why attach UAMI to MCP?
- OBO credential creation happens in `mcp_server_obo/obo_auth.py`
- Must request MI token for `api://AzureADTokenExchange/.default` scope

### Backend Service (A) Environment

```
AZURE_CLIENT_ID=<backend-app-client-id>
AZURE_TENANT_ID=<tenant-id>
FABRIC_WORKSPACE_ID=<workspace-id>
FABRIC_DATASET_ID=<dataset-id>
GITHUB_TOKEN=<github-token>
OBO_MCP_SERVER_URL=https://<mcp-service-host>/mcp
FRONTEND_ORIGIN=https://<frontend-host>
FRONTEND_BACKEND_URL=https://<backend-host>
FRONTEND_MSAL_CLIENT_ID=<frontend-app-client-id>
FRONTEND_MSAL_AUTHORITY=https://login.microsoftonline.com/<tenant-id>
FRONTEND_MSAL_REDIRECT_URI=https://<frontend-host>/frontend/index.html
FRONTEND_API_SCOPE=api://<backend-app-client-id>/access_as_user
```

### MCP Service (B) Environment

```
AZURE_CLIENT_ID=<backend-app-client-id>
AZURE_TENANT_ID=<tenant-id>
ENVIRONMENT=production
UAMI_CLIENT_ID=<uami-client-id>
OBO_CLIENT_SECRET=<leave empty>
FABRIC_WORKSPACE_ID=<workspace-id>
FABRIC_DATASET_ID=<dataset-id>
OBO_API_CLIENT_ID=<backend-app-client-id>
OBO_REQUIRED_SCOPE=access_as_user
```

### Cloud Container Commands

**Backend:**
```bash
python -m uvicorn backend_gh.main:app --host 0.0.0.0 --port 8000
```

**MCP:**
```bash
python mcp_server_obo/server.py
```

### Federated Credential Checklist

In backend app registration:
- [ ] Federated credential exists and points to the UAMI attached to MCP service
- [ ] Audience is exactly `api://AzureADTokenExchange`
- [ ] Backend app client ID matches `AZURE_CLIENT_ID` in MCP environment
- [ ] `UAMI_CLIENT_ID` in MCP env matches attached UAMI

### CORS and Redirect URIs

- Backend `FRONTEND_ORIGIN` must match your frontend origin exactly
- Frontend app registration must include the exact redirect URI used in browser

---

## Troubleshooting

### OBO exchange failed / invalid client assertion

**Check:**
1. Federated credential exists on backend app (not frontend)
2. UAMI on runtime matches federated credential target
3. Audience is `api://AzureADTokenExchange`
4. `ENVIRONMENT=production` and `OBO_CLIENT_SECRET` is empty

### Missing required delegated scope

**Check:**
1. Frontend requests `FRONTEND_API_SCOPE` exactly
2. Backend app exposes `access_as_user` scope
3. User/token contains scope claim with `access_as_user`

### Invalid audience in token validation

**Check:**
1. `OBO_API_CLIENT_ID` equals backend app client ID
2. Frontend token audience is backend API, not Graph/Power BI directly

### CORS blocked in browser

**Check:**
1. `FRONTEND_ORIGIN` matches actual frontend origin
2. Access backend via same origin configured in `/client-config`

### Fabric DatasetExecuteQueriesError / MSOLAP connection

**Check:**
1. Dataset ID and workspace ID are correct
2. User has rights in workspace/model
3. Power BI delegated permissions and tenant settings allow operation

---

## Pre-Go-Live Checklist

- [ ] Local end-to-end signin and chat works
- [ ] Cloud end-to-end signin and chat works
- [ ] MCP service: `ENVIRONMENT=production` and `OBO_CLIENT_SECRET` is empty
- [ ] Federated credential configured on backend app, points to UAMI
- [ ] CORS and redirect URIs match production hosts exactly
- [ ] Logs scrubbed of secrets before shipping

---

## Key Files

- `backend_gh/main.py` — FastAPI orchestrator
- `backend_gh/config.py` — Backend configuration
- `mcp_server_obo/server.py` — MCP server entry point
- `mcp_server_obo/obo_auth.py` — Token validation and OBO exchange
- `frontend/index.html` — SPA entry point
- `.env.example` — Environment variables template
- `comparison.md` — Detailed architecture history
