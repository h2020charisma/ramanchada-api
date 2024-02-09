from fastapi import APIRouter, Request, HTTPException, Response, status
from fastapi.responses import JSONResponse

router = APIRouter()

from ..models.models import tasks_db

@router.get("/task/{uuid}")
async def get_task(request : Request, uuid: str, response: Response):
    if uuid in tasks_db:
        if tasks_db[uuid].status == "Error":
            response.status_code = status.HTTP_400_BAD_REQUEST
            return tasks_db[uuid]
        else:
            return tasks_db[uuid]
    else:
        raise HTTPException(status_code=404, detail="Not found")

@router.get("/task")
async def get_tasks(request : Request):
    return list(tasks_db.values())
