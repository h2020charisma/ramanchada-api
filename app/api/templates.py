from fastapi import APIRouter, Depends, status, Response, Header
from fastapi import Request , Query , HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from app.models.models import Task  # Import the Task model
from app.services import template_service
import os
import uuid
import time
from pathlib import Path
import traceback
from datetime import datetime
import hashlib
import glob 

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

def get_uuid():
    return str(uuid.uuid4())

def generate_etag(data):
    data_str = str(data)
    return hashlib.md5(data_str.encode()).hexdigest()

def get_last_modified(file_path):
    try:
        timestamp = os.path.getmtime(file_path)
        last_modified = datetime.utcfromtimestamp(timestamp)
        return last_modified
    except FileNotFoundError:
        return None

@router.post("/template")  # Use router.post instead of app.post
async def convert(request: Request,
                    background_tasks: BackgroundTasks,
                    response: Response,
                    if_modified_since: datetime = Header(None, alias="If-Modified-Since")
                ):
    task_id = get_uuid()    
    template_uuid = task_id
    content_type = request.headers.get("content-type", "").lower()    
    if content_type != "application/json":
        perr = Exception(": expected content type is not application/json")
    else:
        perr = None
    try:
        base_url = get_baseurl(request)  
    except Exception as err:
        perr = err

    task = Task(
            uri=f"{base_url}task/{task_id}",
            id=task_id,
            name=f"Store template json",
            error=None,
            policyError=None,
            status="Running",
            started=int(time.time() * 1000),
            completed=None,
            result=f"{base_url}template/{template_uuid}",
            result_uuid=template_uuid,
            errorCause=None
        )      
    try:
        tasks_db[task.id] = task
        if perr is None:
            _json = await request.json()        
            background_tasks.add_task(template_service.process,_json,task,base_url,template_uuid)
        else: 
            background_tasks.add_task(template_service.process_error,perr,task,base_url,template_uuid)
            response.status_code = status.HTTP_400_BAD_REQUEST
    except Exception as perr:
        task.result=f"{base_url}template/{template_uuid}",
        task.status="Error"
        task.error = f"Error storing template {perr}"
        task.errorCause = traceback.format_exc() 
        task.result = None
        response.status_code = status.HTTP_400_BAD_REQUEST

    return task

    

@router.post("/template/{uuid}")  # Use router.post instead of app.post
async def convert(request: Request,
                    background_tasks: BackgroundTasks,
                    uuid: str
                ):
    base_url = get_baseurl(request)
    task_id = get_uuid()  
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
            result_uuid = uuid,
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
async def get_template(request : Request, response : Response,
                        uuid: str,
                        format:str = Query(None, description="format",enum=["xlsx", "json", "nmparser", "h5", "nxs"]),
                        if_none_match: str = Header(None, alias="If-None-Match"),
                        if_modified_since: datetime = Header(None, alias="If-Modified-Since")
                        ):
    # Construct the file path based on the provided UUID
    format_supported  = {
        "xlsx" : {"mime" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                  "ext" : "xlsx"},
        "json" : {"mime" : "application/json" , "ext" : "json" },
        "nmparser" : {"mime" : "application/json" , "ext" : "nmparser.json" }
    }

    _response = None
    if format is None:
        format = "json"
    
    
    if format in format_supported:
        if format=="json":
            json_data ,file_path = template_service.get_template_json(uuid) 
            # Check Last-Modified header
            last_modified_time = get_last_modified(file_path)
            if if_modified_since and if_modified_since >= last_modified_time:
                return JSONResponse(content=None, status_code=304)       
            _etag = generate_etag(json_data)
            if if_none_match and if_none_match == str(_etag):
                return JSONResponse(content=None, status_code=304)

            # Return the data with updated headers
            custom_headers = { "ETag": _etag,    "Last-Modified":  last_modified_time.strftime("%a, %d %b %Y %H:%M:%S GMT") }
            response.headers.update(custom_headers)
            return json_data
        elif format=="nmparser":             
            file_path =  template_service.get_nmparser_config(uuid)
            _response =  FileResponse(file_path, media_type=format_supported[format]["mime"], 
                                    headers={"Content-Disposition": f'attachment; filename="{uuid}.{format}.json"'})
            custom_headers = {  "Last-Modified":  last_modified_time.strftime("%a, %d %b %Y %H:%M:%S GMT") }
            response.headers.update(custom_headers)
            return _response
        elif format=="xlsx":         
            file_path =  template_service.get_template_xlsx(uuid)
            # Return the file using FileResponse
            _response =  FileResponse(file_path, media_type=format_supported[format]["mime"], 
                                    headers={"Content-Disposition": f'attachment; filename="{uuid}.{format}"'})
            custom_headers = {  "Last-Modified":  last_modified_time.strftime("%a, %d %b %Y %H:%M:%S GMT") }
            response.headers.update(custom_headers)
            return _response
    else:
            raise HTTPException(status_code=400, detail="Format not supported")


@router.get("/template")
async def get_templates(request : Request,q:str = Query(None), response: Response = None,
                    if_modified_since: datetime = Header(None, alias="If-Modified-Since")):
    base_url = get_baseurl(request) 
    uuids = {}
    last_modified_time = None
    try:
        list_of_json_files = glob.glob(os.path.join(TEMPLATE_DIR, '*.json'))
        latest_json_file = max(list_of_json_files, key=os.path.getmtime)
        last_modified_time = os.path.getmtime(latest_json_file)
        if if_modified_since and if_modified_since >= last_modified_time:
            return JSONResponse(content=None, status_code=304)        
    except:
        pass

         
    for filename in os.listdir(TEMPLATE_DIR):
        if filename.endswith(".json"):
            file_path = os.path.join(TEMPLATE_DIR, filename)
            if os.path.isfile(file_path):
                _uuid = Path(file_path).stem.split("_")[0]
                _json, _file_path = template_service.get_template_json(_uuid); 
                timestamp = os.path.getmtime(file_path)
                if last_modified_time is None or last_modified_time<timestamp:
                    last_modified_time = timestamp
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
                            uuids[_uuid][tag] = "DRAFT" if tag=="template_status" else "?"
    last_modified_datetime = datetime.utcfromtimestamp(last_modified_time)
    custom_headers = {
        "Last-Modified": last_modified_datetime.strftime("%a, %d %b %Y %H:%M:%S GMT")
    }
    response.headers.update(custom_headers)
    return {"template" : list(uuids.values())}

@router.delete("/template/{uuid}",
    responses={
        200: {"description": "Template deleted successfully"},
        404: {"description": "Template not found"}
    }
)
async def delete_template(request: Request,
                    background_tasks: BackgroundTasks,
                    uuid: str):
    template_path = os.path.join(TEMPLATE_DIR, f"{uuid}.json")
    base_url = get_baseurl(request)  
    task_id = get_uuid()
    task = Task(
            uri=f"{base_url}task/{task_id}",
            id=task_id,
            name=f"Delete template {uuid}",
            error=None,
            policyError=None,
            status="Running",
            started=int(time.time() * 1000),
            completed=None,
            result=f"{base_url}task/{task_id}",
            result_uuid = None,
            errorCause=None
        )      
    tasks_db[task.id] = task
    background_tasks.add_task(template_service.delete_template,template_path,task,base_url,task_id)
    return task
