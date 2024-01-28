import os
from app.models.models import Task  # Import your data models
from pathlib import Path
import json 
import nexusformat.nexus.tree as nx
import ramanchada2 as rc2 
from fastapi import HTTPException
import traceback
import os

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
    file_path_xlsx = os.path.join(TEMPLATE_DIR, f"{uuid}.xlsx")
    
    if force or not os.path.exists(file_path):
        file_path = os.path.join(TEMPLATE_DIR, f"{uuid}.json")
        if os.path.exists(file_path):
            with open(file_path, "r") as file:
                json_blueprint = json.load(file)     
            df_info,df_result,df_raw =bp.get_template_frame(json_blueprint)
            bp.iom_format_2excel(file_path_xlsx,df_info,df_result,df_raw)
        else:
            raise FileNotFoundError(f"Fole not found {uuid}.json")
    return file_path_xlsx       

def get_nmparser_config(uuid,force=True):
    
    if force or not os.path.exists(file_path):
        file_path = os.path.join(TEMPLATE_DIR, f"{uuid}.json")
        if os.path.exists(file_path):
            with open(file_path, "r") as file:
                json_blueprint = json.load(file)     
            file_path = os.path.join(TEMPLATE_DIR, f"{uuid}.nmparser.json")      
            json_config = bp.get_nmparser_config(json_blueprint)
            with open(file_path, 'w') as json_file:
                json.dump(json_config, json_file, indent=2)            
            return file_path   
        else:
            raise Exception(f"No such file {uuid}.json")
    raise Exception("")    