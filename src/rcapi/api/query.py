from fastapi import APIRouter, Request, HTTPException, Depends, Query, Body
from typing import Optional, Literal, Set, List, Dict, Any
import traceback

from rcapi.services import query_service
from rcapi.services.standard_response import StandardResponse
from rcapi.services.solr_query import (
    SOLR_ROOT, SOLR_VECTOR, SOLR_COLLECTIONS, SOLR_FIELDS, solr_query_get
)
from rcapi.services.kc import get_token, get_roles_from_token

router = APIRouter()


@router.api_route(
    "/query",
    methods=["GET", "POST"],
    response_model=StandardResponse[List[dict]],
    summary="Search experiments",
    description="Perform a search for study types as in ambit data model using query parameters or filters.",
    openapi_extra={
        "x-mcp-prompt": (
            "Use this tool to search the ambit/enanomapper  database. Provide query terms, "
            "dynamic query fields, and optional parameters. Example for metadata search: "
            "{'query_type': 'metadata', 'q': '*', 'qdynamic': {'name_s': 'polystyrene'}, 'data_source': 'charisma'}. "
            "For vector similarity search: {'query_type': 'knnquery', 'ann': '<base64_vector>'}. "
            "Include pagination with 'page' and 'pagesize'."
        )
    }
)
async def query_universal(
    request: Request,
    # standard GET parameters
    q: Optional[str] = Query(default="*"),
    query_type: Optional[Literal["metadata", "text", "knnquery"]] = "text",
    q_reference: Optional[str] = "*",
    q_provider: Optional[str] = "*",
    q_method: Optional[str] = "*",
    ann: Optional[str] = None,
    page: Optional[int] = 0,
    pagesize: Optional[int] = 10,
    img: Optional[Literal["embedded", "original", "thumbnail"]] = "thumbnail",
    vector_field: Optional[str] = None,
    data_source: Optional[Set[str]] = Query(default=None),
    # flexible JSON input for POST 
    qdynamic: Optional[Dict[str, Any]] = Body(
        default=None,
        example={"name_s": "Anatase"},
        description="Optional dict of field:value dynamic query (keys limited by configuration)"
    ),
    token: Optional[str] = Depends(get_token),
):
    """
    Universal query endpoint for spectra and safety-related data.

    - **GET** supports classic query-string style .
    - **POST** accepts structured JSON for MCP or automated clients.

    Example POST body:
    ```json
    {
      "q": "PP",
      "data_source": "charisma",
      "qdynamic": {"name_s": "Anatase"},
      "page": 0,
      "pagesize": 10
    }
    ```
    """
    try:
        # --- handle POST body (merge JSON with query params) --------------------------
        if request.method == "POST":
            body = await request.json()
            q = body.get("q", q)
            query_type = body.get("query_type", query_type)
            q_reference = body.get("q_reference", q_reference)
            q_provider = body.get("q_provider", q_provider)
            q_method = body.get("q_method", q_method)
            ann = body.get("ann", ann)
            page = body.get("page", page)
            pagesize = body.get("pagesize", pagesize)
            img = body.get("img", img)
            vector_field = body.get("vector_field", vector_field)
            # Allow both str and list for data_source
            ds = body.get("data_source", data_source)
            data_source = {ds} if isinstance(ds, str) else set(ds or [])
            qdynamic = body.get("qdynamic", qdynamic)
        # --- GET: extract filters.* parameters -----------------------------------
        elif request.method == "GET":
            query_dynamic = {
                k[len("qdynamic."):]: v
                for k, v in request.query_params.items()
                if k.startswith("qdynamic.")
            }
            if query_dynamic:
                qdynamic = query_dynamic

        # --- determine which collections user can access ------------------------------
        solr_url, collection_param, dropped = SOLR_COLLECTIONS.get_url(
            SOLR_ROOT, data_source, drop_private=token is None
        )

        # --- filter sanitization ------------------------------------------------------
        allowed_fields = [
            f.field.removeprefix("qdynamic.") 
            for f in SOLR_FIELDS
        ]
        qdynamic = sanitize_filters(qdynamic, allowed_fields)

        # --- merge filters into Solr query string -------------------------------------
        textQuery = q or "*"
        if qdynamic:
            filter_query = " AND ".join(f"{k}:{v}" for k, v in qdynamic.items())
            textQuery = f"({textQuery}) AND ({filter_query})" if textQuery != "*" else filter_query

        # --- call Solr service --------------------------------------------------------
        stdResponse = await query_service.process(
            request=request,
            solr_url=solr_url,
            q=textQuery,
            query_type=query_type,
            q_reference=q_reference,
            q_provider=q_provider,
            q_method=q_method,
            ann=ann,
            page=page,
            pagesize=pagesize,
            img=img,
            collections=collection_param,
            vector_field=SOLR_VECTOR if vector_field is None else vector_field,
            token=token,
        )
        stdResponse.status = 1 if dropped else 0
        return stdResponse
    except HTTPException as err:
        raise err
    except Exception as err:
        print(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(err))


@router.get(
    "/query/field",
    summary="Get facet values for a query field",
    description="Return all possible values for a given query field",
    openapi_extra={
        "x-mcp-prompt": (
            "Use this resource to get the list of values for a specific field. "
            "Provide the field name (e.g., 'instrument_s') and optional data sources. "
            "Returns read-only metadata with counts for each value."
        )
    },
    response_model=StandardResponse[List[dict]]
)
async def get_field(
    request: Request,
    name: str = "publicname_s",
    data_source: Optional[Set[str]] = Query(default=None),
    token: Optional[str] = Depends(get_token),
):
    solr_url, collection_param, dropped = SOLR_COLLECTIONS.get_url(
        SOLR_ROOT, data_source, drop_private=token is None
    )
    try:
        # we need the original field names
        _name = name.replace("qdynamic.", "")
        _name = query_service.get_predefined(_name)
        params = {"q": "*", "rows": 0, "facet.field": _name, "facet": "true"}
        if collection_param is not None:
            params["collection"] = collection_param
        rs = await solr_query_get(solr_url, params, token)
        # Extract the facet field values
        facet_field_values = rs.json()["facet_counts"]["facet_fields"][_name]
        # Convert to an array of objects with name and count properties
        result = []
        for i in range(0, len(facet_field_values), 2):
            result.append({"value": facet_field_values[i],
                           "count": facet_field_values[i + 1]})
        return StandardResponse(status=1 if dropped else 0, response=result)
    except HTTPException as err:
        raise err
    except Exception as err:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(err))


# https://github.com/h2020charisma/ramanchada-api/issues/59
@router.get(
    "/query/sources",
    summary="List available data sources",
    description="Return  collections accessible to the user along with field metadata.",
    openapi_extra={
        "x-mcp-prompt": (
            "Use this resource to discover which data sources are available for queries. "
            "Returns a list of collections with names, descriptions, and accessibility. "
            "This is read-only metadata."
        )
    },
)
async def get_sources(
        request: Request,
        token: Optional[str] = Depends(get_token)
        ):
    try:
        if token is not None:
            user_roles = get_roles_from_token(token)
        else:
            user_roles = []
        user_roles.append("public")
        # Filter collections based on user's roles
        accessible_collections = SOLR_COLLECTIONS.for_roles(user_roles)

        return {
            "default": SOLR_COLLECTIONS.default,
            "data_sources": [
                {"name": c.name,
                 "description": c.description,
                 "public": "public" in c.roles}
                for c in accessible_collections
            ],
            "fields": SOLR_FIELDS
        }

    except HTTPException as err:
        raise err
    except Exception as err:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(err))


# --- helper for safe filter handling -------------------------------------------------
def sanitize_filters(filters: Optional[dict], allowed_fields: list[str]) -> dict:
    """
    Keep only filters that match allowed Solr field names.
    Ignore unknown or malformed filters.
    """
    if not filters:
        return {}
    safe = {}
    for key, value in filters.items():
        if key in allowed_fields and isinstance(value, (str, int, float)):
            safe[key] = value
    return safe