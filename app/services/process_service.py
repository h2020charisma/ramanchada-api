import time
from app.models.models import Task  # Import your data models

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
    



