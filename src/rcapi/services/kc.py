import httpx
from fastapi import Request, HTTPException, Header
import logging
import threading
from typing import Optional
from rcapi.config.app_config import initialize_dirs
from jose import jwt
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
        return decoded.get("roles")
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
        return None if _token == "null" else _token
    else:
        return None
    #    raise HTTPException(status_code=401, detail="Invalid or missing Authorization header")

