from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Azure App Registration (Backend)
    azure_client_id: str
    azure_client_secret: str
    azure_tenant_id: str

    # Fabric / Power BI
    fabric_workspace_id: str
    fabric_dataset_id: str

    # GitHub Copilot
    github_token: str = ""

    # OBO MCP Server routing (confused-deputy guard)
    obo_mcp_server_name: str = "fabric-obo"
    obo_mcp_server_url: str = "http://localhost:8002/mcp"

    # If true, /chat allows requests without Authorization header and relies on
    # MCP-side agent identity fallback. If false, user auth header is required.
    allow_anonymous_fallback: bool = False

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
