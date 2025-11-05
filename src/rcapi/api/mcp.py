# src/rcapi/api/mcp.py
from fastapi import APIRouter, Request, Depends
from fastapi.openapi.utils import get_openapi
from urllib.parse import urljoin
from rcapi.services.solr_query import SOLR_FIELDS, SOLR_COLLECTIONS
from rcapi.services.kc import get_token, get_roles_from_token

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
async def mcp_tools(request: Request, token: str = Depends(get_token)):
    """Return list of callable tools based on OpenAPI paths + query-specific info."""
    app = request.app
    base_url = str(request.base_url)
    _ensure_manifest(app, base_url)
    openapi_schema = app.state.mcp_openapi

    # Compute dynamic data sources
    if token:
        user_roles = get_roles_from_token(token)
    else:
        user_roles = []
    user_roles.append("public")
    accessible_collections = SOLR_COLLECTIONS.for_roles(user_roles)
    data_sources = [
        {"name": c.name, "description": c.description, "public": "public" in c.roles}
        for c in accessible_collections
    ]

    # Known Solr fields
    solr_fields = [{"name": f.name, "field": f.field} for f in SOLR_FIELDS]

    tools = []

    # Iterate OpenAPI paths
    for path, methods in openapi_schema.get("paths", {}).items():
        # skip docs and MCP endpoints
        if path.startswith("/docs") or path.startswith("/openapi") or path.startswith("/.well-known"):
            continue
        # just list /db paths
        if not path.startswith("/db/"):
            continue
        for method, spec in methods.items():
            tool = {
                "name": f"{method.upper()} {path}",
                "description": spec.get("summary") or spec.get("description") or "",
                "method": method.upper(),
                "path": path,
                "url": urljoin(base_url, path.lstrip("/")),
                "parameters": spec.get("parameters", []),
                "requestBody": spec.get("requestBody", {}),
                "responses": spec.get("responses", {}),
            }

            # Add query-specific info for /query
            if path.endswith("/query"):
                # GET filters.* parameters
                get_params = {f"filters.{f.field}": {"type": "string", "description": f"Filter by {f.name}"} for f in SOLR_FIELDS}
                tool["parameters"] = tool.get("parameters", []) + list(get_params.values())
                # POST filters object
                tool["requestBody"] = {
                    "description": "POST body for universal query",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "filters": {
                                        "type": "object",
                                        "properties": {f.field: {"type": "string"} for f in SOLR_FIELDS},
                                        "description": "Dynamic filters by Solr field",
                                        "default": {},
                                    },
                                    "q": {"type": "string", "default": "*"},
                                    "query_type": {"type": "string", "default": "text", "enum": ["metadata", "text", "knnquery"]},
                                    "q_reference": {"type": "string", "default": "*"},
                                    "q_provider": {"type": "string", "default": "*"},
                                    "q_method": {"type": "string", "default": "*"},
                                    "ann": {"type": "string", "default": None},
                                    "page": {"type": "integer", "default": 0},
                                    "pagesize": {"type": "integer", "default": 10},
                                    "img": {"type": "string", "default": "thumbnail", "enum": ["embedded", "original", "thumbnail"]},
                                    "data_source": {"type": "array", "items": {"type": "string"}, "default": None},
                                },
                                "required": [],
                            }
                        }
                    },
                }

            # Attach static info
            if path.endswith("/query") or path.endswith("/query/field") or path.endswith("/query/sources"):
                tool["fields"] = solr_fields
                tool["data_sources"] = data_sources

            tools.append(tool)

    return {"version": "1.0", "base_url": base_url.rstrip("/") + "/", "tools": tools}
