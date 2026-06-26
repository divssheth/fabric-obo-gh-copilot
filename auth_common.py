import httpx


_jwks_cache_by_tenant: dict[str, dict] = {}


async def get_jwks(tenant_id: str) -> dict:
    cached = _jwks_cache_by_tenant.get(tenant_id)
    if cached is not None:
        return cached

    openid_config_url = (
        f"https://login.microsoftonline.com/{tenant_id}"
        "/v2.0/.well-known/openid-configuration"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(openid_config_url)
        resp.raise_for_status()
        jwks_uri = resp.json()["jwks_uri"]

        resp = await client.get(jwks_uri)
        resp.raise_for_status()
        jwks = resp.json()

    _jwks_cache_by_tenant[tenant_id] = jwks
    return jwks