from functools import wraps
from fastapi import Request, HTTPException, Header
import logging
import threading
import h5pyd
import httpx
from contextlib import contextmanager, asynccontextmanager
from typing import Optional

# Thread-local storage for API key
thread_local = threading.local()

logger = logging.getLogger(__name__)

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


# Context manager to temporarily patch h5pyd.File to inject the api_key
@contextmanager
def inject_api_key_h5pyd(api_key):
    """
    Smth is wrong with  this
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
        if thread_local.api_key is not None:
            kwargs['api_key'] = thread_local.api_key
        return original_h5pyd_file( *args, **kwargs)

    def patched_h5pyd_folder(*args, **kwargs):
        # Inject the thread-local API key into the h5pyd.Folder call
        if thread_local.api_key is not None:
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

@asynccontextmanager
async def inject_api_key_into_httpx(api_key: str):
    """
    Smth is wrong with  this
    Thread-safe async context manager to inject the API key into the thread-local `httpx.AsyncClient`
    used for making HTTP requests.

    Each thread will have its own independent `httpx.AsyncClient`, ensuring that the
    `Authorization: Bearer <api_key>` header is correctly applied without affecting other threads.

    Parameters:
    -----------
    api_key : str
        The API key to inject into the requests headers.

    Yields:
    -------
    client : httpx.AsyncClient
        The thread-local `AsyncClient` object, with the Authorization header pre-configured.

    Example:
    --------
    >>> async with inject_api_key_into_requests(api_key="your_api_key") as client:
    >>>     response = await client.get("https://example.com/data")
    >>>     response = await client.post("https://example.com/data", json={"key": "value"})
    >>>     # The Authorization header will automatically be included in both requests.
    """
    if not hasattr(thread_local, "client"):
        thread_local.client = httpx.AsyncClient()

    # Add Authorization header to the client for this thread
    thread_local.client.headers.update({"Authorization": f"Bearer {api_key}"})

    try:
        yield thread_local.client  # Provide the client for this thread's context
    finally:
        # Optionally close the client if required
        await thread_local.client.aclose()
        del thread_local.client  # Clean up the client after use