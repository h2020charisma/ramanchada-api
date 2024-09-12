from functools import wraps
from fastapi import Request, HTTPException, Header
import logging
import threading
import h5pyd
import requests
from contextlib import contextmanager
from typing import Optional

# Thread-local storage for API key
thread_local = threading.local()

logger = logging.getLogger(__name__)

# Dependency to extract API key from Bearer token
def get_api_key(authorization: Optional[str] = Header(None)):
    if authorization is None:
        return None
    elif authorization.startswith("Bearer "):
        # Extract the token (API key)
        return authorization.split(" ")[1]
    else:
        return None
    #    raise HTTPException(status_code=401, detail="Invalid or missing Authorization header")

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
    

# Context manager to inject the API key into a thread-local session for all requests
@contextmanager
def inject_api_key_into_requests(api_key):
    """
    Thread-safe context manager to inject the API key into the thread-local `requests.Session`
    used for making HTTP requests.

    Each thread will have its own independent `requests.Session`, ensuring that the
    `Authorization: Bearer <api_key>` header is correctly applied without affecting other threads.

    Parameters:
    -----------
    api_key : str
        The API key to inject into the requests headers.

    Yields:
    -------
    session : requests.Session
        The thread-local session object, with the Authorization header pre-configured.

    Example:
    --------
    >>> with inject_api_key_into_requests(api_key="your_api_key") as session:
    >>>     response = session.get("https://example.com/data")
    >>>     response = session.post("https://example.com/data", json={"key": "value"})
    >>>     # The Authorization header will automatically be included in both requests.
    
    """
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()

    # Add Authorization header to the session for this thread
    thread_local.session.headers.update({"Authorization": f"Bearer {api_key}"})

    try:
        yield thread_local.session  # Provide the session for this thread's context
    finally:
        # Optional: Clean up if necessary (e.g., closing the session)
        pass
    

# Context manager to temporarily patch h5pyd.File to inject the api_key
@contextmanager
def inject_api_key_h5pyd(api_key):
    """
    Thread-safe context manager that injects the `api_key` into the `h5pyd.File` and `h5pyd.Folder`
    calls for the current thread.

    This context manager ensures that each thread uses its own `api_key` for the `h5pyd` calls,
    avoiding conflicts in multithreaded environments.
    
    Parameters:
    -----------
    api_key : str
        The API key to inject into the `h5pyd.File` and `h5pyd.Folder` calls.

    Yields:
    -------
    None
        Code inside the `with` block will have the `api_key` injected into relevant calls.
    
    Example:
    --------
    >>> with inject_api_key_h5pyd(api_key="your_api_key"):
    >>>     file = some_module.access_h5_file("example.h5", mode="r", retries=3)
    >>>     folder = some_module.access_h5_folder("/example/folder", mode="r", retries=3)
    >>>     # The API key will be injected into both the file and folder access calls.
    
    """
    # Store the API key in thread-local storage
    thread_local.api_key = api_key

    # Store the original methods
    original_h5pyd_file = h5pyd.File
    original_h5pyd_folder = h5pyd.Folder

    def patched_h5pyd_file( *args, **kwargs):
        # Inject the thread-local API key into the h5pyd.File call
        kwargs['api_key'] = thread_local.api_key
        return original_h5pyd_file( *args, **kwargs)

    def patched_h5pyd_folder(*args, **kwargs):
        # Inject the thread-local API key into the h5pyd.Folder call
        kwargs['api_key'] = thread_local.api_key
        return original_h5pyd_folder( *args, **kwargs)

    # Temporarily patch the h5pyd.File and h5pyd.Folder methods
    h5pyd.File = patched_h5pyd_file
    h5pyd.Folder = patched_h5pyd_folder

    try:
        yield  # Execute the code within the context block
    except Exception as e:
        print(f"Error: {e}")
        raise     
    finally:
        # Restore the original methods after the context ends
        h5pyd.File = original_h5pyd_file
        h5pyd.Folder = original_h5pyd_folder

