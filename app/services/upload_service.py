import os
import uuid
import time
import shutil
from app.models.models import Task  # Import your data models

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def process(file,base_url):
    task_id = str(uuid.uuid4())
    task = Task(
        uri=f"{base_url}task/{task_id}",
        id=task_id,
        name=f"Upload file {file.filename}",
        error="",
        policyError="",
        status="Running",
        started=int(time.time() * 1000),
        completed=int(time.time() * 1000),
        result=f"{base_url}dataset/{task_id}",
        errorCause=None
    )    
    try:
        # Save uploaded file to a temporary location
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        
        # Simulate processing time
        time.sleep(5)
        task.status="Completed"
        task.completed=int(time.time() * 1000)
    except Exception as err:
        task.error = str(err)
        task.status = "Error"
        task.completed=int(time.time() * 1000)
    
    return task
