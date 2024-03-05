import os
import uuid
import time
import shutil
from rcapi.models.models import Task  # Import your data models
from pathlib import Path
import requests
import json 
from pynanomapper.datamodel.ambit import Substances, SubstanceRecord, CompositionEntry, Component, Compound
from pynanomapper.datamodel.nexus_writer import to_nexus
from pynanomapper.datamodel.nexus_spectra import spe2ambit
import nexusformat.nexus.tree as nx
import ramanchada2 as rc2 
from fastapi import HTTPException
import traceback
import h5py
from rcapi.config.app_config import initialize_dirs

config, UPLOAD_DIR, NEXUS_DIR, TEMPLATE_DIR = initialize_dirs()


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
            task.error = "not supported here, use /dataset/convert instead"
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
    
def extract_cha_metadata(file_path,json_meta={}):
    #these are the attributes used by charisma_api and stored in HSDS 
    annotation_found = False
    with h5py.File(file_path) as dataset:
        if "annotation_sample" in dataset:
            for tag in ["sample","sample_provider"]:
                try:
                    json_meta[tag] = dataset["annotation_sample"].attrs[tag]
                except:
                    json_meta[tag] = None
            annotation_found = True
        if "annotation_study" in dataset:
            for tag in ["sample_provider","provider","wavelength","investigation","laser_power","optical_path","laser_power_percent","instrument"]:
                try:
                    json_meta[tag] = dataset["annotation_study"].attrs[tag]
                except:
                    json_meta[tag] = "DEFAULT"     
            annotation_found = True       
    return (annotation_found,json_meta)
            
def extract_native_metadata(meta,json_meta={}):
    for tag in meta.keys():
        _tag = tag.lower()
        try:
            _value = "".join(meta[tag])
        except: 
            _value = meta[tag]
        print(_tag, meta[tag],_value)
        if _tag in ["laser_wavelength","wavelength","laser wavelength"]:
            json_meta["wavelength"]=_value
        elif _tag in ["laser_powerlevel","laser power"]:
            json_meta["laser_power_percent"]=_value
        elif _tag in ["intigration times(ms)","interval_time"]:
            json_meta["integration_time (ms)","integration time"]=_value
        elif _tag in  ["model","title"]:
            json_meta["instrument_{}".format(_tag)]=_value             
        elif _tag in  ["temperature"]:
            json_meta["temperature".format(_tag)]=_value          
        elif _tag in  ["laser temperature"]:
            json_meta["laser_temperature".format(_tag)]=_value        
        elif _tag in  ["technique"]:
            json_meta["technique".format(_tag)]=_value 
        elif _tag in  ["slit width"]:
            json_meta["slit_width".format(_tag)]=_value                                                    
    return json_meta


def parse_spectrum_files(task,base_url,file_path,jsonconfig):
                        #instrument,wavelength,provider,investigation,sample,sample_provider,prefix):
    json_data = {"instrument" : "DEFAULT", "wavelength" : "DEFAULT", "provider" : "DEFAULT",
                 "investigation" : "DEFAULT", "sample" : "DEFAULT", "sample_provider" : "DEFAULT", 
                 "prefix" : "NONE"}                        
    if file_path.endswith(".cha"):
        spe = rc2.spectrum.from_chada(file_path)
        annotation_found, json_meta = extract_cha_metadata(file_path, json_data )
        if annotation_found:
            json_data = json_meta   
        else:
            json_data = extract_native_metadata(spe.meta.dict()['__root__'],json_data)
            #print(spe.meta,json_data)
    else:
        spe = rc2.spectrum.from_local_file(file_path)
        #print(spe.meta)
        json_data = extract_native_metadata(spe.meta.dict()['__root__'],json_data)
        #print(spe.meta,json_data)
        annotation_found= False    
    if not annotation_found:  #load from 
        #print(json_data)
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
    #print(json_data)
    papp = spe2ambit(spe.x,spe.y,json_data,
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

def convert_to_nexus(substances: Substances,task,base_url,dataset_uuid):
    try:
        nxroot = substances.to_nexus(nx.NXroot())
        nexus_file_path = os.path.join(NEXUS_DIR, f"{dataset_uuid}.nxs")   
        nxroot.save(nexus_file_path,mode="w")
        task.status="Completed"
        task.result=f"{base_url}dataset/{dataset_uuid}?format=nxs"
        task.result_uuid = dataset_uuid
        task.completed =int(time.time() * 1000)
    except Exception as perr:
        task.result_uuid = None
        task.result=f"{base_url}dataset/{dataset_uuid}?format=json",
        task.status="Error"
        task.error = f"Error converting to hdf5 {perr}"
        task.errorCause = traceback.format_exc() 
        task.completed =int(time.time() * 1000)
     

def parse_template_wizard_files(task,base_url,file_path,jsonconfig,expandconfig=None):
    if jsonconfig is None:
        task.status="Error"
        task.error = "Missing jsonconfig"
        task.result_uuid = None
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
            task.result_uuid = None
            task.status="Error"
            task.error = f"Error parsing template wizard files {perr}"   
            task.errorCause = traceback.format_exc() 
    task.completed=int(time.time() * 1000)

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
           
