import httpx
from fastapi import Request, HTTPException, Header
import logging
import threading
from typing import Optional
from rcapi.config.app_config import initialize_dirs
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
from functools import lru_cache
import traceback


# Thread-local storage for API key
thread_local = threading.local()

config, UPLOAD_DIR, NEXUS_DI, TEMPLATE_DIR = initialize_dirs()

logger = logging.getLogger(__name__)


@lru_cache()
def get_jwks() -> dict:
    openid_config = httpx.get(config.KEYCLOAK.OPENID_CONFIG_URI).json()
    return httpx.get(openid_config["jwks_uri"]).json()


def decode_token(token: str, key: str | dict) -> dict:
    return jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=config.KEYCLOAK.JWT_AUDIENCE,
        issuer=config.KEYCLOAK.JWT_ISSUER,
        options={
            "require_iat": True,
            "require_exp": True,
            "require_iss": True,
            "require_jti": True,
        },
    )


def get_roles_from_token(token: str, key: str | dict | None = None) -> list[str]:
    try:
        if not key:
            key = get_jwks()
        decoded = decode_token(token, key)
        roles = decoded.get("roles")
        # Always a list: callers append "public" to it, and a realm without the
        # roles protocol mapper would otherwise return None and crash them.
        return roles if isinstance(roles, list) else []
    except Exception:
        traceback.print_exc()
        return []


# Dependency to extract Bearer token
def get_token(authorization: Optional[str] = Header(None)):
    if authorization is None:
        return None
    elif authorization.startswith("Bearer "):
        # Extract the token (API key)
        _token = authorization.split(" ")[1]
        if _token == "null":
            return None
        return _validated(_token)
    else:
        return None


def _validated(token: str) -> str:
    """Reject an expired or malformed token with 401 instead of passing it on.

    Callers treat "a token is present" as "the user is authenticated": private
    collections are kept in the candidate set (drop_private is `token is None`)
    and the token is forwarded to Solr. An expired session therefore used to
    look like empty data -- Solr refused the stale token, or the roles lookup
    swallowed the expiry and answered "no roles" -- with nothing anywhere
    saying the session had ended. A 401 is what clients can actually act on.

    No token at all stays anonymous: public data must work signed out.
    """
    try:
        key = get_jwks()
    except Exception:
        # Keycloak unreachable: don't make every request depend on it. Pass the
        # token through unvalidated, as before, and let Solr decide.
        logger.warning("JWKS unavailable, skipping token validation",
                       exc_info=True)
        return token

    try:
        decode_token(token, key)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Session expired. Please sign in again.")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token.")
    return token

