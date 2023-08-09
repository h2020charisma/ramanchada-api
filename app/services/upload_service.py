import os
import uuid
import time
import shutil
from app.models.models import Task  # Import your data models
from pathlib import Path
import requests
import json 

from ..config.app_config import load_config

config = load_config()

UPLOAD_DIR = config.upload_dir
os.makedirs(UPLOAD_DIR, exist_ok=True)

def process(file,jsonconfig,expandconfig,base_url):
    task_id = str(uuid.uuid4())
    task = Task(
        uri=f"{base_url}task/{task_id}",
        id=task_id,
        name=f"Upload file {file.filename}",
        error=None,
        policyError=None,
        status="Running",
        started=int(time.time() * 1000),
        completed=int(time.time() * 1000),
        result=f"{base_url}dataset/{task_id}",
        errorCause=None
    )    
    try:
        # Save uploaded file to a temporary location
        file_extension = Path(file.filename).suffix
        file_path = os.path.join(UPLOAD_DIR, f"{task_id}{file_extension}")
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        task.result=f"{base_url}dataset/{task_id}{file_extension}",
        
        if file_extension.lower() == ".xlsx" or file_extension.lower() == ".xls":
            if jsonconfig is None:
                task.status="Error"
                task.error = "Missing jsonconfig"
            else:    
                json_file_path = os.path.join(UPLOAD_DIR, f"{task_id}_config.json")
                with open(json_file_path, "wb") as f:
                    shutil.copyfileobj(jsonconfig.file, f)

                parsed_file_path = os.path.join(UPLOAD_DIR, f"{task_id}.json")   
                parsed_json = nmparser(file_path,json_file_path)
                with open(parsed_file_path, "w") as json_file:
                    json.dump(parsed_json, json_file)                     
                task.result=f"{base_url}dataset/{task_id}.json",
                task.status="Completed"

        else: #consider a spectrum
            task.status="Error"
            task.error = "not supported yet"
        
        task.completed=int(time.time() * 1000)
        
    except Exception as err:
        task.error = str(err)
        task.status = "Error"
        task.completed=int(time.time() * 1000)
    
    return task



def nmparser(xfile,jsonconfig,expandfile=None):
    with open(xfile, 'rb') as fin:
        with open(jsonconfig, 'rb') as jin:
            form = {'files[]': fin,'jsonconfig' : jin, 'expandfile':expandfile}
            response = requests.post(config.nmparse_url, files=form)
                                 #auth=GraviteeAuth("1942a33b-d71e-466c-8c06-c0147b90d878"))
        return response.json()
           
