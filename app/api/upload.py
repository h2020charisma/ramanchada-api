from fastapi import APIRouter, UploadFile, File, Depends
from fastapi import Request , Query , HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from app.models.models import Task  # Import the Task model
from app.services import upload_service
import os
import uuid
import time
import shutil
from pynanomapper.datamodel.ambit import Substances

router = APIRouter()

from ..config.app_config import load_config
from ..models.models import tasks_db

config = load_config()

UPLOAD_DIR = config.upload_dir
os.makedirs(UPLOAD_DIR, exist_ok=True)

async def get_request(request: Request = Depends()):
    return request

@router.post("/dataset")  # Use router.post instead of app.post
async def upload_and_convert(request: Request,
                             background_tasks: BackgroundTasks,
                                file: UploadFile = File(...), 
                                jsonconfig: UploadFile = File(None),
                                expandconfig: UploadFile = File(None)
                                ):
    base_url = str(request.base_url)  
    #background_tasks.add_task(process_long_task, data)
    task_id = str(uuid.uuid4())
    task = Task(
        uri=f"{base_url}task/{task_id}",
        id=task_id,
        name=f"Upload file {file.filename}",
        error=None,
        policyError=None,
        status="Running",
        started=int(time.time() * 1000),
        completed=None,
        result=f"{base_url}dataset/{task_id}",
        errorCause=None
    )      
    tasks_db[task.id] = task
    background_tasks.add_task(upload_service.process,task,file,jsonconfig,expandconfig,base_url)
    return {"task": [task.dict()]}

@router.get("/dataset/{uuid}",
    responses={
    200: {
        "description": "Returns the dataset in the requested format",
        "content": {
            "application/json": {
                "example": "see pynanomapper.datamodel.ambit.Substances "
                #"schema": {"$ref": "#/components/schemas/Substances"}
            },
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                "example": "see Template Wizard data entry templates"
            },
            "application/x-hdf5": {
                "example": "pynanomapper.datamodel.ambit.Substances converted to Nexus format"
            }
        }
    },
    404: {"description": "Dataset not found"}
}
)
async def get_dataset(request : Request, uuid: str,format:str = Query(None, description="format",enum=["xlsx", "json", "h5", "nxs"])):
    # Construct the file path based on the provided UUID
    format_supported  = {
        "xlsx" : {"mime" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "ext" : "xlsx"},
        "json" : {"mime" : "application/json" , "ext" : "json"},
        "hdf5" : {"mime" : "application/x-hdf5", "ext" : "nxs"},
        "h5" : {"mime" : "application/x-hdf5", "ext" : "nxs"},
        "nxs" : {"mime" : "application/x-hdf5", "ext" : "nxs"},
        "nexus" : {"mime" : "application/x-hdf5", "ext" : "nxs"}
    }
    
    if format is None:
        format = "nxs"
    if format in format_supported:
        _ext = format_supported[format]["ext"]
        file_path = os.path.join(UPLOAD_DIR, f"{uuid}.{_ext}")
        if os.path.exists(file_path):
            # Return the file using FileResponse
            return FileResponse(file_path, media_type=format_supported[format]["mime"], 
                                    headers={"Content-Disposition": f'attachment; filename="{uuid}.{format}"'})
    else:
        file_path = os.path.join(UPLOAD_DIR, f"{uuid}.{format}")
        if os.path.exists(file_path):
            return FileResponse(file_path, 
                                    headers={"Content-Disposition": f'attachment; filename="{uuid}.{format}"'})            
      
    raise HTTPException(status_code=404, detail="Not found")