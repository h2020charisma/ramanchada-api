from fastapi import APIRouter, UploadFile, File, Depends
from fastapi import Request 
from fastapi.responses import FileResponse
from app.models.models import Task  # Import the Task model
from app.services import upload_service
import os
import uuid
import time
import shutil
from ..config.app_config import load_config

router = APIRouter()
config = load_config()

UPLOAD_DIR = config.upload_dir
os.makedirs(UPLOAD_DIR, exist_ok=True)

async def get_request(request: Request = Depends()):
    return request

@router.post("/dataset")  # Use router.post instead of app.post
async def upload_and_convert(request: Request,file: UploadFile = File(...)):
    base_url = str(request.base_url)  
    task =  upload_service.process(file,base_url)
    return {"task": [task.dict()]}

@router.get("/dataset/{uuid}")
async def get_dataset(uuid: str):
    # Construct the file path based on the provided UUID
    file_path = os.path.join(UPLOAD_DIR, f"{uuid}.xlsx")

    if os.path.exists(file_path):
        # Return the file using FileResponse
        return FileResponse(file_path, media_type="application/octet-stream")
    else:
        return {"error": "File not found"}