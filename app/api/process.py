from fastapi import APIRouter
from fastapi import Request , Query , HTTPException, BackgroundTasks
from app.models.models import Task  # Import the Task model
from app.services import  process_service
import os
import uuid
import time
import shutil

from ..models.models import tasks_db

router = APIRouter()

@router.post("/process")  # Use router.post instead of app.post
async def process_hdf5(request: Request,
                       background_tasks: BackgroundTasks,
                       dataset_uri:str = Query(..., description="dataset_uri")):
    base_url = str(request.base_url)  
    task_id = str(uuid.uuid4())
    task = Task(
        uri=f"{base_url}task/{task_id}",
        id=task_id,
        name=f"Process file {dataset_uri}",
        error=None,
        policyError=None,
        status="Running",
        started=int(time.time() * 1000),
        completed=None,
        result=f"{dataset_uri}",
        errorCause=None
    )      
    tasks_db[task.id] = task
    background_tasks.add_task(process_service.process,task,dataset_uri)
    return {"task": [task.dict()]}
