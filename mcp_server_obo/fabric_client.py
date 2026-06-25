import httpx
import logging

from .config import FABRIC_DATASET_ID, FABRIC_WORKSPACE_ID

POWER_BI_BASE = f"https://api.powerbi.com/v1.0/myorg/groups/{FABRIC_WORKSPACE_ID}"
logger = logging.getLogger(__name__)


def _raise_for_status_with_details(resp: httpx.Response, operation: str) -> None:
    """Raise with a helpful log line that includes request ID and error details."""
    if resp.is_success:
        return

    request_id = resp.headers.get("requestid")
    pbi_error = resp.headers.get("x-powerbi-error-info")
    body_preview = (resp.text or "")[:1500]
    logger.error(
        "%s failed: status=%s requestid=%s powerbi_error=%s body=%s",
        operation,
        resp.status_code,
        request_id,
        pbi_error,
        body_preview,
    )
    resp.raise_for_status()


async def get_schema(token: str) -> dict:
    """Fetch tables, columns, and measures from the semantic model via INFO.VIEW.* DAX functions."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{POWER_BI_BASE}/datasets/{FABRIC_DATASET_ID}/executeQueries"

    async with httpx.AsyncClient(timeout=30.0) as client:
        tables_resp = await client.post(
            url,
            headers=headers,
            json={
                "queries": [
                    {
                        "query": (
                            "EVALUATE SELECTCOLUMNS("
                            "FILTER(INFO.VIEW.TABLES(), [IsHidden] = FALSE), "
                            "\"Name\", [Name])"
                        )
                    }
                ],
                "serializerSettings": {"includeNulls": True},
            },
        )
        _raise_for_status_with_details(tables_resp, "get_schema.tables")
        table_rows = tables_resp.json()["results"][0]["tables"][0].get("rows", [])

        columns_resp = await client.post(
            url,
            headers=headers,
            json={
                "queries": [
                    {
                        "query": (
                            "EVALUATE SELECTCOLUMNS("
                            "FILTER(INFO.VIEW.COLUMNS(), [IsHidden] = FALSE), "
                            "\"Table\", [Table], "
                            "\"Column\", [Name], "
                            "\"DataType\", [DataType])"
                        )
                    }
                ],
                "serializerSettings": {"includeNulls": True},
            },
        )
        _raise_for_status_with_details(columns_resp, "get_schema.columns")
        column_rows = columns_resp.json()["results"][0]["tables"][0].get("rows", [])

        measures_resp = await client.post(
            url,
            headers=headers,
            json={
                "queries": [
                    {
                        "query": (
                            "EVALUATE SELECTCOLUMNS("
                            "INFO.VIEW.MEASURES(), "
                            "\"Table\", [Table], "
                            "\"Measure\", [Name], "
                            "\"Expression\", [Expression])"
                        )
                    }
                ],
                "serializerSettings": {"includeNulls": True},
            },
        )
        _raise_for_status_with_details(measures_resp, "get_schema.measures")
        measure_rows = measures_resp.json()["results"][0]["tables"][0].get("rows", [])

    visible_tables = {row.get("[Name]", "") for row in table_rows}

    columns_by_table: dict[str, list] = {}
    for row in column_rows:
        table_name = row.get("[Table]", "")
        col_name = row.get("[Column]", "")
        data_type = row.get("[DataType]", "")
        if table_name in visible_tables and col_name:
            columns_by_table.setdefault(table_name, []).append(
                {"name": col_name, "dataType": data_type}
            )

    measures_by_table: dict[str, list] = {}
    for row in measure_rows:
        table_name = row.get("[Table]", "")
        measure_name = row.get("[Measure]", "")
        expression = row.get("[Expression]", "")
        if table_name in visible_tables and measure_name:
            measures_by_table.setdefault(table_name, []).append(
                {"name": measure_name, "expression": expression}
            )

    schema: dict = {"tables": []}
    for table_name in visible_tables:
        if not table_name:
            continue
        entry: dict = {"name": table_name}
        if table_name in columns_by_table:
            entry["columns"] = columns_by_table[table_name]
        if table_name in measures_by_table:
            entry["measures"] = measures_by_table[table_name]
        schema["tables"].append(entry)

    return schema


async def execute_dax(token: str, dax_query: str) -> list[dict]:
    """Execute a DAX query and return result rows."""
    url = f"{POWER_BI_BASE}/datasets/{FABRIC_DATASET_ID}/executeQueries"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "queries": [{"query": dax_query}],
        "serializerSettings": {"includeNulls": True},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        _raise_for_status_with_details(resp, "execute_dax")
        data = resp.json()

    return data["results"][0]["tables"][0].get("rows", [])
