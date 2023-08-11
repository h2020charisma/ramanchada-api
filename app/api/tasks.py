from fastapi import APIRouter, Request, HTTPException

router = APIRouter()

from ..models.models import tasks_db

@router.get("/task/{uuid}")
async def get_task(request : Request, uuid: str):
    if uuid in tasks_db:
        return tasks_db[uuid]
    else:
        raise HTTPException(status_code=404, detail="Not found")

@router.get("/task")
async def get_tasks(request : Request):
    return list(tasks_db.values())
