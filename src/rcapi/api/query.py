from fastapi import APIRouter, Request
from fastapi import Request , HTTPException
from typing import Optional, Literal
from rcapi.services import query_service

router = APIRouter()

solr_root = "https://solr-kc.ideaconsult.net/solr/"

@router.get("/query", )
async def get_query(request : Request, 
                    q: Optional[str] = "*", 
                    query_type : Optional[Literal["metadata","knnquery"]] = "metadata", 
                    q_reference : Optional[str] = "*", q_provider : Optional[str] = "*", 
                    ann : Optional[str] = None,
                    page : Optional[int] = 0, pagesize : Optional[int] = 10,
                    img: Optional[Literal["embedded", "original", "thumbnail"]] = "thumbnail"
                    ):
    solr_url = "{}charisma/select".format(solr_root)

    textQuery = q
    textQuery = "*" if textQuery is None or textQuery=="" else textQuery

    #tr.set_name("query_type={}&q_reference={}&q_provider={}&solr_url={}&embedded={}&q={}&ann={}".format(query_type,q_reference,q_provider,solr_url,embedded_images,q,ann))
    try:
        results = query_service.process(
            request=request,
            solr_url=solr_url,
            q=q,
            query_type=query_type,
            q_reference=q_reference,
            q_provider=q_provider,
            ann=ann,
            page=page,
            pagesize=pagesize,
            img=img
        )
    except Exception as err:
        print(traceback.exc)
        raise HTTPException(status_code=400, detail=str(err))

    return results
