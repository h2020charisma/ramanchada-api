import os
import uuid
import time
import shutil
from rcapi.models.models import Task  # Import your data models
import h5py
from ..config.app_config import load_config
from pyambit.nexus_parser import SpectrumParser

config = load_config()
async def process(task : Task,process_config : dict, nexus_dataset_url: str,base_url: str):
    try:
        process_class = process_config["class"]
        process_class.process(task,nexus_dataset_url,base_url)

        task.status = "Completed"
    except (ImportError, AttributeError) as e:
        task.status = "Error"
        task.error = f"Failed to load plugin or class: {e}"
    except Exception as e:
        task.status = "Error"
        task.error = f"{e}"   
    task.completed=int(time.time() * 1000)  
UPLOAD_DIR = config.upload_dir
os.makedirs(UPLOAD_DIR, exist_ok=True)

async def process_new(task : Task,nexus_dataset_url: str,base_url: str):
    open_dataset(nexus_dataset_url,base_url)
    task.status = "Completed"
    task.completed=int(time.time() * 1000)
    

def open_dataset(nexus_dataset_url: str,base_url: str):
    if nexus_dataset_url.startswith(base_url):
        uuid = nexus_dataset_url.split("/")[-1]
        spectrum_parser = SpectrumParser()
        spectrum_parser.parse(os.path.join(UPLOAD_DIR,f"{uuid}.nxs"))
        # Access the spectrum data
        for key in spectrum_parser.parsed_objects:
            spe = spectrum_parser.parsed_objects[key]
            print("Spectrum data", key, spe)
            #spe.plot()     
        
    else:
        pass