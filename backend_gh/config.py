from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Azure App Registration (Backend)
    azure_client_id: str
    azure_tenant_id: str

    # Fabric / Power BI
    fabric_workspace_id: str
    fabric_dataset_id: str

    # GitHub Copilot
    github_token: str = ""

    # Copilot auth mode: "pat" (GitHub PAT) or "byok" (Azure AI Foundry)
    copilot_auth_mode: str = "pat"

    # BYOK settings (only required when copilot_auth_mode=byok)
    # Uses Entra ID (DefaultAzureCredential) — no API key needed.
    # Local: az login | Production: Managed Identity
    byok_foundry_endpoint: str = ""
    byok_foundry_model: str = ""

    # OBO MCP Server routing (confused-deputy guard)
    obo_mcp_server_name: str = "fabric-obo"
    obo_mcp_server_url: str = "http://localhost:8002/mcp"

    # Auth mode for Approach B runtime. Current supported value:
    # - user_delegated: require bearer token and user-scoped OBO flow.
    auth_mode: str = "user_delegated"

    # Frontend (for CORS)
    frontend_origin: str = "http://localhost:5500"

    # Public frontend MSAL config (safe to expose via /client-config, no secrets)
    frontend_msal_client_id: str = ""
    frontend_msal_authority: str = ""
    frontend_msal_redirect_uri: str = "http://localhost:5500/frontend/index.html"
    frontend_api_scope: str = ""
    frontend_backend_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
