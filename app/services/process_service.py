import os
import uuid
import time
import shutil
from app.models.models import Task  # Import your data models
import h5py
from ..config.app_config import initialize_dirs
from pynanomapper.datamodel.nexus_parser import SpectrumParser

config, UPLOAD_DIR, NEXUS_DIR, TEMPLATE_DIR = initialize_dirs()


async def process(task : Task,nexus_dataset_url: str,base_url: str):
    open_dataset(nexus_dataset_url,base_url)
    task.status = "Completed"
    task.completed=int(time.time() * 1000)
    

def open_dataset(nexus_dataset_url: str,base_url: str):
    if nexus_dataset_url.startswith(base_url):
        uuid = nexus_dataset_url.split("/")[-1]
        spectrum_parser = SpectrumParser()
        spectrum_parser.parse(os.path.join(NEXUS_DIR,f"{uuid}.nxs"))
        # Access the spectrum data
        for key in spectrum_parser.parsed_objects:
            spe = spectrum_parser.parsed_objects[key]
            print("Spectrum data", key, spe)
            #spe.plot()     
        
    else:
        pass