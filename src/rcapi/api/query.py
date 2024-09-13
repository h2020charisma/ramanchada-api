from fastapi import APIRouter, Request
from fastapi import Request , HTTPException, Header, Depends
from typing import Optional, Literal
from rcapi.services import query_service
import traceback 
router = APIRouter()

solr_root = "https://solr-kc.ideaconsult.net/solr/"

@router.get("/query", )
async def get_query(
                    request: Request,
                    q: Optional[str] = "*", 
                    query_type : Optional[Literal["metadata","knnquery"]] = "metadata", 
                    q_reference : Optional[str] = "*", q_provider : Optional[str] = "*", 
                    ann : Optional[str] = None,
                    page : Optional[int] = 0, pagesize : Optional[int] = 10,
                    img: Optional[Literal["embedded", "original", "thumbnail"]] = "thumbnail",
                    ):
    solr_url = "{}charisma/select".format(solr_root)

    textQuery = q
    textQuery = "*" if textQuery is None or textQuery=="" else textQuery

    #tr.set_name("query_type={}&q_reference={}&q_provider={}&solr_url={}&embedded={}&q={}&ann={}".format(query_type,q_reference,q_provider,solr_url,embedded_images,q,ann))
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
            img=img
        )
        return results
    except Exception as err:
        print(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(err))

    
