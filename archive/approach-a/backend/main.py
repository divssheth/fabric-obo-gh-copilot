from contextlib import asynccontextmanager
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

from .auth import validate_token, get_obo_token
from .config import settings

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

_agent: Agent | None = None
_credential: AzureCliCredential | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent, _credential

    _credential = AzureCliCredential()
    client = FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint,
        model=settings.foundry_model,
        credential=_credential,
    )

    mcp_tool = MCPStreamableHTTPTool(
        name="fabric-query",
        description="Tools for querying the Fabric semantic model. Includes get_semantic_model_schema and execute_dax_query.",
        url=settings.mcp_server_url,
        additional_tool_argument_names=["fabric_token"],
    )

    async with Agent(
        client=client,
        name="FabricAnalyst",
        instructions=(
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
        ),
        tools=[mcp_tool],
    ) as agent:
        _agent = agent
        logger.info("Backend agent initialized")
        yield

    if _credential:
        await _credential.close()


app = FastAPI(title="Fabric OBO Chat", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    user_token = auth_header[7:]
    await validate_token(user_token)

    fabric_token = get_obo_token(user_token)

    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    result = await _agent.run(
        body.message,
        function_invocation_kwargs={"fabric_token": fabric_token},
    )

    return ChatResponse(reply=result.text)
