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
import openpyxl
import pandas as pd 

from ..config.app_config import initialize_dirs

config, UPLOAD_DIR, NEXUS_DI, TEMPLATE_DIR = initialize_dirs()

def process(_json,task,base_url,uuid):
    try:
        with open(os.path.join(TEMPLATE_DIR,f"{uuid}.json"), "w") as json_file:
            json.dump(_json, json_file, indent=4) 
        task.status="Completed"
        task.result=f"{base_url}template/{uuid}"
    except Exception as perr:
        task.result=f"{base_url}template/{uuid}",
        task.status="Error"
        task.error = f"Error storing template {perr}"
        task.errorCause = traceback.format_exc() 

def get_template_json(uuid):
    file_path = os.path.join(TEMPLATE_DIR, f"{uuid}.json")
    json_data = None
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            json_data = json.load(file)
    return json_data



from pynanomapper.datamodel.templates import blueprint as bp
    

def get_template_xlsx(uuid,force=True):
    
    if force or not os.path.exists(file_path):
        file_path = os.path.join(TEMPLATE_DIR, f"{uuid}.json")
        if os.path.exists(file_path):
            with open(file_path, "r") as file:
                json_blueprint = json.load(file)     
            file_path = os.path.join(TEMPLATE_DIR, f"{uuid}.xlsx")      
            df = bp.get_template_frame(json_blueprint)
            bp.iom_format_2excel(df,file_path)

    return file_path       