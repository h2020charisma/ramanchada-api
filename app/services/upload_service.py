import os
import uuid
import time
import shutil
from app.models.models import Task  # Import your data models
from pathlib import Path
import requests
import json 
from  pynanomapper.datamodel.ambit import Substances,SubstanceRecord,CompositionEntry,Component, Compound
from  pynanomapper.datamodel.nexus_writer import to_nexus
from  pynanomapper.datamodel.nexus_spectra import spe2ambit
import nexusformat.nexus.tree as nx
import ramanchada2 as rc2 
from fastapi import HTTPException
import traceback

from ..config.app_config import initialize_dirs

config, UPLOAD_DIR, NEXUS_DIR = initialize_dirs()

async def process(task,dataset_type,file,jsonconfig,expandconfig,base_url):
    
    try:
        # Save uploaded file to a temporary location
        file_extension = Path(file.filename).suffix
        file_path = os.path.join(UPLOAD_DIR, f"{task.id}{file_extension}")
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        ext = file_extension.replace(".","")    
        task.result=f"{base_url}dataset/{task.id}?format={ext}",
        
        if dataset_type == "raman_spectrum":
            parse_spectrum_files(task,base_url,file_path,jsonconfig)
        elif dataset_type == "ambit_json":
            task.error = "not supported yet"
            task.status = "Error"              
            pass
        else: #assume "template_wizard"
            dataset_type = "template_wizard"
            if file_extension.lower() == ".xlsx" or file_extension.lower() == ".xls":
                try:
                    parse_template_wizard_files(task,base_url,file_path,jsonconfig,expandconfig)
                    task.status = "Completed"
                except HTTPException as err:
                    task.error = "error parsing file"
                    task.errorCause = traceback.format_exc()
                    task.status = "Error"                
                except Exception as err:
                    task.error = str(err)
                    task.status = "Error"
            else:
                task.error = f"Unsupported file {file.filename} of type {dataset_type}"
                task.status = "Error"
        task.completed=int(time.time() * 1000)
        
    except Exception as err:
        task.error = str(err)
        task.status = "Error"
        task.completed=int(time.time() * 1000)
    

def parse_spectrum_files(task,base_url,file_path,jsonconfig):
                        #instrument,wavelength,provider,investigation,sample,sample_provider,prefix):
    spe = rc2.spectrum.from_local_file(file_path)
    json_data = {"instrument" : "DEFAULT", "wavelength" : "DEFAULT", "provider" : "DEFAULT",
                 "investigation" : "DEFAULT", "sample" : "DEFAULT", "sample_provider" : "DEFAULT", 
                 "prefix" : "NONE"}
    if jsonconfig is None:
        task.status="Warning"
        task.error = "Missing jsonconfig"
    else:    
        json_file_path = os.path.join(UPLOAD_DIR, f"{task.id}_config.json")
        with open(json_file_path, "wb") as f:
            shutil.copyfileobj(jsonconfig.file, f)
        with open(json_file_path, "r") as f:
            json_data = json.load(f)            
    sample=json_data["sample"]
    papp = spe2ambit(spe.x,spe.y,spe.meta,
                            instrument = json_data["instrument"],
                            wavelength=json_data["wavelength"],
                            provider=json_data["provider"],
                            investigation=json_data["investigation"],
                            sample=json_data["sample"],
                            sample_provider = json_data["sample_provider"],
                            prefix = json_data["prefix"])                       
    substance = SubstanceRecord(name=sample,i5uuid=papp.owner.substance.uuid)
    substance.composition = list()
    composition_entry = CompositionEntry(component = Component(compound = Compound(name=sample),values={}))
    substance.composition.append(composition_entry)
    if substance.study is None:
        substance.study = [papp]
    else:
        substance.study.add(papp)
    substances = []
    substances.append(substance)
        #study = mx.Study(study=studies)
    convert_to_nexus(Substances(substance=substances),task,base_url)       

def convert_to_nexus(substances: Substances,task,base_url):
    try:
        nxroot = substances.to_nexus(nx.NXroot())
        nexus_file_path = os.path.join(NEXUS_DIR, f"{task.id}.nxs")   
        nxroot.save(nexus_file_path,mode="w")
        task.status="Completed"
        task.result=f"{base_url}dataset/{task.id}?format=nxs"
    except Exception as perr:
        task.result=f"{base_url}dataset/{task.id}?format=json",
        task.status="Error"
        task.error = f"Error converting to hdf5 {perr}"
        task.errorCause = traceback.format_exc() 
     

def parse_template_wizard_files(task,base_url,file_path,jsonconfig,expandconfig=None):
    if jsonconfig is None:
        task.status="Error"
        task.error = "Missing jsonconfig"
    else:    
        json_file_path = os.path.join(UPLOAD_DIR, f"{task.id}_config.json")
        with open(json_file_path, "wb") as f:
            shutil.copyfileobj(jsonconfig.file, f)
        parsed_file_path = os.path.join(UPLOAD_DIR, f"{task.id}.json")   
        try:
            parsed_json = nmparser(file_path,json_file_path)
            with open(parsed_file_path, "w") as json_file:
                json.dump(parsed_json, json_file)             
            substances = Substances(**parsed_json)
            convert_to_nexus(substances,task,base_url)                
        except Exception as perr:    
            task.result=f"{base_url}dataset/{task.id}?format=json",
            task.status="Error"
            task.error = f"Error parsing template wizard files {perr}"   
            task.errorCause = traceback.format_exc() 

def nmparser(xfile,jsonconfig,expandfile=None):
    with open(xfile, 'rb') as fin:
        with open(jsonconfig, 'rb') as jin:
            form = {'files[]': fin,'jsonconfig' : jin, 'expandfile':expandfile}
            try:
                response = requests.post(config.nmparse_url, files=form, timeout=None)
                response.raise_for_status()
                return response.json()
            except Exception as err:
                raise err
           
