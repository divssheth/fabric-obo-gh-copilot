import logging
from jose import jwt, JWTError
from fastapi import HTTPException, status

from auth_common import get_jwks
from .config import settings

logger = logging.getLogger(__name__)


async def validate_token(token: str) -> dict:
    """Validate the incoming JWT from the frontend and return claims."""
    jwks = await get_jwks(settings.azure_tenant_id)

    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token header",
        )

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
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            options={"verify_aud": False, "verify_iss": False},
        )

        token_aud = payload.get("aud", "")
        valid_audiences = {f"api://{settings.azure_client_id}", settings.azure_client_id}
        if token_aud not in valid_audiences:
            raise JWTError(f"Invalid audience: {token_aud}")

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
