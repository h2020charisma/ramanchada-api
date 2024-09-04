from functools import wraps
from fastapi import Request, HTTPException
import logging

logger = logging.getLogger(__name__)

def get_bearer_token(authorization_header: str) -> str:
    if authorization_header is None:
        return None
    parts = authorization_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None

def pass_auth(func):
    """Decorator to extract and attach the Bearer token to the request."""
    @wraps(func)
    async def decorated(request: Request, *args, **kwargs):
        token = get_bearer_token(request.headers.get('Authorization'))
        if token:
            setattr(request.state, "api_key", token)
        else:
            logger.warning("No Bearer token found in the request")
        return await func(request, *args, **kwargs)
    
    return decorated
