# Fabric OBO — AI Agent + Custom MCP Server with On-Behalf-Of Authentication

Connect AI agents to Microsoft Fabric semantic models with user-delegated (OBO) authentication. Each user's queries run under their own identity, respecting existing Fabric permissions.

## Why This Exists

Fabric's Data Agent exposes an MCP endpoint, but your agent sees the Data Agent's data — not each user's permissioned view. The Semantic Model MCP Server (Fabric Toolbox) is great for a single developer in VS Code, but isn't designed for multi-user agents.

This repo solves the enterprise pattern: take a user's identity, exchange it via On-Behalf-Of, and query Fabric as that specific user.

## Architecture

```
Browser (MSAL sign-in)
    │
    ▼  Authorization: Bearer <user-token>
┌─────────────────────────────────────┐
│  Backend API (FastAPI)              │
│  • Validates user token             │
│  • Orchestrates agent (Copilot SDK  │
│    or MAF + Foundry)                │
│  • Forwards token to MCP via header │
└────────────────┬────────────────────┘
                 │  Authorization: Bearer <user-token>
                 ▼
┌─────────────────────────────────────┐
│  OBO MCP Server                     │
│  • Validates user token             │
│  • OBO exchange → Fabric token      │
│  • Executes DAX queries as user     │
└─────────────────────────────────────┘
                 │
                 ▼
         Microsoft Fabric
       (Semantic Model / DAX)
```

**Two auth flows, completely isolated:**
1. **Backend → LLM (inference):** Service identity authenticates to GitHub Copilot or Azure AI Foundry. Nothing to do with the end user.
2. **Backend → MCP → Fabric (data access):** The end user's token is forwarded to the MCP server, which performs OBO to query Fabric as that user.

---

## Choose Your Orchestrator

| | `backend_gh/` (Copilot SDK) | `backend_maf/` (MAF + Foundry) |
|---|---|---|
| **LLM Provider** | GitHub Copilot (PAT) or Azure OpenAI (BYOK) | Azure AI Foundry |
| **Auth to LLM** | GitHub PAT or Azure OpenAI API key | Entra ID (DefaultAzureCredential) |
| **Agent Framework** | GitHub Copilot SDK | Microsoft Agent Framework |
| **MCP Integration** | Native `mcp_servers` config with headers | `MCPStreamableHTTPTool` with custom `http_client` |
| **Production Story** | BYOK avoids GitHub PAT (uses Azure OpenAI key) | Fully Entra ID — no keys or tokens |
| **Deployment** | Any compute | Agent on Foundry, MCP on Azure Container Apps |

Both backends expose the same API (`GET /client-config`, `POST /chat`) — the frontend works with either without changes.

---

## Why Two Orchestrators?

Both backends work identically for local development and prototyping. They diverge on **production identity management** — specifically, how the backend authenticates to the LLM provider without requiring personal accounts or manual secret rotation.

### The Account-Linking Problem (Copilot SDK — PAT Mode)

In a multi-user agent, the **LLM inference call is a service-level concern** — the backend calls the model on behalf of the application, not a specific end-user. Only the data access call (Fabric/OBO) needs user identity. A production-ready architecture separates these: service identity → LLM, user identity → data.

The Copilot SDK conflates these two concerns. Every LLM call requires a **GitHub Personal Access Token** tied to a human GitHub account with a Copilot subscription. **GitHub has no equivalent of Azure Managed Identity** — there is no way to say "this compute is authorized to call Copilot" without a personal token.

The SDK's [multi-tenancy guide](https://github.com/github/copilot-sdk/tree/main/docs/setup/multi-tenancy.md) suggests GitHub OAuth per-user as the production pattern, but this doesn't solve the core problem — it just means every end-user must:

1. Have a **GitHub account** (a second identity plane alongside their corporate Entra ID)
2. Hold an active **Copilot license** (per-seat cost)
3. Go through a **GitHub OAuth consent flow** (on top of their existing Entra sign-in)

This adds friction and cost without achieving what managed identity provides: a credential-free, human-free service authentication path for the LLM call.

| | Copilot SDK (PAT) | MAF (Managed Identity) |
|---|---|---|
| **Who authenticates to LLM?** | A human (via GitHub token) | The compute (via managed identity) |
| **Humans in the loop for LLM?** | Yes — always | No — zero |
| **Equivalent to Azure MI?** | Does not exist in GitHub | `DefaultAzureCredential` → system-assigned MI |
| **Multi-user scaling** | Each user needs GitHub + Copilot seat | Single service identity, unlimited users |

### Copilot SDK — BYOK Mode (Partial Mitigation)

BYOK (Bring Your Own Key) removes the GitHub dependency entirely — no Copilot subscription, no GitHub account. The SDK becomes a pure orchestration runtime that routes to your Azure OpenAI deployment via API key.

However, the SDK's [auth documentation](https://github.com/github/copilot-sdk/tree/main/docs/auth/authenticate.md) notes:

> "BYOK uses key-based authentication only. Microsoft Entra ID (Azure AD), managed identities, and third-party identity providers are not supported."

This means you're managing a **static API key** that must be rotated manually, stored securely, and shared across all sessions. It works — but it's a secret to manage rather than a credential-free identity.

### MAF + Azure AI Foundry (Production-Ready)

The Microsoft Agent Framework authenticates to Azure AI Foundry using `DefaultAzureCredential`, which in production resolves to the compute's **system-assigned managed identity**:

- **No personal accounts** — the service identity is attached to the compute, not a human
- **No API keys or secrets** — Entra ID handles token issuance and refresh automatically
- **Standard Azure RBAC** — assign "Azure AI Developer" role to the managed identity
- **Same identity model** your enterprise already uses for Azure SQL, Key Vault, Storage, etc.

### When to Use Which

| Scenario | Recommended Backend |
|---|---|
| Quick local prototyping / exploring Copilot SDK capabilities | `backend_gh/` (PAT mode) |
| Internal tool where all users have GitHub + Copilot | `backend_gh/` (PAT mode with per-user OAuth) |
| Prototype without GitHub dependency | `backend_gh/` (BYOK mode) |
| Production multi-user enterprise app | `backend_maf/` (MAF + Foundry) |
| Secretless deployment with managed identity | `backend_maf/` (MAF + Foundry) |

> **This repo includes both** so you can prototype quickly with the Copilot SDK and switch to MAF when moving to production — the MCP server, frontend, and auth flow remain identical.

---

## Quick Start (Local)

1. Clone and set up environment:
   ```powershell
   git clone <repo-url>
   cd fabric-obo
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your values (see [Environment Configuration](#environment-configuration))

3. Start services in separate terminals:

   **Terminal 1 — MCP Server:**
   ```powershell
   python mcp_server_obo/server.py
   ```

   **Terminal 2 — Backend (choose one):**
   ```powershell
   # Option A: Copilot SDK (PAT mode)
   python -m uvicorn backend_gh.main:app --host 127.0.0.1 --port 8000

   # Option B: MAF + Foundry
   python -m uvicorn backend_maf.main:app --host 127.0.0.1 --port 8000
   ```

   **Terminal 3 — Frontend (choose one):**

   Option A: VS Code Live Server (recommended)
   - Install the [Live Server extension](https://marketplace.visualstudio.com/items?itemName=ritwickdey.LiveServer)
   - Right-click `frontend/index.html` → "Open with Live Server"
   - It will serve on `http://localhost:5500` by default

   Option B: Python static server
   ```powershell
   python -m http.server 5500
   ```

4. Open `http://localhost:5500/frontend/index.html`, sign in, and ask a question.

---

## Prerequisites

- Python 3.11+
- Azure tenant with app registrations and managed identities
- Power BI / Fabric workspace + semantic model (dataset)
- **For Copilot SDK (PAT mode):** GitHub token with Copilot access
- **For Copilot SDK (BYOK mode):** Azure OpenAI endpoint + API key
- **For MAF:** Azure AI Foundry project endpoint (authenticate via `az login`)

---

## Environment Configuration

### Common Variables (all backends)

```env
AZURE_CLIENT_ID=<backend-app-client-id>
AZURE_TENANT_ID=<tenant-id>
FABRIC_WORKSPACE_ID=<workspace-id>
FABRIC_DATASET_ID=<dataset-id>
OBO_MCP_SERVER_URL=http://localhost:8002/mcp
FRONTEND_ORIGIN=http://localhost:5500
FRONTEND_BACKEND_URL=http://localhost:8000
FRONTEND_MSAL_CLIENT_ID=<frontend-app-client-id>
FRONTEND_MSAL_AUTHORITY=https://login.microsoftonline.com/<tenant-id>
FRONTEND_MSAL_REDIRECT_URI=http://localhost:5500/frontend/index.html
FRONTEND_API_SCOPE=api://<backend-app-client-id>/access_as_user
```

### MCP Server Variables

```env
ENVIRONMENT=local
OBO_CLIENT_SECRET=<backend-app-client-secret>
OBO_API_CLIENT_ID=<backend-app-client-id>
OBO_REQUIRED_SCOPE=access_as_user
```

### Copilot SDK Backend (`backend_gh/`)

```env
# PAT mode (default)
COPILOT_AUTH_MODE=pat
GITHUB_TOKEN=<github-token>

# OR BYOK mode (Azure OpenAI with API key)
COPILOT_AUTH_MODE=byok
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<api-key>
AZURE_OPENAI_MODEL=gpt-4o
```

### MAF Backend (`backend_maf/`)

```env
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
FOUNDRY_MODEL=gpt-4o
```

**No API key required.** MAF authenticates to Azure AI Foundry via Entra ID (`DefaultAzureCredential`):
- **Local:** Uses your `az login` session automatically — just run `az login` before starting the backend.
- **Production:** Uses Managed Identity on the compute (e.g., system-assigned identity on Azure Container Apps).
- **Required role:** The identity needs "Azure AI Developer" or "Cognitive Services OpenAI User" on the Foundry project.

---

## Azure Identity Setup

Create three Azure identity objects:

1. **Frontend app registration (SPA)**
   - Platform: Single-page application
   - Redirect URIs: local + production frontend URLs
   - API permissions: `api://<backend-client-id>/access_as_user`

2. **Backend app registration (Web/API)**
   - Expose an API: `api://<backend-client-id>` with scope `access_as_user`
   - API permissions: Power BI delegated permissions (admin consent)
   - Client secret (local dev) or federated credential (production)

3. **User-assigned managed identity (UAMI)** — production only
   - Attached to MCP service runtime (e.g., Azure Container Apps)
   - Federated with backend app registration for secretless OBO
   - Audience: `api://AzureADTokenExchange`

---

## Cloud Deployment

| Service | Runtime | Command |
|---------|---------|---------|
| Backend (Copilot SDK) | Any compute | `python -m uvicorn backend_gh.main:app --host 0.0.0.0 --port 8000` |
| Backend (MAF) | Azure AI Foundry / ACA | `python -m uvicorn backend_maf.main:app --host 0.0.0.0 --port 8000` |
| MCP Server | Azure Container Apps | `python mcp_server_obo/server.py` |
| Frontend | Static hosting | Serve `frontend/` directory |

### MCP Service (Production) Environment

```env
ENVIRONMENT=production
AZURE_CLIENT_ID=<backend-app-client-id>
AZURE_TENANT_ID=<tenant-id>
UAMI_CLIENT_ID=<uami-client-id>
OBO_CLIENT_SECRET=
FABRIC_WORKSPACE_ID=<workspace-id>
FABRIC_DATASET_ID=<dataset-id>
OBO_API_CLIENT_ID=<backend-app-client-id>
OBO_REQUIRED_SCOPE=access_as_user
```

### Federated Credential Checklist

- [ ] Federated credential on backend app points to UAMI attached to MCP service
- [ ] Audience is exactly `api://AzureADTokenExchange`
- [ ] `UAMI_CLIENT_ID` in MCP env matches attached UAMI
- [ ] `ENVIRONMENT=production` and `OBO_CLIENT_SECRET` is empty

---

## Troubleshooting

| Problem | Check |
|---------|-------|
| OBO exchange failed | Federated credential exists on backend app, UAMI matches, audience is `api://AzureADTokenExchange` |
| Missing delegated scope | Frontend requests correct `FRONTEND_API_SCOPE`, backend exposes `access_as_user` |
| Invalid audience | `OBO_API_CLIENT_ID` = backend app client ID, frontend token audience = backend API |
| CORS blocked | `FRONTEND_ORIGIN` matches actual frontend origin exactly |
| Fabric query error | Dataset/workspace IDs correct, user has workspace access, Power BI permissions granted |

---

## Project Structure

```
├── backend_gh/          # Copilot SDK backend (PAT or BYOK)
│   ├── config.py        # Settings with COPILOT_AUTH_MODE toggle
│   ├── auth.py          # JWT validation
│   └── main.py          # FastAPI app
├── backend_maf/         # MAF + Foundry backend
│   ├── config.py        # Settings with Foundry endpoint
│   ├── auth.py          # JWT validation
│   └── main.py          # FastAPI app
├── mcp_server_obo/      # OBO MCP Server (shared by both backends)
│   ├── server.py        # MCP endpoint + tools
│   ├── obo_auth.py      # Token validation + OBO exchange
│   ├── fabric_client.py # Fabric DAX query execution
│   └── config.py        # MCP server settings
├── frontend/            # MSAL-authenticated SPA
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── auth_common.py       # Shared JWKS fetching
└── requirements.txt
```

---

## Key Design Decisions

- **Fail-closed auth:** Missing or invalid token → request rejected. No fallback to service account.
- **Confused-deputy guard:** Only the configured MCP server receives the user's bearer token.
- **Tokens in headers, not arguments:** OBO token flows via HTTP headers, never as tool arguments visible to the model.
- **Per-request httpx client (MAF):** Each request creates its own `MCPStreamableHTTPTool` with a custom `httpx.AsyncClient` that carries the user's `Authorization` header as a default. This avoids `ContextVar` propagation issues across the MCP transport's internal async tasks — `header_provider` sets headers via a `ContextVar`, but the transport spawns separate tasks where that var is empty.
- **Same API contract:** Both backends expose identical routes — frontend is backend-agnostic.
- **Isolated auth paths:** Foundry/Copilot credential (LLM inference) is completely separate from user OBO token (data access).
