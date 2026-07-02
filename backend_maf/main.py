import logging
import uuid
from dataclasses import dataclass, field

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent_framework import Agent, MCPStreamableHTTPTool, Message
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from .auth import validate_token
from .config import settings

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

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


@dataclass
class ConversationSession:
    """Tracks conversation history for multi-turn interactions."""
    messages: list = field(default_factory=list)


# In-memory session store: session_id -> ConversationSession
_sessions: dict[str, ConversationSession] = {}


def _build_mcp_tool(user_token: str) -> MCPStreamableHTTPTool:
    """Build MCPStreamableHTTPTool with header_provider for OBO token forwarding."""
    if not settings.obo_mcp_server_url:
        raise HTTPException(status_code=500, detail="OBO MCP server URL is not configured")

    return MCPStreamableHTTPTool(
        name=settings.obo_mcp_server_name,
        url=settings.obo_mcp_server_url,
        header_provider=lambda kwargs: {"Authorization": f"Bearer {kwargs['user_token']}"},
        approval_mode="never_require",
    )


app = FastAPI(title="Fabric OBO Chat (MAF)")

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
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@app.get("/client-config", response_model=ClientConfig)
async def client_config():
    """Return safe public MSAL config for the frontend to bootstrap MSAL."""
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
    if settings.auth_mode != "user_delegated":
        raise HTTPException(
            status_code=500,
            detail=f"Unsupported AUTH_MODE '{settings.auth_mode}'. Expected 'user_delegated'.",
        )

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    user_token = auth_header[7:]
    await validate_token(user_token)

    # Get or create session
    session_id = body.session_id
    if session_id and session_id in _sessions:
        conv = _sessions[session_id]
    else:
        session_id = str(uuid.uuid4())
        conv = ConversationSession()
        _sessions[session_id] = conv
        logger.info("Created new session %s", session_id)

    # Add user message to history
    conv.messages.append(Message("user", [body.message]))

    mcp_tool = _build_mcp_tool(user_token)

    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        credential=credential,
        project_endpoint=settings.foundry_project_endpoint,
        model=settings.foundry_model,
    )

    async with Agent(
        client=client,
        name="FabricAnalyst",
        instructions=SYSTEM_MESSAGE,
        tools=mcp_tool,
    ) as agent:
        result = await agent.run(
            conv.messages,
            function_invocation_kwargs={"user_token": user_token},
        )

    content = result.text if result else ""
    if not content:
        content = "No response from the assistant."

    # Add assistant response to history
    conv.messages.append(Message("assistant", [content]))

    return ChatResponse(reply=content, session_id=session_id)
