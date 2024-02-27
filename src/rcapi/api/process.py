from fastapi import APIRouter
from fastapi import Request , Form , HTTPException, BackgroundTasks
from rcapi.models.models import Task  # Import the Task model
from rcapi.models.models import tasks_db
from rcapi.services import  process_service
from rcapi.services import processing_spectra as ps
import os
import uuid
import time
import shutil

router = APIRouter()

config_processing = {
    "test" : { "class" : ps.ProcessMock },
    "calibrate" : { "class" : ps.ProcessCalibrate},
    "peaks" : { "class" : ps.ProcessFindPeak},

}

def get_process_class(process_id : str):
    if process_id in config_processing:
        return config_processing[process_id]
    else:
        return None
    
@router.get("/process")
async def get_tasks(request : Request):
    return list(config_processing.keys())
    
@router.post("/process/{process_id}")  # Use router.post instead of app.post
async def process_run(request: Request,
                       process_id: str,
                       background_tasks: BackgroundTasks,
                       dataset_uri:str = Form(...)):
    base_url = str(request.base_url)  
    task_id = str(uuid.uuid4())
    task = Task(
        uri=f"{base_url}task/{task_id}",
        id=task_id,
        name=f"Process file {dataset_uri} with {process_id}",
        error=None,
        policyError=None,
        status="Running",
        started=int(time.time() * 1000),
        completed=None,
        result=f"{dataset_uri}",
        result_uuid= None,
        errorCause=None
    )      
    tasks_db[task.id] = task
    process_config = get_process_class(process_id);
    if process_config is None:
        task.status = "Error"
        task.error = f"Invalid process_id {process_id}"    
        task.completed=int(time.time() * 1000)
    else:
        background_tasks.add_task(process_service.process,task,process_config,dataset_uri,base_url)
    return {"task": [task.dict()]}
