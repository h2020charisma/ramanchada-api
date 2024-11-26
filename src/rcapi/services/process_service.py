import os
import time
from rcapi.models.models import Task  # Import your data models
from ..config.app_config import load_config


config = load_config()
UPLOAD_DIR = config.upload_dir
os.makedirs(UPLOAD_DIR, exist_ok=True)


async def process(task: Task, process_config: dict,
                  nexus_dataset_url: str, base_url: str):
    task.status = "Error"
    task.error = "Not implemented"
    task.completed = int(time.time() * 1000)


async def process_new(task: Task, nexus_dataset_url: str, base_url: str):
    task.status = "Error"
    task.completed = int(time.time() * 1000)
