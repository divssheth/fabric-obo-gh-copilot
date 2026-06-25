import asyncio
from contextlib import asynccontextmanager
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from copilot import CopilotClient
from copilot.session import PermissionHandler
from copilot.session_events import AssistantMessageData

from .auth import validate_token
from .config import settings

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

_client: CopilotClient | None = None

SYSTEM_MESSAGE = (
    "You are a data analyst assistant with access to a Fabric semantic model via DAX.\n\n"
    "Workflow:\n"
    "1. Call get_semantic_model_schema to discover available tables and columns.\n"
    "2. Write a DAX EVALUATE query that answers the user's question using only tables/columns from the schema.\n"
    "3. Call execute_dax_query with your DAX query string.\n"
    "4. Summarize the results clearly for the user.\n\n"
    "Rules:\n"
    "- Always start with get_semantic_model_schema so you know what data is available.\n"
    "- Use only EVALUATE statements (not SELECT). Wrap expressions in SUMMARIZE, FILTER, TOPN, etc.\n"
    "- If execute_dax_query returns an error, fix the DAX and retry once.\n"
    "- Never fabricate data; only report what the query returns."
)


def _build_mcp_servers_config(user_token: str | None) -> dict:
    """Build MCP server config with confused-deputy guard.

    We only attach Authorization to the configured OBO MCP server.
    """
    if not settings.obo_mcp_server_name or not settings.obo_mcp_server_url:
        raise HTTPException(status_code=500, detail="OBO MCP server name/url is not configured")

    server_entry = {
        "type": "http",
        "url": settings.obo_mcp_server_url,
        "tools": ["*"],
    }

    # Confused-deputy guard: only this server gets the user bearer token.
    if user_token:
        server_entry["headers"] = {"Authorization": f"Bearer {user_token}"}

    return {settings.obo_mcp_server_name: server_entry}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client
    _client = CopilotClient(github_token=settings.github_token)
    await _client.start()
    logger.info("CopilotClient started")
    yield
    await _client.stop()
    logger.info("CopilotClient stopped")


app = FastAPI(title="Fabric OBO Chat (Copilot SDK)", lifespan=lifespan)

allowed_origins = {
    settings.frontend_origin,
    "http://localhost:5500",
    "http://127.0.0.1:5500",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


class ClientConfig(BaseModel):
    msalClientId: str
    authority: str
    redirectUri: str
    apiScope: str
    backendBaseUrl: str


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/client-config", response_model=ClientConfig)
async def client_config():
    """Return safe public MSAL config for the frontend to bootstrap MSAL.

    Only safe, non-secret values are exposed here. Never add credentials,
    tokens, secrets, or internal routing info to this endpoint.
    """
    if not settings.frontend_msal_client_id or not settings.frontend_msal_authority:
        raise HTTPException(
            status_code=503,
            detail="Frontend MSAL config is not configured on this server.",
        )
    return ClientConfig(
        msalClientId=settings.frontend_msal_client_id,
        authority=settings.frontend_msal_authority,
        redirectUri=settings.frontend_msal_redirect_uri,
        apiScope=settings.frontend_api_scope,
        backendBaseUrl=settings.frontend_backend_url,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    auth_header = request.headers.get("authorization", "")
    user_token: str | None = None
    if auth_header.startswith("Bearer "):
        user_token = auth_header[7:]
        await validate_token(user_token)
    elif not settings.allow_anonymous_fallback:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    if _client is None:
        raise HTTPException(status_code=503, detail="CopilotClient not initialized")

    mcp_servers = _build_mcp_servers_config(user_token)

    session = await _client.create_session(
        on_permission_request=PermissionHandler.approve_all,
        system_message={"content": SYSTEM_MESSAGE},
        mcp_servers=mcp_servers,
    )

    try:
        reply = await session.send_and_wait(body.message)

        content = ""
        if reply and isinstance(reply.data, AssistantMessageData):
            content = reply.data.content or ""

        if not content:
            content = "No response from the assistant."

        return ChatResponse(reply=content)
    finally:
        await session.disconnect()
