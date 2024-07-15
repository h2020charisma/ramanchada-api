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
import asyncio
import pandas as pd
from openpyxl import load_workbook

config, UPLOAD_DIR, NEXUS_DI, TEMPLATE_DIR = initialize_dirs()

# Create a lock object
lock = asyncio.Lock()

async def write_to_json(data, filename):
    async with lock:
        with open(filename, "w") as json_file:
            json.dump(data, json_file, indent=4)
            return filename   


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


async def process(_json,task,base_url,uuid):
    try:
        if json is None:
            print(_json,task,base_url,uuid)
            raise ValueError("Empty JSON!")
        await write_to_json(_json,os.path.join(TEMPLATE_DIR,f"{uuid}.json"))
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
        try:
            with open(file_path, "r") as file:
                json_data = json.load(file)
        except Exception as err:
            print(uuid,err)
            return None,None        
    else:
        file_path = None
    return json_data ,file_path



from pynanomapper.datamodel.templates import blueprint as bp
    
async def get_template_xlsx(uuid,json_blueprint,project):
    try:
        file_path_xlsx = os.path.join(TEMPLATE_DIR, f"{uuid}.xlsx")  
        json_blueprint = clean_blueprint_json(json_blueprint)
        print(json_blueprint)
        layout = json_blueprint.get("template_layout","dose_response")
        
        if layout == "dose_response": 
            df_info,df_result,df_raw,df_conditions =bp.get_template_frame(json_blueprint)
            bp.iom_format_2excel(file_path_xlsx,df_info,df_result,df_raw,df_conditions)
            try:
                bp.add_plate_layout(file_path_xlsx,json_blueprint)
                json_blueprint["template_uuid"] = uuid            
                bp.add_hidden_jsondef(file_path_xlsx,json_blueprint)                
            except:
                pass
            try:
                add_project(file_path_xlsx,project)
            except:
                pass
            return file_path_xlsx  
        else:
            json_blueprint["template_uuid"] = uuid
            bp.pchem_format_2excel(file_path_xlsx,json_blueprint)
            return file_path_xlsx  
    except Exception as err:
        raise err

async def get_nmparser_config(uuid,json_blueprint,force=True):
    file_path = os.path.join(TEMPLATE_DIR, f"{uuid}.json.nmparser")      
    json_config = bp.get_nmparser_config(json_blueprint)
    await write_to_json(json_config,file_path) 
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
                task.error = f"Can't load template {template_path}, likely invalid json. Deleting anyway."     
                os.remove(template_path)               
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

def add_materials(file_path,materials):
    column_mapping = {
        "ERM": "ERM identifiers",
        "id": "ID",
        "name": "Name",
        "casrn": "CAS",
        "type": "type",
        "supplier": "Supplier",
        "supplier_code": "Supplier code",
        "batch": "Batch",
        "core": "Core",
        "BET surface in m²/g": "BET"
    }
    # Extract keys from materials that are present in the default column mapping
    valid_keys = [key for key in column_mapping.keys() if key in set().union(*[material.keys() for material in materials])]
    
    # Create column mapping based on default mapping and valid keys
    column_mapping = {key: column_mapping[key] for key in valid_keys}
   
    # Rearrange data to match the desired order and rename columns
    materials_df = pd.DataFrame([{column_mapping[key]: value for key, value in row.items() if key in valid_keys} for row in materials])
    
        
    with pd.ExcelWriter(file_path,engine="openpyxl", mode="a",if_sheet_exists='overlay') as writer:
        materials_df.to_excel(writer, startcol=1, startrow=1, sheet_name='Materials',index=False, header=False)


def add_project(file_path,project):
    if project is None:
        return
    try:
        workbook = load_workbook(file_path)
        sheet = workbook.active
        sheet['A1'] = project.upper()
        workbook.save(file_path)
    except Exception as err:
        print(err)

def clean_blueprint_json(data):
    valid_conditions = {condition['conditon_name'] for condition in data['conditions']}
    for report in data['raw_data_report']:
        if "raw_conditions" in report:
            report['raw_conditions'] = [
                condition for condition in report['raw_conditions'] if condition in valid_conditions
            ]
    for report in data['question3']:
        if "results_conditions" in report:
            report['results_conditions'] = [
                condition for condition in report['results_conditions'] if condition in valid_conditions
            ]    
    return data    