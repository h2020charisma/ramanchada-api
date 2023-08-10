import os
import uuid
import time
import shutil
from app.models.models import Task  # Import your data models
from pathlib import Path
import requests
import json 
from  pynanomapper.datamodel.ambit import Substances,SubstanceRecord,CompositionEntry,Component, Compound
from  pynanomapper.datamodel.nexus_utils import to_nexus
from  pynanomapper.datamodel.nexus_spectra import spe2ambit
import nexusformat.nexus.tree as nx
import ramanchada2 as rc2 

from ..config.app_config import load_config

config = load_config()

UPLOAD_DIR = config.upload_dir
os.makedirs(UPLOAD_DIR, exist_ok=True)

def process(file,jsonconfig,expandconfig,base_url):
    task_id = str(uuid.uuid4())
    task = Task(
        #uri=f"{base_url}task/{task_id}",
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
        task.result=f"{base_url}dataset/{task_id}?format={file_extension}",
        
        if file_extension.lower() == ".xlsx" or file_extension.lower() == ".xls":
            parse_template_wizard_files(task,base_url,file_path,jsonconfig,expandconfig)
        else: #consider a spectrum
            parse_spectrum_files(task,base_url,file_path,jsonconfig)
        
        task.completed=int(time.time() * 1000)
        
    except Exception as err:
        task.error = str(err)
        task.status = "Error"
        task.completed=int(time.time() * 1000)
    
    return task

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
    nxroot = Substances(substance=substances).to_nexus(nx.NXroot())
    nexus_file_path = os.path.join(UPLOAD_DIR, f"{task.id}.nxs")   
    nxroot.save(nexus_file_path,mode="w")
    task.status="Completed"
    task.result=f"{base_url}dataset/{task.id}?format=nxs",        

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
            task.result=f"{base_url}dataset/{task.id}?format=nxs",
        except Exception as perr:    
            task.result=f"{base_url}dataset/{task.id}?format=json",
            task.status="Error"
            task.error = f"Error converting to hdf5 {perr}"    

def nmparser(xfile,jsonconfig,expandfile=None):
    with open(xfile, 'rb') as fin:
        with open(jsonconfig, 'rb') as jin:
            form = {'files[]': fin,'jsonconfig' : jin, 'expandfile':expandfile}
            response = requests.post(config.nmparse_url, files=form)
        return response.json()
           
