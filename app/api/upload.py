from fastapi import APIRouter, UploadFile, File, Depends
from fastapi import Request , Query , HTTPException
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

config = load_config()

UPLOAD_DIR = config.upload_dir
os.makedirs(UPLOAD_DIR, exist_ok=True)

async def get_request(request: Request = Depends()):
    return request

@router.post("/dataset")  # Use router.post instead of app.post
async def upload_and_convert(request: Request,file: UploadFile = File(...), 
                                jsonconfig: UploadFile = File(None),
                                expandconfig: UploadFile = File(None)):
    base_url = str(request.base_url)  
    task =  upload_service.process(file,jsonconfig,expandconfig,base_url)
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
        "xlsx" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "json" : "application/json",
        "hdf5" : "application/x-hdf5",
        "h5" : "application/x-hdf5",
        "nxs" : "application/x-hdf5",
        "nexus" : "application/x-hdf5",
    }
    if format is None:
        format = "nxs"
    if format in format_supported:
        file_path = os.path.join(UPLOAD_DIR, f"{uuid}.{format}")
        if os.path.exists(file_path):
            # Return the file using FileResponse
            return FileResponse(file_path, media_type=format_supported[format], headers={"Content-Disposition": f'attachment; filename="{uuid}.{format}"'})
    else:
        raise HTTPException(status_code=404, detail="Not found")