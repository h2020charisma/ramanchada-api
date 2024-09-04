from functools import wraps
from fastapi import Request, HTTPException
import logging
import requests

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


class AuthenticatedRequest:
    def __init__(self, get_token):
        """
        Initialize the AuthenticatedRequest context manager.

        Args:
            get_token (callable): A function to retrieve the current token.

        with AuthenticatedRequest(get_token):
            requests.get()
            ...
        """
        self.get_token = get_token
        self.original_post = None

    def __enter__(self):
        # Save the original requests.post method
        self.original_post = requests.post
        # Override requests.post with our modified version
        requests.post = self.modified_post

    def __exit__(self, exc_type, exc_value, traceback):
        # Restore the original requests.post method
        requests.post = self.original_post

   
    def modified_post(self, url, **kwargs):
        # Retrieve the current token
        token = self.get_token()
        # Ensure the headers dictionary exists
        headers = kwargs.setdefault('headers', {})
        # Add the Authorization header, without overwriting other headers
        if 'Authorization' not in headers:
            headers['Authorization'] = f'Bearer {token}'
        # Make the request with the modified headers
        return self.original_post(url, **kwargs)    