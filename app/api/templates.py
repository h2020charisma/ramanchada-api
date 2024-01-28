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


def get_baseurl(request : Request):
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "http")
    base_url = str(request.base_url) 
    if "localhost" not in base_url:
        base_url = base_url.replace("http://", "{}://".format(forwarded_proto))  
    return base_url


@router.post("/template")  # Use router.post instead of app.post
async def convert(request: Request,
                    background_tasks: BackgroundTasks
                ):
    content_type = request.headers.get("content-type", "").lower()
    base_url = get_baseurl(request)  
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
    background_tasks.add_task(template_service.process,_json,task,base_url,task_id)
    return task

    

@router.post("/template/{uuid}")  # Use router.post instead of app.post
async def convert(request: Request,
                    background_tasks: BackgroundTasks,
                    uuid: str
                ):
    base_url = get_baseurl(request)
    task_id = str(uuid.uuid4())
    _json = await request.json()
    task = Task(
            uri=f"{base_url}task/{task_id}",
            id=task_id,
            name=f"Update template json {uuid}",
            error=None,
            policyError=None,
            status="Running",
            started=int(time.time() * 1000),
            completed=None,
            result=f"{base_url}template/{uuid}",
            errorCause=None
        )      
    tasks_db[task.id] = task
    background_tasks.add_task(template_service.process,_json,task,base_url,uuid)
    return task


@router.get("/template/{uuid}",
    responses={
    200: {
        "description": "Returns the template in the requested format",
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
async def get_template(request : Request, uuid: str,format:str = Query(None, description="format",enum=["xlsx", "json", "nmparser", "h5", "nxs"])):
    # Construct the file path based on the provided UUID
    format_supported  = {
        "xlsx" : {"mime" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                  "ext" : "xlsx"},
        "json" : {"mime" : "application/json" , "ext" : "json" },
        "nmparser" : {"mime" : "application/json" , "ext" : "nprasrer.json" }
    }
    
    if format is None:
        format = "json"
    if format in format_supported:
        if format=="json":
            return template_service.get_template_json(uuid)
        elif format=="nmparser":             
            file_path =  template_service.get_nmparser_config(uuid)
            return FileResponse(file_path, media_type=format_supported[format]["mime"], 
                                    headers={"Content-Disposition": f'attachment; filename="{uuid}.{format}.json"'})
        elif format=="xlsx":         
            file_path =  template_service.get_template_xlsx(uuid)
            # Return the file using FileResponse
            return FileResponse(file_path, media_type=format_supported[format]["mime"], 
                                    headers={"Content-Disposition": f'attachment; filename="{uuid}.{format}"'})

    raise HTTPException(status_code=404, detail="Not found")

@router.get("/template")
async def get_datasets(request : Request,q:str = Query(None)):
    base_url = get_baseurl(request) 
    uuids = {}
    for filename in os.listdir(TEMPLATE_DIR):
        if filename.endswith(".json"):
            file_path = os.path.join(TEMPLATE_DIR, filename)
            if os.path.isfile(file_path):
                _uuid = Path(file_path).stem.split("_")[0]
                _json = template_service.get_template_json(_uuid); 
                timestamp = os.path.getmtime(file_path)
                try:
                    _method = _json["METHOD"]               
                except:
                    _method = None
                if not (_uuid in uuids):
                    uri=f"{base_url}template/{_uuid}"
                    #_ext = Path(file_path).suffix
                    uuids[_uuid] = {}
                    uuids[_uuid]["uri"] =  uri
                    uuids[_uuid]["uuid"] = _uuid 
                    uuids[_uuid]["METHOD"] = _method
                    uuids[_uuid]["timestamp"] = int(timestamp)
                    for tag in ["PROTOCOL_CATEGORY_CODE","EXPERIMENT","template_name","template_status","template_author","template_acknowledgment"]:
                        try:
                            uuids[_uuid][tag] = _json[tag]
                        except:
                            uuids[_uuid][tag] = "?"

    return {"template" : list(uuids.values())}
