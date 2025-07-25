from fastapi import APIRouter, Request, HTTPException, Response, status, Header
from datetime import datetime
from rcapi.models.models import tasks_db

router = APIRouter()

@router.get("/task/{uuid}")
async def get_task(request: Request, uuid: str, response: Response,
            if_none_match: str = Header(None, alias="If-None-Match"),
            if_modified_since: datetime = Header(None, alias="If-Modified-Since")
            ):
    if uuid in tasks_db:
        # Check Last-Modified header
        #if if_modified_since and if_modified_since >= last_modified_time:
        #    return JSONResponse(content=None, status_code=304)
    
        if tasks_db[uuid].status == "Error":
            response.status_code = status.HTTP_400_BAD_REQUEST
            return tasks_db[uuid]
        else:
            return tasks_db[uuid]
    else:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/task")
async def get_tasks(request: Request):
    return list(tasks_db.values())
