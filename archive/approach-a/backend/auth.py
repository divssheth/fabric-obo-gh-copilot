import httpx
import logging
import msal
from jose import jwt, JWTError
from fastapi import HTTPException, status

from .config import settings

logger = logging.getLogger(__name__)

# MSAL confidential client for OBO flow
_msal_app = msal.ConfidentialClientApplication(
    client_id=settings.azure_client_id,
    client_credential=settings.azure_client_secret,
    authority=f"https://login.microsoftonline.com/{settings.azure_tenant_id}",
)

# Cached JWKS keys
_jwks_cache: dict | None = None


async def _get_jwks() -> dict:
    """Fetch and cache the Entra ID JWKS signing keys."""
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    openid_config_url = (
        f"https://login.microsoftonline.com/{settings.azure_tenant_id}"
        "/v2.0/.well-known/openid-configuration"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(openid_config_url)
        resp.raise_for_status()
        jwks_uri = resp.json()["jwks_uri"]

        resp = await client.get(jwks_uri)
        resp.raise_for_status()
        _jwks_cache = resp.json()

    return _jwks_cache


async def validate_token(token: str) -> dict:
    """Validate the incoming JWT from the frontend and return claims."""
    jwks = await _get_jwks()

    try:
        # Decode without verification first to get the header
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token header",
        )

    # Find the signing key
    rsa_key = None
    for key in jwks.get("keys", []):
        if key["kid"] == unverified_header.get("kid"):
            rsa_key = key
            break

    if not rsa_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to find appropriate signing key",
        )

    try:
        # Decode without audience/issuer check first, then validate manually
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            options={"verify_aud": False, "verify_iss": False},
        )

        # Validate audience manually (python-jose doesn't accept a list)
        token_aud = payload.get("aud", "")
        valid_audiences = {f"api://{settings.azure_client_id}", settings.azure_client_id}
        if token_aud not in valid_audiences:
            raise JWTError(f"Invalid audience: {token_aud}")

        # Validate issuer manually
        token_iss = payload.get("iss", "")
        valid_issuers = {
            f"https://login.microsoftonline.com/{settings.azure_tenant_id}/v2.0",
            f"https://sts.windows.net/{settings.azure_tenant_id}/",
        }
        if token_iss not in valid_issuers:
            raise JWTError(f"Invalid issuer: {token_iss}")

    except JWTError as e:
        logger.error(f"Token validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {e}",
        )

    return payload


def get_obo_token(user_token: str) -> str:
    """Exchange the user token for a Fabric-scoped token via OBO flow."""
    result = _msal_app.acquire_token_on_behalf_of(
        user_assertion=user_token,
        scopes=["https://analysis.windows.net/powerbi/api/.default"],
    )

    if "access_token" not in result:
        error = result.get("error_description", result.get("error", "Unknown error"))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OBO token exchange failed: {error}",
        )

    return result["access_token"]
