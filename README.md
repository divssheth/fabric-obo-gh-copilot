# Fabric OBO Runbook (Local + Cloud)

This runbook documents how to run the active architecture in this repository:
- Backend API: `backend_gh/main.py`
- OBO MCP server: `mcp_server_obo/server.py`
- Frontend: `frontend/index.html`

## Active Architecture (Approach B)

**Approach B** is the canonical baseline:
- Backend orchestrates via Copilot SDK (CopilotClient) from `github-copilot-sdk`.
- MCP server (FastMCP) executes tools with header-forwarded OBO for Power BI/Fabric.
- Frontend bootstraps with MSAL, frontend MSAL config served by backend `/client-config` (no hardcoding).
- Authentication: fail-closed user-delegated OBO via bearer token validation and MCP token resolver.
- Security: confused-deputy mitigation via allowlist routing and header forwarding only to configured MCP endpoint.

See [comparison.md](comparison.md) for detailed architecture comparison.

### Note on Approach A

**Approach A** (MAF + Foundry + argument injection) is archived in `archive/approach-a/` and not used by this runbook.
It injects Fabric token as MCP tool argument instead of using header-forwarded OBO.
It is retained for reference only.

---

## 1) Architecture and request flow

1. Browser signs in with MSAL and gets a user access token for your backend API scope.
2. Browser calls backend `/chat` with `Authorization: Bearer <user-token>`.
3. Backend validates token and forwards that Authorization header only to the configured MCP server.
4. MCP validates the same user token and performs OBO for Power BI/Fabric.
5. MCP executes DAX and returns results.

Security highlights:
- Confused deputy guard in backend: header only forwarded to configured OBO MCP endpoint.
- Fail-closed auth mode: only `AUTH_MODE=user_delegated` is accepted.

---

## 2) Prerequisites

- Python 3.11+ (recommended)
- Azure tenant where you can create app registrations and managed identities
- Fabric/Power BI workspace + dataset
- GitHub token for Copilot SDK (`GITHUB_TOKEN`)

Optional for local dev convenience:
- VS Code Live Server extension (or use Python http server command below)

---

## 3) Azure identity objects you need

Create and keep track of these IDs:

1. Frontend app registration (SPA)
   - Used by browser MSAL
   - Has redirect URI for local and cloud frontend URL

2. Backend app registration (Web/API)
   - This is the API audience for frontend tokens
   - This is also the confidential client used in OBO
   - Its client ID becomes `AZURE_CLIENT_ID`

3. User-assigned managed identity (UAMI)
   - Attached to your cloud runtime
   - Its client ID becomes `UAMI_CLIENT_ID`

---

## 4) App registration setup (required for both local and cloud)

### 4.1 Backend app registration (Web/API)

In Azure Portal -> Microsoft Entra ID -> App registrations -> your backend app:

1. Expose an API
   - Set Application ID URI (for example `api://<backend-client-id>`)
   - Add scope `access_as_user`

2. API permissions
   - Add delegated permissions for Power BI API needed by your queries
   - Grant admin consent for tenant

3. Authentication
   - Ensure platform is appropriate for your backend API scenario

4. Federated credentials (for cloud secretless OBO)
   - Certificates and secrets -> Federated credentials -> Add credential
   - Credential scenario: Managed identity
   - Select your UAMI
   - Audience: `api://AzureADTokenExchange`

### 4.2 Frontend app registration (SPA)

In your frontend app registration:

1. Authentication
   - Platform: Single-page application
   - Add redirect URIs:
     - Local: `http://localhost:5500/frontend/index.html`
     - Cloud: your hosted frontend URL (for example `https://<frontend-host>/index.html`)

2. API permissions
   - Add delegated permission to your backend API scope:
     - `api://<backend-client-id>/access_as_user`
   - Grant/admin-consent if required by tenant policy

---

## 5) Local development setup

### 5.1 Environment file

Copy `.env.example` to `.env` and set values.

Minimum local values:

- `AZURE_CLIENT_ID=<backend-app-client-id>`
- `AZURE_TENANT_ID=<tenant-id>`
- `ENVIRONMENT=local`
- `OBO_CLIENT_SECRET=<backend-app-client-secret>`
- `UAMI_CLIENT_ID=` (can be empty for local secret fallback)
- `FABRIC_WORKSPACE_ID=<workspace-id>`
- `FABRIC_DATASET_ID=<dataset-id>`
- `GITHUB_TOKEN=<github-token>`
- `OBO_MCP_SERVER_NAME=fabric-obo`
- `OBO_MCP_SERVER_URL=http://localhost:8002/mcp`
- `AUTH_MODE=user_delegated`
- `OBO_API_CLIENT_ID=<backend-app-client-id>`
- `OBO_REQUIRED_SCOPE=access_as_user`
- `FRONTEND_ORIGIN=http://localhost:5500`
- `FRONTEND_BACKEND_URL=http://localhost:8000`
- `FRONTEND_MSAL_CLIENT_ID=<frontend-app-client-id>`
- `FRONTEND_MSAL_AUTHORITY=https://login.microsoftonline.com/<tenant-id>`
- `FRONTEND_MSAL_REDIRECT_URI=http://localhost:5500/frontend/index.html`
- `FRONTEND_API_SCOPE=api://<backend-app-client-id>/access_as_user`

### 5.2 Install dependencies

```powershell
cd "C:\Users\divyesheth\OneDrive - Microsoft\Documents\python-projects\fabric-obo"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 5.3 Start services (3 terminals)

Terminal 1: MCP server
```powershell
cd "C:\Users\divyesheth\OneDrive - Microsoft\Documents\python-projects\fabric-obo"
.\.venv\Scripts\python mcp_server_obo/server.py
```

Terminal 2: Backend API
```powershell
cd "C:\Users\divyesheth\OneDrive - Microsoft\Documents\python-projects\fabric-obo"
.\.venv\Scripts\python -m uvicorn backend_gh.main:app --host 127.0.0.1 --port 8000
```

Terminal 3: Frontend static server
```powershell
cd "C:\Users\divyesheth\OneDrive - Microsoft\Documents\python-projects\fabric-obo"
.\.venv\Scripts\python -m http.server 5500
```

Open browser:
- `http://localhost:5500/frontend/index.html`

### 5.4 Quick health checks

1. Backend client config endpoint
```powershell
curl http://localhost:8000/client-config
```

2. MCP endpoint should be reachable
```powershell
curl http://localhost:8002/mcp
```

3. In browser:
- Sign in
- Ask a chat question
- Confirm response appears

---

## 6) Cloud deployment (recommended: two services + managed identity)

Deploy backend and MCP as separate cloud services.

Reference topology:
- Service A: backend (`backend_gh.main:app`)
- Service B: mcp (`mcp_server_obo.server`)
- UAMI attached to Service B (MCP service)

Why attach UAMI to MCP service:
- OBO credential creation happens in `mcp_server_obo/obo_auth.py`.
- That process must be able to request MI token for `api://AzureADTokenExchange/.default`.

### 6.1 Cloud environment variables

Set for Backend service (A):
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `FABRIC_WORKSPACE_ID`
- `FABRIC_DATASET_ID`
- `GITHUB_TOKEN`
- `OBO_MCP_SERVER_NAME=fabric-obo`
- `OBO_MCP_SERVER_URL=https://<mcp-service-host>/mcp`
- `AUTH_MODE=user_delegated`
- `FRONTEND_ORIGIN=https://<frontend-host>`
- `FRONTEND_BACKEND_URL=https://<backend-host>`
- `FRONTEND_MSAL_CLIENT_ID`
- `FRONTEND_MSAL_AUTHORITY`
- `FRONTEND_MSAL_REDIRECT_URI`
- `FRONTEND_API_SCOPE`

Set for MCP service (B):
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `ENVIRONMENT=production`
- `UAMI_CLIENT_ID=<uami-client-id>`
- `OBO_CLIENT_SECRET=` (empty)
- `FABRIC_WORKSPACE_ID`
- `FABRIC_DATASET_ID`
- `OBO_API_CLIENT_ID=<backend-app-client-id>`
- `OBO_REQUIRED_SCOPE=access_as_user`
- `AUTH_MODE=user_delegated`

### 6.2 Federated credential checklist (cloud)

In backend app registration:
1. Federated credential exists and points to the same UAMI attached to MCP service.
2. Audience is exactly `api://AzureADTokenExchange`.
3. Backend app client ID matches `AZURE_CLIENT_ID` in MCP environment.
4. `UAMI_CLIENT_ID` in MCP env matches attached UAMI.

### 6.3 CORS and redirect URIs

- Backend `FRONTEND_ORIGIN` must match your frontend origin exactly.
- Frontend app registration must include exact redirect URI used in browser.

### 6.4 Startup commands in cloud containers

Backend container command:
```bash
python -m uvicorn backend_gh.main:app --host 0.0.0.0 --port 8000
```

MCP container command:
```bash
python mcp_server_obo/server.py
```

---

## 7) OIDC/federation troubleshooting

### Error: OBO exchange failed / invalid client assertion

Check:
1. Federated credential exists on backend app registration (not frontend app).
2. UAMI on runtime matches federated credential target.
3. Audience is `api://AzureADTokenExchange`.
4. `ENVIRONMENT=production` and `OBO_CLIENT_SECRET` is empty.

### Error: Missing required delegated scope

Check:
1. Frontend requests `FRONTEND_API_SCOPE` exactly.
2. Backend app exposes `access_as_user`.
3. User/token contains scope claim with `access_as_user`.

### Error: Invalid audience in token validation

Check:
1. `OBO_API_CLIENT_ID` equals backend app client ID.
2. Frontend token audience is backend API, not Graph/Power BI directly.

### Error: CORS blocked in browser

Check:
1. `FRONTEND_ORIGIN` matches actual frontend origin.
2. Access backend via same origin configured in `/client-config`.

### Error: Fabric DatasetExecuteQueriesError / MSOLAP connection

Check:
1. Dataset ID and workspace ID are correct.
2. User has rights in workspace/model.
3. Power BI delegated permissions and tenant settings allow operation.

---

## 8) Validation checklist before go-live

- [ ] Local login and chat end-to-end succeeds
- [ ] Cloud login and chat end-to-end succeeds
- [ ] MCP uses `ENVIRONMENT=production` and no secret fallback
- [ ] Federated credential is configured and validated
- [ ] CORS and redirect URIs match production hosts
- [ ] Logs do not contain secrets

---

## 9) Useful file references

- `.env.example`
- `backend_gh/main.py`
- `backend_gh/config.py`
- `mcp_server_obo/server.py`
- `mcp_server_obo/obo_auth.py`
- `frontend/app.js`
