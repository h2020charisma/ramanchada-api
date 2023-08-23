import os
import uuid
import time
import shutil
from app.models.models import Task  # Import your data models
from pathlib import Path
import requests
import json 
import nexusformat.nexus.tree as nx
import ramanchada2 as rc2 
from fastapi import HTTPException
import traceback

from ..config.app_config import initialize_dirs

config, UPLOAD_DIR, NEXUS_DI, TEMPLATE_DIR = initialize_dirs()

def process(_json,task,base_url):
    try:
        with open(os.path.join(TEMPLATE_DIR,f"{task.id}.json"), "w") as json_file:
            json.dump(_json, json_file, indent=4) 

        task.result=f"{base_url}template/{task.id}?format=json"
    except Exception as perr:
        task.result=f"{base_url}template/{task.id}?format=json",
        task.status="Error"
        task.error = f"Error storing template {perr}"
        task.errorCause = traceback.format_exc() 