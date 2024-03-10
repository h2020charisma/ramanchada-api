import os
from rcapi.config.app_config import initialize_dirs
from rcapi.models.models import Task  # Import your data models
from pathlib import Path
import json 
import nexusformat.nexus.tree as nx
import ramanchada2 as rc2 
from fastapi import HTTPException
import traceback
import os
from datetime import datetime, timedelta
import glob 
import time
import uuid
config, UPLOAD_DIR, NEXUS_DI, TEMPLATE_DIR = initialize_dirs()

def process_error(perr,task,base_url,uuid):
    task.result=f"{base_url}template/{uuid}"
    task.result_uuid = None
    task.status="Error"
    task.error = f"Error storing template {perr}"
    task.completed=int(time.time() * 1000)
    if isinstance(perr, str):
        task.errorCause = perr
    else:
        task.errorCause = traceback.format_exc()


def process(_json,task,base_url,uuid):
    try:
        print(_json)
        with open(os.path.join(TEMPLATE_DIR,f"{uuid}.json"), "w") as json_file:
            json.dump(_json, json_file, indent=4) 
        task.status="Completed"
        task.result=f"{base_url}template/{uuid}"
        task.result_uuid = uuid
        task.completed=int(time.time() * 1000)
    except Exception as perr:
        task.result=f"{base_url}template/{uuid}"
        task.result_uuid = None
        task.status="Error"
        task.error = f"Error storing template {perr}"
        task.errorCause = traceback.format_exc() 
        task.completed=int(time.time() * 1000)
        

def get_template_json(uuid):
    file_path = os.path.join(TEMPLATE_DIR, f"{uuid}.json")
    json_data = None
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            json_data = json.load(file)
    return json_data ,file_path



from pynanomapper.datamodel.templates import blueprint as bp
    


def get_template_xlsx(uuid,json_blueprint):
    try:
        file_path_xlsx = os.path.join(TEMPLATE_DIR, f"{uuid}.xlsx")   
        df_info,df_result,df_raw =bp.get_template_frame(json_blueprint)
        bp.iom_format_2excel(file_path_xlsx,df_info,df_result,df_raw)
        return file_path_xlsx  
    except Exception as err:
        raise err

def get_nmparser_config(uuid,json_blueprint,force=True):
    file_path = os.path.join(TEMPLATE_DIR, f"{uuid}.json.nmparser")      
    json_config = bp.get_nmparser_config(json_blueprint)
    with open(file_path, 'w') as json_file:
        json.dump(json_config, json_file, indent=2)            
        return file_path   
    

# 8h is for a test 
# otherwise we agreed on 1 month
def cleanup(delta = timedelta(hours=8) ):
    current_time = datetime.now() 
    threshold_time = current_time - delta
    
    json_files = glob.glob(os.path.join(TEMPLATE_DIR, '*.json'))
    for file_name in json_files:
        last_modified_time = datetime.fromtimestamp(os.path.getmtime(file_name))
        # Check if the file is older than age_hours
        if last_modified_time < threshold_time:
            task_id = str(uuid.uuid4())
            task = Task(
                uri=task_id,
                id=task_id,
                name="Delete template {}".format(file_name),
                error=None,
                policyError=None,
                status="Running",
                started=int(time.time() * 1000),
                completed=None,
                result=task_id,
                result_uuid=None,
                errorCause=None
            ) 
            delete_template(file_name,task=task)


def delete_template(template_path,task,base_url=None,uuid=None):
    if os.path.exists(template_path):
        json_data = None
        try:
            with open(template_path, 'r') as json_file:
                json_data = json.load(json_file)
            if json_data is None:
                task.status="Error"
                task.error = f"Can't load template {template_path}"                    
            else:    
                template_status = json_data.get('template_status') if "template_status" in json_data else "DRAFT"
                if template_status == 'DRAFT':
                    os.remove(template_path)
                    task.status="Completed"
                else:
                    task.status="Error"
                    task.error = f"Template is finalized, can't be deleted"                    
                
        except Exception as err:
            task.status="Error"
            task.error = f"Error deleting template {err}"
            task.errorCause = traceback.format_exc()     
    else:
        task.status="Error"
        task.error = f"Template not found"
    task.completed =int(time.time() * 1000)
