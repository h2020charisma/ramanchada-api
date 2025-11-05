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


@router.api_route("/query", methods=["GET", "POST"], response_model=StandardResponse[List[dict]])
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
    filters: Optional[Dict[str, Any]] = Body(
        default=None,
        example={"name_s": "Anatase"},
        description="Optional dict of field:value filters (keys limited by configuration)"
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
      "filters": {"name_s": "Anatase"},
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
            filters = body.get("filters", filters)
        # --- GET: extract filters.* parameters -----------------------------------
        elif request.method == "GET":
            query_filters = {
                k[len("filters."):]: v
                for k, v in request.query_params.items()
                if k.startswith("filters.")
            }
            if query_filters:
                filters = query_filters

        # --- determine which collections user can access ------------------------------
        solr_url, collection_param, dropped = SOLR_COLLECTIONS.get_url(
            SOLR_ROOT, data_source, drop_private=token is None
        )

        # --- filter sanitization ------------------------------------------------------
        allowed_fields = [f.field for f in SOLR_FIELDS]
        filters = sanitize_filters(filters, allowed_fields)

        # --- merge filters into Solr query string -------------------------------------
        textQuery = q or "*"
        if filters:
            filter_query = " AND ".join(f"{k}:{v}" for k, v in filters.items())
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


@router.get("/query/field", response_model=StandardResponse[List[dict]])
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
        params = {"q": "*", "rows": 0, "facet.field": name, "facet": "true"}
        if collection_param is not None:
            params["collection"] = collection_param
        rs = await solr_query_get(solr_url, params, token)
        # Extract the facet field values
        facet_field_values = rs.json()["facet_counts"]["facet_fields"][name]
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
@router.get("/query/sources")
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