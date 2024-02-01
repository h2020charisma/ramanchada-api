from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import time
from app.api import upload, process, info, tasks, templates
from app.models.models import tasks_db
from pydantic import BaseSettings
import os 
from .config.app_config import initialize_dirs

config, UPLOAD_DIR, NEXUS_DIR, TEMPLATE_DIR = initialize_dirs(migrate=True)

app = FastAPI(
     title="Ramanchada API",
     version="0.0.1",
     description = "A web API for the RamanChada 2 Raman spectroscopy harmonisation library, incorporating the AMBIT/eNanoMapper data model"
)

# Include your application configuration here if needed

# Include your API endpoint routers here
app.include_router(upload.router, prefix="", tags=["dataset"])
app.include_router(process.router, prefix="", tags=["process"])
app.include_router(tasks.router, prefix="", tags=["task"])
app.include_router(info.router, prefix="", tags=["info"])
app.include_router(templates.router, prefix="", tags=["templates"])


from h5grove import fastapi_utils
fastapi_utils.settings.base_dir = os.path.abspath(NEXUS_DIR)
app.include_router(fastapi_utils.router, prefix="/h5grove", tags=["h5grove"])

for route in app.routes:
    print(f"Route: {route.path} | Methods: {route.methods}")


def cleanup_tasks():
    current_time = int(time.time() * 1000)  # Current time in milliseconds
    two_hours_ago = current_time - (2 * 60 * 60 * 1000)  # Two hours in milliseconds
    tasks_to_remove = [task_id for task_id, task_data in tasks_db.items() if task_data.started < two_hours_ago and task_data.status != "Running"]
    for task_id in tasks_to_remove:
        tasks_db.pop(task_id)

def cleanup_templates():
    templates.cleanup(age_hours = 24)

scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_tasks, 'interval', minutes=30)  # Clean up every 30 minutes
#scheduler.add_job(cleanup_templates, 'interval', hours=4)  # test, otherwise once a day would be ok
scheduler.start()

if __name__ == "__main__":
    import uvicorn
    
    # Start the FastAPI app using the Uvicorn server
    uvicorn.run(app, host="0.0.0.0", port=8000)
