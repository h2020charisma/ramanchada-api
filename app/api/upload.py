from fastapi import APIRouter, UploadFile, File
from app.models.models import Task  # Import the Task model
from app.services import upload_service
import os
import uuid
import time
import shutil

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/dataset")  # Use router.post instead of app.post
async def upload_and_convert(file: UploadFile = File(...)):
    try:
        task =  upload_service.process(file)
        return {"task": [task.dict()]}
    except Exception as err:
        print(err)
