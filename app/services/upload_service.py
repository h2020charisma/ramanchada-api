import os
import uuid
import time
import shutil
from app.models.models import Task  # Import your data models

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def process(file):
    task_id = str(uuid.uuid4())
    
    # Save uploaded file to a temporary location
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    # Simulate processing time
    time.sleep(5)
    
    task = Task(
        uri=f"https://apps.ideaconsult.net/calibrate/task/{task_id}",
        id=task_id,
        name="example",
        error="",
        policyError="",
        status="Completed",
        started=int(time.time() * 1000),
        completed=int(time.time() * 1000),
        result=f"https://apps.ideaconsult.net/calibrate/task/{task_id}",
        errorCause=None
    )
    
    return task
