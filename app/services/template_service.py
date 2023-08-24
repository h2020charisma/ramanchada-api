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

from ..config.app_config import initialize_dirs

config, UPLOAD_DIR, NEXUS_DI, TEMPLATE_DIR = initialize_dirs()

def process(_json,task,base_url):
    try:
        with open(os.path.join(TEMPLATE_DIR,f"{task.id}.json"), "w") as json_file:
            json.dump(_json, json_file, indent=4) 
        task.status="Completed"
        task.result=f"{base_url}template/{task.id}?format=json"
    except Exception as perr:
        task.result=f"{base_url}template/{task.id}?format=json",
        task.status="Error"
        task.error = f"Error storing template {perr}"
        task.errorCause = traceback.format_exc() 

def get_template_json(uuid):
    file_path = os.path.join(TEMPLATE_DIR, f"{uuid}.json")
    json_data = None
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            json_data = json.load(file)
    return json_data;

def get_template_xlsx(uuid):
    file_path = os.path.join(TEMPLATE_DIR, f"{uuid}.xlsx")
    if not os.path.exists(file_path):
       json_data =  get_template_json(uuid)
       workbook = openpyxl.Workbook()
       sheet = workbook.create_sheet("Template")
       col = 1
       
       for pg in json_data["PARAMETER_GROUP"]:
           print(pg)
           sheet.cell(row=1,column=col).value = pg["section_name"]
           for p in pg["experiment_parameters"]:
               sheet.cell(row=2,column=col).value = p["PARAMETER_NAME"]
               col = col + 1 
       workbook.save(file_path)

    return file_path       