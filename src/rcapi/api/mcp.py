# src/rcapi/api/mcp.py
from fastapi import APIRouter, Request
from fastapi.openapi.utils import get_openapi
from urllib.parse import urljoin

router = APIRouter()


def _ensure_manifest(app, base_url: str):
    """Generate and cache the MCP manifest + OpenAPI schema once per app."""
    if not hasattr(app.state, "mcp_openapi"):
        openapi_schema = get_openapi(
            title=app.title or "ramanchada-api",
            version=getattr(app, "version", "1.0.0"),
            description=getattr(app, "description", ""),
            routes=app.routes,
        )

        endpoints = list(openapi_schema.get("paths", {}).keys())
        app.state.mcp_openapi = openapi_schema
        app.state.mcp_manifest = {
            "version": "1.0",
            "name": app.title or "ramanchada-api",
            "description": getattr(app, "description", ""),
            "base_url": base_url.rstrip("/") + "/",
            "openapi": openapi_schema,
            "endpoints": endpoints,
        }


@router.get("/.well-known/mcp/manifest.json", include_in_schema=False, response_model=None)
async def mcp_manifest(request: Request):
    """Return MCP manifest derived from the OpenAPI schema."""
    app = request.app
    base_url = str(request.base_url)
    _ensure_manifest(app, base_url)
    return app.state.mcp_manifest


@router.get("/.well-known/mcp/tools.json", include_in_schema=False, response_model=None)
async def mcp_tools(request: Request):
    """Return list of callable tools based on OpenAPI paths."""
    app = request.app
    base_url = str(request.base_url)
    _ensure_manifest(app, base_url)
    openapi_schema = app.state.mcp_openapi

    tools = []
    for path, methods in openapi_schema.get("paths", {}).items():
        for method, spec in methods.items():
            # skip docs and MCP endpoints
            if path.startswith("/docs") or path.startswith("/openapi") or path.startswith("/.well-known"):
                continue
            tools.append({
                "name": f"{method.upper()} {path}",
                "description": spec.get("summary") or spec.get("description") or "",
                "method": method.upper(),
                "path": path,
                "url": urljoin(base_url, path.lstrip("/")),
                "parameters": spec.get("parameters", []),
                "requestBody": spec.get("requestBody", {}),
                "responses": spec.get("responses", {}),
            })

    return {"version": "1.0", "base_url": base_url.rstrip("/") + "/", "tools": tools}
