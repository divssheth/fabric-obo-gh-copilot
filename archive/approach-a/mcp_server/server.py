import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from mcp.server.fastmcp import FastMCP

# Support running as script or as module
if __name__ != "__main__":
    from .fabric_client import get_schema, execute_dax
else:
    sys.path.insert(0, os.path.dirname(__file__))
    from fabric_client import get_schema, execute_dax

mcp = FastMCP("fabric-semantic-model", host="0.0.0.0", port=8001)


@mcp.tool()
async def get_semantic_model_schema(fabric_token: str = "") -> str:
    """Retrieve the schema (tables and columns) of the Fabric semantic model. Returns JSON with table names and their columns."""
    if not fabric_token:
        return "Error: No authorization token provided."

    try:
        schema = await get_schema(fabric_token)
    except Exception as e:
        return f"Error retrieving schema: {e}"

    if not schema.get("tables"):
        return "Error: Schema is empty or inaccessible."

    return json.dumps(schema, indent=2)


@mcp.tool()
async def execute_dax_query(dax_query: str, fabric_token: str = "") -> str:
    """Execute a DAX query against the Fabric semantic model and return the result rows as JSON."""
    if not fabric_token:
        return "Error: No authorization token provided."

    if not dax_query.strip():
        return "Error: dax_query must not be empty."

    try:
        rows = await execute_dax(fabric_token, dax_query)
    except Exception as e:
        return f"Error executing DAX: {e}"

    if not rows:
        return "Query returned no results."

    return json.dumps(rows, indent=2, default=str)


# Hide fabric_token from advertised tool schemas so the LLM doesn't
# provide it (empty) and overwrite the runtime-injected value.
for _tool_name in ["get_semantic_model_schema", "execute_dax_query"]:
    _tool = mcp._tool_manager._tools[_tool_name]
    _tool.parameters["properties"].pop("fabric_token", None)
    if "required" in _tool.parameters:
        _tool.parameters["required"] = [
            r for r in _tool.parameters["required"] if r != "fabric_token"
        ]


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
