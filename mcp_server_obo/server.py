import json
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP, Context

if __package__ in (None, ""):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

from mcp_server_obo.fabric_client import get_schema, execute_dax
from mcp_server_obo.obo_auth import AuthError, resolve_fabric_token
from mcp_server_obo.config import AUTH_MODE

logging.basicConfig(level=logging.INFO)

mcp = FastMCP("fabric-semantic-model-obo", host="0.0.0.0", port=8002)


def _get_authorization_header(ctx: Context) -> str | None:
    """Read Authorization header from FastMCP request context if present."""
    try:
        request = ctx.request_context.request
        if request is None:
            return None

        headers = getattr(request, "headers", None)
        if headers is None:
            return None

        return headers.get("authorization")
    except Exception:
        return None


async def _resolve_request_fabric_token(ctx: Context) -> tuple[str, str]:
    auth_header = _get_authorization_header(ctx)
    return await resolve_fabric_token(auth_header, auth_mode=AUTH_MODE)


@mcp.tool()
async def get_semantic_model_schema(ctx: Context) -> str:
    """Retrieve the schema (tables and columns) of the Fabric semantic model."""
    try:
        fabric_token, mode = await _resolve_request_fabric_token(ctx)
    except AuthError as e:
        return f"Error: Unauthorized. {e}"
    except Exception as e:
        return f"Error: Authentication failure. {e}"

    try:
        schema = await get_schema(fabric_token)
    except Exception as e:
        return f"Error retrieving schema: {e}"

    if not schema.get("tables"):
        return "Error: Schema is empty or inaccessible."

    schema["authMode"] = mode
    return json.dumps(schema, indent=2)


@mcp.tool()
async def execute_dax_query(dax_query: str, ctx: Context) -> str:
    """Execute a DAX query against the Fabric semantic model and return rows as JSON."""
    if not dax_query.strip():
        return "Error: dax_query must not be empty."

    try:
        fabric_token, mode = await _resolve_request_fabric_token(ctx)
    except AuthError as e:
        return f"Error: Unauthorized. {e}"
    except Exception as e:
        return f"Error: Authentication failure. {e}"

    try:
        rows = await execute_dax(fabric_token, dax_query)
    except Exception as e:
        return f"Error executing DAX: {e}"

    if not rows:
        return "Query returned no results."

    return json.dumps({"authMode": mode, "rows": rows}, indent=2, default=str)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
