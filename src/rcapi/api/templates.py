from fastapi import APIRouter, Depends, status, Response, Header
from fastapi import Request , Query , HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from rcapi.config.app_config import initialize_dirs
from rcapi.models.models import Task  # Import the Task model
from rcapi.models.models import tasks_db
from rcapi.services import template_service
import os
import uuid
import time
from pathlib import Path
import traceback
from datetime import datetime
import hashlib
import glob 

router = APIRouter()

config, UPLOAD_DIR, NEXUS_DIR, TEMPLATE_DIR = initialize_dirs()
DATE_FORMAT = "%a, %d %b %Y %H:%M:%S GMT" 

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

def is_valid_uuid(s):
    try:
        uuid_obj = uuid.UUID(str(s))
        return str(uuid_obj) == s
    except ValueError:
        return False

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
                    response: Response
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
        print(err)
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
        print(f"Error parsing JSON: {perr}")
        print(f"Request body: {await request.body()}")           
        task.status="Error"
        task.error = f"Error storing template {perr}"
        task.errorCause = traceback.format_exc() 
        task.result = None
        task.result_uuid = None
        response.status_code = status.HTTP_400_BAD_REQUEST
        task.completed=int(time.time() * 1000)

    return task

    

@router.post("/template/{uuid}")  # Use router.post instead of app.post
async def update(request: Request,
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


@router.post("/template/{uuid}/copy")  # copy a template
async def makecopy(request: Request,
                    background_tasks: BackgroundTasks,
                    uuid: str
                ):
    base_url = get_baseurl(request)
    task_id = get_uuid()  
    result_uuid = get_uuid()
    json_data ,file_path = template_service.get_template_json(uuid) 
    json_data["origin_uuid"] = uuid
    try:
        _json = await request.json()
        for tag in ["template_name","template_author","template_acknowledgment"]:
            _label = "Copy of"
            if tag in _json:
                _label = _json[tag]
            json_data[tag] = "{} {}".format(_label,json_data[tag])
    except Exception as err:
        #empty body
        pass
    task = Task(
            uri=f"{base_url}task/{task_id}",
            id=task_id,
            name=f"Create copy of /template/{uuid}",
            error=None,
            policyError=None,
            status="Running",
            started=int(time.time() * 1000),
            completed=None,
            result=f"{base_url}template/{result_uuid}",
            result_uuid = result_uuid,
            errorCause=None
        )      
    tasks_db[task.id] = task
    background_tasks.add_task(template_service.process,json_data,task,base_url,result_uuid)
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
                        if_modified_since: str = Header(None, alias="If-Modified-Since")
                        ):
    # Construct the file path based on the provided UUID
    format_supported  = {
        "xlsx" : {"mime" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                  "ext" : "xlsx"},
        "json" : {"mime" : "application/json" , "ext" : "json" },
        "nmparser" : {"mime" : "application/json" , "ext" : "nmparser.json" }
    }
    if not is_valid_uuid(uuid):
        raise HTTPException(status_code=400, detail="Invalid UUID")
    _response = None
    if format is None:
        format = "json"
    
    if format in format_supported:
        json_blueprint ,file_path = template_service.get_template_json(uuid) 
        if file_path is None:
            raise HTTPException(status_code=404, detail="Not found")
        if json_blueprint is None:
            raise HTTPException(status_code=404, detail="Not found")        
        last_modified_time = get_last_modified(file_path)
        custom_headers = {  "Last-Modified":  last_modified_time.strftime(DATE_FORMAT) }
        if format=="json":
            # Check Last-Modified header
            if if_modified_since and last_modified_time <= datetime.strptime(if_modified_since,DATE_FORMAT):
                return JSONResponse(status_code=304, content=None)            
   
            _etag = generate_etag(json_blueprint)
            if if_none_match and if_none_match == str(_etag):
                return JSONResponse(content=None, status_code=304)
            # Return the data with updated headers
            response.headers.update(custom_headers)
            return json_blueprint
            #response = JSONResponse(content=json_blueprint, headers=custom_headers)
        elif format=="nmparser":             
            file_path =  await template_service.get_nmparser_config(uuid,json_blueprint)
            _response =  FileResponse(file_path, media_type=format_supported[format]["mime"], 
                                    headers={"Content-Disposition": f'attachment; filename="{uuid}.{format}.json"'})
            _response.headers.update(custom_headers)
            return _response
        elif format=="xlsx":         
            try:
                file_path =  await template_service.get_template_xlsx(uuid,json_blueprint)
                # Return the file using FileResponse
                _response =  FileResponse(file_path, media_type=format_supported[format]["mime"], 
                                    headers={"Content-Disposition": f'attachment; filename="{uuid}.{format}"'})
                _response.headers.update(custom_headers)
                return _response
            except Exception as err:
                raise HTTPException(status_code=400, detail="The blueprint may not be complete. {}".format(err))
    else:
        raise HTTPException(status_code=400, detail="Format not supported")


def generate_etag_for_response(uuids):
    """Generate a single ETag for the entire response based on UUIDs."""
    concatenated_values = ''.join(str(value) for value in uuids.values())
    sha256 = hashlib.sha256()
    sha256.update(concatenated_values.encode('utf-8'))
    return sha256.hexdigest()

@router.get("/template")
async def get_templates(request : Request,q:str = Query(None), response: Response = None,
                    if_modified_since: str = Header(None, alias="If-Modified-Since"),
                    if_none_match: str = Header(None, alias="If-None-Match")
                    ):
    #print("Received Headers:", request.headers)
    #print("if_modified_since",if_modified_since)
    base_url = get_baseurl(request) 
    uuids = {}
    last_modified_time = None
    try:
        list_of_json_files = glob.glob(os.path.join(TEMPLATE_DIR, '*.json'))
        latest_json_file = max(list_of_json_files, key=os.path.getmtime)
        last_modified_time = get_last_modified(latest_json_file)
        if if_modified_since and last_modified_time <= datetime.strptime(if_modified_since,DATE_FORMAT):
            return JSONResponse(status_code=304, content=None)
    except Exception as err:
        print(err)
        pass
         
    for filename in os.listdir(TEMPLATE_DIR):
        if filename.endswith(".json"):
            file_path = os.path.join(TEMPLATE_DIR, filename)
            if os.path.isfile(file_path):
                _uuid = Path(file_path).stem.split("_")[0]
                _json, _file_path = template_service.get_template_json(_uuid); 
                if _file_path is None:
                    continue
                if _json is None:
                    _json = {}               
                timestamp =  get_last_modified(_file_path)
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
                    uuids[_uuid]["timestamp"] = timestamp
                    for tag in ["PROTOCOL_CATEGORY_CODE","EXPERIMENT","template_name","template_status","template_author","template_acknowledgment"]:
                        try:
                            uuids[_uuid][tag] = _json[tag]
                        except:
                            uuids[_uuid][tag] = "DRAFT" if tag=="template_status" else "?"
    
    response_etag = generate_etag_for_response(uuids)
    if if_none_match and if_none_match == response_etag:
       print(if_none_match,response_etag)
       return JSONResponse(status_code=304, content=None)        

    if last_modified_time != None:
        custom_headers = {
            "Last-Modified": last_modified_time.strftime(DATE_FORMAT)
        }
        response.headers.update(custom_headers)
        #print(custom_headers)
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
