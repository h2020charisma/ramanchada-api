from fastapi import APIRouter, UploadFile, File, Depends
from fastapi import Request , Query , HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from app.models.models import Task  # Import the Task model
from app.services import template_service
import os
import uuid
import time
import shutil
from pynanomapper.datamodel.ambit import Substances
from pathlib import Path
import json
        
router = APIRouter()

from ..models.models import tasks_db

from ..config.app_config import initialize_dirs

config, UPLOAD_DIR, NEXUS_DIR, TEMPLATE_DIR = initialize_dirs()


async def get_request(request: Request = Depends()):
    return request


@router.post("/template")  # Use router.post instead of app.post
async def convert(request: Request,
                    background_tasks: BackgroundTasks
                ):
    content_type = request.headers.get("content-type", "").lower()
    base_url = str(request.base_url)  
    task_id = str(uuid.uuid4())
    _json = await request.json()
    task = Task(
            uri=f"{base_url}task/{task_id}",
            id=task_id,
            name=f"Store template json",
            error=None,
            policyError=None,
            status="Running",
            started=int(time.time() * 1000),
            completed=None,
            result=f"{base_url}template/{task_id}",
            errorCause=None
        )      
    tasks_db[task.id] = task
    background_tasks.add_task(template_service.process,_json,task,base_url)
    return task

    
@router.get("/template/{uuid}",
    responses={
    200: {
        "description": "Returns the dataset in the requested format",
        "content": {
            "application/json": {
                "example": "surveyjs json"
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
    404: {"description": "Template not found"}
}
)
async def get_template(request : Request, uuid: str,format:str = Query(None, description="format",enum=["xlsx", "json", "h5", "nxs"])):
    # Construct the file path based on the provided UUID
    format_supported  = {
        "xlsx" : {"mime" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                  "ext" : "xlsx"},
        "json" : {"mime" : "application/json" , "ext" : "json" },
        "hdf5" : {"mime" : "application/x-hdf5", "ext" : "nxs"},
        "h5" : {"mime" : "application/x-hdf5", "ext" : "nxs" },
        "nxs" : {"mime" : "application/x-hdf5", "ext" : "nxs" },
        "nexus" : {"mime" : "application/x-hdf5", "ext" : "nxs" }
    }
    
    if format is None:
        format = "json"
    if format in format_supported:
        _ext = format_supported[format]["ext"]
        _dir = TEMPLATE_DIR
        file_path = os.path.join(_dir, f"{uuid}.{_ext}")
        if os.path.exists(file_path):
            if format=="json":
                with open(file_path, "r") as json_file:
                    json_data = json.load(json_file)
                return json_data  
            else:          
            # Return the file using FileResponse
                return FileResponse(file_path, media_type=format_supported[format]["mime"], 
                                    headers={"Content-Disposition": f'attachment; filename="{uuid}.{format}"'})
    else:
        file_path = os.path.join(TEMPLATE_DIR, f"{uuid}.{format}")
        if os.path.exists(file_path):
            return FileResponse(file_path, 
                                    headers={"Content-Disposition": f'attachment; filename="{uuid}.{format}"'})            
      
    raise HTTPException(status_code=404, detail="Not found")

@router.get("/template")
async def get_datasets(request : Request,q:str = Query(None)):
    base_url = str(request.base_url) 
    uuids = {}
    for _dir in [TEMPLATE_DIR]:
        for filename in os.listdir(_dir):
            file_path = os.path.join(_dir, filename)
            if os.path.isfile(file_path):
                _uuid = Path(file_path).stem.split("_")[0]
                uri=f"{base_url}template/{_uuid}"
                _ext = Path(file_path).suffix
                if not uri in uuids:
                    uuids[uri] = {}
                    uuids[uri]["format"] = []
                uuids[uri]["format"].append(_ext.replace(".",""))
    return { "templates" : uuids}
