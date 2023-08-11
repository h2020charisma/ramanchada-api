from fastapi import APIRouter, Request, HTTPException

tasks_db = {}

router = APIRouter()

@router.get("/task/{uuid}")
async def get_dataset(request : Request, uuid: str):
    if uuid in tasks_db:
        return tasks_db[uuid]
    else:
        raise HTTPException(status_code=404, detail="Not found")
