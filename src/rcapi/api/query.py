from fastapi import APIRouter, Request, HTTPException, Depends, Query
from typing import Optional, Literal, Set
from rcapi.services import query_service
from rcapi.services.solr_query import (
    SOLR_ROOT, SOLR_VECTOR, SOLR_COLLECTIONS, solr_query_get
)
from rcapi.services.kc import get_token, get_roles_from_token
import traceback

router = APIRouter()


@router.get("/query", )
async def get_query(
        request: Request,
        q: Optional[str] = "*",
        query_type: Optional[Literal["metadata", "text", "knnquery"]] = "text",
        q_reference: Optional[str] = "*", q_provider: Optional[str] = "*",
        ann: Optional[str] = None,
        page: Optional[int] = 0, pagesize: Optional[int] = 10,
        img: Optional[Literal["embedded", "original", "thumbnail"]] = "thumbnail",
        vector_field: Optional[str] = None,
        data_source: Optional[Set[str]] = Query(default=None),
        token: Optional[str] = Depends(get_token)
        ):
    solr_url, collection_param = SOLR_COLLECTIONS.get_url(
        SOLR_ROOT, data_source)

    textQuery = q
    textQuery = "*" if textQuery is None or textQuery == "" else textQuery

    # tr.set_name("query_type={}&q_reference={}&q_provider={}&solr_url={}&embedded={}&q={}&ann={}".format(query_type,q_reference,q_provider,solr_url,embedded_images,q,ann))
    try:
        results = await query_service.process(
            request=request,
            solr_url=solr_url,
            q=q,
            query_type=query_type,
            q_reference=q_reference,
            q_provider=q_provider,
            ann=ann,
            page=page,
            pagesize=pagesize,
            img=img,
            collections=collection_param,
            vector_field=SOLR_VECTOR if vector_field is None else vector_field,
            token=token
        )
        return results
    except Exception as err:
        print(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(err))


@router.get("/query/field")
async def get_field(
        request: Request,
        name: str = "publicname_s",
        data_source: Optional[Set[str]] = Query(default=None),
        token: Optional[str] = Depends(get_token)
        ):
    solr_url, collection_param = SOLR_COLLECTIONS.get_url(
        SOLR_ROOT, data_source)
    try:
        params = {"q": "*", "rows": 0, "facet.field": name, "facet": "true"}
        if collection_param is not None:
            params["collection"] = collection_param
        rs = await solr_query_get(solr_url, params, token)
        result = []
        # Extract the facet field values
        facet_field_values = rs.json()["facet_counts"]["facet_fields"][name]
        # Convert to an array of objects with name and count properties
        result = []
        for i in range(0, len(facet_field_values), 2):
            result.append({"value": facet_field_values[i],
                           "count": facet_field_values[i + 1]})
        return result
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
            "data_sources": [
                {"name": c.name, "description": c.description}
                for c in accessible_collections
            ]
        }

    except HTTPException as err:
        raise err
    except Exception as err:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(err))