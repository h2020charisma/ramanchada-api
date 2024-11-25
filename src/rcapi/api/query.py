from fastapi import APIRouter, Request, HTTPException, Depends
from typing import Optional, Literal
from rcapi.services import query_service
from rcapi.services.solr_query import (
    SOLR_ROOT, SOLR_VECTOR, SOLR_COLLECTION, solr_query_get
)
from rcapi.services.kc import get_token
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
        token: Optional[str] = Depends(get_token)
        ):
    solr_url = "{}{}/select".format(SOLR_ROOT, SOLR_COLLECTION)

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
        token: Optional[str] = Depends(get_token)
        ):
    solr_url = "{}{}/select".format(SOLR_ROOT, SOLR_COLLECTION)
    try:
        params = {"q": "*", "rows":0, "facet.field":name, "facet":"true"}
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
