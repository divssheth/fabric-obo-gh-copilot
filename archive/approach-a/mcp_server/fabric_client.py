import httpx
import os

WORKSPACE_ID = os.environ.get("FABRIC_WORKSPACE_ID", "")
DATASET_ID = os.environ.get("FABRIC_DATASET_ID", "")
POWER_BI_BASE = f"https://api.powerbi.com/v1.0/myorg/groups/{WORKSPACE_ID}"


async def get_schema(token: str) -> dict:
    """Fetch tables, columns, and measures from the semantic model via INFO.VIEW.* DAX functions."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{POWER_BI_BASE}/datasets/{DATASET_ID}/executeQueries"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get visible tables
        tables_resp = await client.post(url, headers=headers, json={
            "queries": [{"query": (
                "EVALUATE SELECTCOLUMNS("
                "FILTER(INFO.VIEW.TABLES(), [IsHidden] = FALSE), "
                "\"Name\", [Name])"
            )}],
            "serializerSettings": {"includeNulls": True},
        })
        tables_resp.raise_for_status()
        tables_data = tables_resp.json()
        table_rows = tables_data["results"][0]["tables"][0].get("rows", [])

        # Get visible columns
        columns_resp = await client.post(url, headers=headers, json={
            "queries": [{"query": (
                "EVALUATE SELECTCOLUMNS("
                "FILTER(INFO.VIEW.COLUMNS(), [IsHidden] = FALSE), "
                "\"Table\", [Table], "
                "\"Column\", [Name], "
                "\"DataType\", [DataType])"
            )}],
            "serializerSettings": {"includeNulls": True},
        })
        columns_resp.raise_for_status()
        columns_data = columns_resp.json()
        column_rows = columns_data["results"][0]["tables"][0].get("rows", [])

        # Get measures
        measures_resp = await client.post(url, headers=headers, json={
            "queries": [{"query": (
                "EVALUATE SELECTCOLUMNS("
                "INFO.VIEW.MEASURES(), "
                "\"Table\", [Table], "
                "\"Measure\", [Name], "
                "\"Expression\", [Expression])"
            )}],
            "serializerSettings": {"includeNulls": True},
        })
        measures_resp.raise_for_status()
        measures_data = measures_resp.json()
        measure_rows = measures_data["results"][0]["tables"][0].get("rows", [])

    # Build set of visible table names
    visible_tables = {row.get("[Name]", "") for row in table_rows}

    # Group columns by table
    columns_by_table: dict[str, list] = {}
    for row in column_rows:
        table_name = row.get("[Table]", "")
        col_name = row.get("[Column]", "")
        data_type = row.get("[DataType]", "")
        if table_name in visible_tables and col_name:
            columns_by_table.setdefault(table_name, []).append(
                {"name": col_name, "dataType": data_type}
            )

    # Group measures by table
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
    url = f"{POWER_BI_BASE}/datasets/{DATASET_ID}/executeQueries"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "queries": [{"query": dax_query}],
        "serializerSettings": {"includeNulls": True},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    rows = data["results"][0]["tables"][0].get("rows", [])
    return rows
