import httpx
import msal
from jose import JWTError, jwt

from .config import (
    AZURE_CLIENT_ID,
    AZURE_CLIENT_SECRET,
    AZURE_TENANT_ID,
    OBO_API_CLIENT_ID,
    OBO_REQUIRED_SCOPE,
)


class AuthError(Exception):
    pass


_msal_app = msal.ConfidentialClientApplication(
    client_id=AZURE_CLIENT_ID,
    client_credential=AZURE_CLIENT_SECRET,
    authority=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}",
)

_jwks_cache: dict | None = None


async def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    openid_config_url = (
        f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
        "/v2.0/.well-known/openid-configuration"
    )
    async with httpx.AsyncClient() as client:
        config_resp = await client.get(openid_config_url)
        config_resp.raise_for_status()
        jwks_uri = config_resp.json()["jwks_uri"]

        keys_resp = await client.get(jwks_uri)
        keys_resp.raise_for_status()
        _jwks_cache = keys_resp.json()

    return _jwks_cache


async def validate_user_token(token: str) -> dict:
    jwks = await _get_jwks()

    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise AuthError(f"Invalid token header: {e}")

    rsa_key = None
    for key in jwks.get("keys", []):
        if key.get("kid") == unverified_header.get("kid"):
            rsa_key = key
            break

    if not rsa_key:
        raise AuthError("Unable to find signing key")

    try:
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            options={"verify_aud": False, "verify_iss": False},
        )

        token_aud = payload.get("aud", "")
        valid_audiences = {f"api://{OBO_API_CLIENT_ID}", OBO_API_CLIENT_ID}
        if token_aud not in valid_audiences:
            raise AuthError(f"Invalid audience: {token_aud}")

        token_iss = payload.get("iss", "")
        valid_issuers = {
            f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/v2.0",
            f"https://sts.windows.net/{AZURE_TENANT_ID}/",
        }
        if token_iss not in valid_issuers:
            raise AuthError(f"Invalid issuer: {token_iss}")

        scopes = set((payload.get("scp") or "").split())
        if OBO_REQUIRED_SCOPE and OBO_REQUIRED_SCOPE not in scopes:
            raise AuthError(
                f"Missing required delegated scope: {OBO_REQUIRED_SCOPE}"
            )

    except JWTError as e:
        raise AuthError(f"Token validation failed: {e}")

    return payload


def _extract_bearer_token(authorization_header: str) -> str:
    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise AuthError("Missing or invalid Authorization header")
    return authorization_header[7:]


def _get_fabric_token_via_obo(user_token: str) -> str:
    result = _msal_app.acquire_token_on_behalf_of(
        user_assertion=user_token,
        scopes=["https://analysis.windows.net/powerbi/api/.default"],
    )
    if "access_token" not in result:
        error = result.get("error_description", result.get("error", "Unknown error"))
        raise AuthError(f"OBO exchange failed: {error}")
    return result["access_token"]


async def resolve_fabric_token(
    authorization_header: str | None,
    auth_mode: str = "user_delegated",
) -> tuple[str, str]:
    """Resolve Fabric token.

    Returns (token, mode) where mode is one of:
    - user_obo
    """
    if auth_mode != "user_delegated":
        raise AuthError(
            f"Unsupported AUTH_MODE '{auth_mode}'. Expected 'user_delegated'."
        )

    if not authorization_header:
        raise AuthError("Missing or invalid Authorization header")

    user_token = _extract_bearer_token(authorization_header)
    await validate_user_token(user_token)
    fabric_token = _get_fabric_token_via_obo(user_token)
    return fabric_token, "user_obo"
