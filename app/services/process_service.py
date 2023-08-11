import os
import uuid
import time
import shutil
from app.models.models import Task  # Import your data models


async def process(task : Task,nexus_dataset_url: str):
    task.status = "Completed"
    task.completed=int(time.time() * 1000)
    