from fastapi import APIRouter, UploadFile, File
from app.models.models import Task  # Import the Task model
from app.services import  process_service
import os
import uuid
import time
import shutil

router = APIRouter()

@router.post("/process")  # Use router.post instead of app.post
async def process_hdf5(hdf5_url: str):
    task =  process_service.process(hdf5_url)
    return {"task": [task.dict()]}