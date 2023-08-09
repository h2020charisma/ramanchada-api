import os
import uuid
import time
import shutil
from app.models.models import Task  # Import your data models
from pathlib import Path
import requests
import json 
from  pynanomapper.datamodel.ambit import Substances
from  pynanomapper.datamodel.nexus_utils import to_nexus
import nexusformat.nexus.tree as nx

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
            parse_template_wizard_files(task,base_url,file_path,jsonconfig,expandconfig)
        else: #consider a spectrum
            parse_spectrum_files(task,base_url,file_path)
        
        task.completed=int(time.time() * 1000)
        
    except Exception as err:
        task.error = str(err)
        task.status = "Error"
        task.completed=int(time.time() * 1000)
    
    return task

def parse_spectrum_files(task,base_url,file_path):
    task.status="Error"
    task.error = "not supported yet"

def parse_template_wizard_files(task,base_url,file_path,jsonconfig,expandconfig=None):
    if jsonconfig is None:
        task.status="Error"
        task.error = "Missing jsonconfig"
    else:    
        json_file_path = os.path.join(UPLOAD_DIR, f"{task.id}_config.json")
        with open(json_file_path, "wb") as f:
            shutil.copyfileobj(jsonconfig.file, f)

        parsed_file_path = os.path.join(UPLOAD_DIR, f"{task.id}.json")   
        parsed_json = nmparser(file_path,json_file_path)
        with open(parsed_file_path, "w") as json_file:
            json.dump(parsed_json, json_file)                       
        try:
            s = Substances(**parsed_json)
            root = s.to_nexus(nx.NXroot())
                #print(root.tree)
            nexus_file_path = os.path.join(UPLOAD_DIR, f"{task.id}.nxs")   
            root.save(nexus_file_path, 'w')                    
            task.status="Completed"
            task.result=f"{base_url}dataset/{task.id}.nxs",
        except Exception as perr:    
            task.result=f"{base_url}dataset/{task.id}.json",
            task.status="Error"
            task.error = "Error converting to hdf5"    

def nmparser(xfile,jsonconfig,expandfile=None):
    with open(xfile, 'rb') as fin:
        with open(jsonconfig, 'rb') as jin:
            form = {'files[]': fin,'jsonconfig' : jin, 'expandfile':expandfile}
            response = requests.post(config.nmparse_url, files=form)
        return response.json()
           
