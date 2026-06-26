from azure.identity import ManagedIdentityCredential, OnBehalfOfCredential
from jose import JWTError, jwt

from auth_common import get_jwks
from .config import settings


class AuthError(Exception):
    pass


def _close_credential(credential: object | None) -> None:
    if credential is None:
        return
    close = getattr(credential, "close", None)
    if callable(close):
        close()


def _build_obo_credential(
    user_token: str,
) -> tuple[OnBehalfOfCredential, ManagedIdentityCredential | None]:
    # Local development can use a client secret fallback.
    if settings.environment.lower() == "local" and settings.obo_client_secret:
        return (
            OnBehalfOfCredential(
                tenant_id=settings.azure_tenant_id,
                client_id=settings.azure_client_id,
                client_secret=settings.obo_client_secret,
                user_assertion=user_token,
            ),
            None,
        )

    if not settings.uami_client_id:
        raise AuthError(
            "UAMI_CLIENT_ID is required for federated OBO outside local-secret mode"
        )

    mi_credential = ManagedIdentityCredential(client_id=settings.uami_client_id)

    def _client_assertion_func() -> str:
        token = mi_credential.get_token("api://AzureADTokenExchange/.default")
        return token.token

    obo_credential = OnBehalfOfCredential(
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id,
        user_assertion=user_token,
        client_assertion_func=_client_assertion_func,
    )
    return obo_credential, mi_credential


async def validate_user_token(token: str) -> dict:
    jwks = await get_jwks(settings.azure_tenant_id)

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
        obo_api_client_id = settings.obo_api_client_id or settings.azure_client_id
        valid_audiences = {f"api://{obo_api_client_id}", obo_api_client_id}
        if token_aud not in valid_audiences:
            raise AuthError(f"Invalid audience: {token_aud}")

        token_iss = payload.get("iss", "")
        valid_issuers = {
            f"https://login.microsoftonline.com/{settings.azure_tenant_id}/v2.0",
            f"https://sts.windows.net/{settings.azure_tenant_id}/",
        }
        if token_iss not in valid_issuers:
            raise AuthError(f"Invalid issuer: {token_iss}")

        scopes = set((payload.get("scp") or "").split())
        if settings.obo_required_scope and settings.obo_required_scope not in scopes:
            raise AuthError(
                f"Missing required delegated scope: {settings.obo_required_scope}"
            )

    except JWTError as e:
        raise AuthError(f"Token validation failed: {e}")

    return payload


def _extract_bearer_token(authorization_header: str) -> str:
    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise AuthError("Missing or invalid Authorization header")
    return authorization_header[7:]


def _get_fabric_token_via_obo(user_token: str) -> str:
    obo_credential: OnBehalfOfCredential | None = None
    mi_credential: ManagedIdentityCredential | None = None
    try:
        obo_credential, mi_credential = _build_obo_credential(user_token)
        access_token = obo_credential.get_token(
            "https://analysis.windows.net/powerbi/api/.default"
        )
        return access_token.token
    except Exception as e:
        raise AuthError(f"OBO exchange failed: {e}")
    finally:
        _close_credential(obo_credential)
        _close_credential(mi_credential)


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
