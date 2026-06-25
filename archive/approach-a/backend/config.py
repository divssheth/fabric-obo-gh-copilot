from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    # Azure App Registration (Backend)
    azure_client_id: str
    azure_client_secret: str
    azure_tenant_id: str

    # Fabric / Power BI
    fabric_workspace_id: str
    fabric_dataset_id: str

    # Azure AI Foundry
    foundry_project_endpoint: str
    foundry_model: str = "gpt-4o-mini"

    # MCP Server
    mcp_server_url: str = "http://localhost:8001/mcp"

    # Frontend (for CORS)
    frontend_origin: str = "http://localhost:5500"

    model_config = ConfigDict(env_file=".env", extra="ignore")


settings = Settings()
