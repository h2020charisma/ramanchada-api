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



def iom_format(df,param_name="param_name",param_group="param_group"):
    df.fillna(" ",inplace=True)
    # Create a new DataFrame with one column
    result_df = pd.DataFrame(columns=['param_name'])
    # Iterate through unique groups
    for group in df[param_group].unique():
        group_df = df[df[param_group] == group]
        # Get names for the group
        names = group_df[param_name].tolist()
        # Append group and names to the result DataFrame
        result_df = pd.concat([result_df, pd.DataFrame({'param_name': [group] + names + ['']})], ignore_index=True)
    return result_df

def json2frame(json_data,sortby):
    return pd.DataFrame(json_data).sort_values(by=sortby)

def get_template_frame(uuid):
    file_path = os.path.join(TEMPLATE_DIR, f"{uuid}.json")
    json_data = None
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            json_data = json.load(file)
    df_sample = json2frame(json_data["METADATA_SAMPLE_INFO"],sortby=["param_sample_group"]).rename(columns={'param_sample_name': 'param_name'})    

    df_sample_prep = json2frame(json_data["METADATA_SAMPLE_PREP"],sortby=["param_sampleprep_group"]).rename(columns={'param_sampleprep_name': 'param_name'})    
    result_df_sampleprep = iom_format(df_sample_prep,"param_name","param_sampleprep_group")

    #df_sample["param_sample_name"] 
    df_params = json2frame(json_data["METADATA_PARAMETERS"],sortby=["param_group"])    
    result_df = iom_format(df_params)

    #print(df_sample.columns,result_df.columns)
    empty_row = pd.DataFrame({col: [""] * len(result_df.columns) for col in result_df.columns})
    return pd.concat([df_sample[["param_name"]],empty_row,result_df_sampleprep,empty_row,result_df], ignore_index=True)
    

def get_template_xlsx(uuid):
    file_path = os.path.join(TEMPLATE_DIR, f"{uuid}.xlsx")
    if not os.path.exists(file_path):
       df = get_template_frame(uuid)
       df.to_excel(file_path, index=False)             
       print(df) 
    return file_path       