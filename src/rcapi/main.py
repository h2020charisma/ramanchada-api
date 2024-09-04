from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from importlib.metadata import version
import time
from rcapi.api import upload, process, info, tasks, templates, query
from rcapi.models.models import tasks_db
import os 
from .config.app_config import initialize_dirs
from rcapi.services import template_service

config, UPLOAD_DIR, NEXUS_DIR, TEMPLATE_DIR = initialize_dirs(migrate=True)

try:
    package_version = version('ramanchada-api')
except Exception:
    package_version = 'Unknown'

app = FastAPI(
     title="Ramanchada API",
     version=package_version,
     description = "A web API for the RamanChada 2 Raman spectroscopy harmonisation library, incorporating the AMBIT/eNanoMapper data model"
)

# Include your application configuration here if needed

# Include your API endpoint routers here
app.include_router(upload.router, prefix="", tags=["dataset"])
app.include_router(process.router, prefix="", tags=["process"])
app.include_router(tasks.router, prefix="", tags=["task"])
app.include_router(info.router, prefix="", tags=["info"])
app.include_router(templates.router, prefix="", tags=["templates"])
app.include_router(query.router, prefix="", tags=["query"])

from h5grove import fastapi_utils
fastapi_utils.settings.base_dir = os.path.abspath(NEXUS_DIR)
app.include_router(fastapi_utils.router, prefix="/h5grove", tags=["h5grove"])

for route in app.routes:
    print(f"Route: {route.path} | Methods: {route.methods}")


def cleanup_tasks():
    current_time = int(time.time()*1000)  # Current time in seconds , milliseconds are fractional
    two_hours_ago = current_time - (2 * 60 * 60 * 1000)  # Two hours in milliseconds
    #two_hours_ago = current_time - (10 * 60 * 1000)  # 10 min  in milliseconds
    #print(current_time,two_hours_ago)
    tasks_to_remove = [task_id for task_id, task_data in tasks_db.items() if task_data.completed < two_hours_ago and task_data.status != "Running"]
    #print(tasks_to_remove)
    for task_id in tasks_to_remove:
        tasks_db.pop(task_id)

def cleanup_templates():
    template_service.cleanup(timedelta(hours=24*30*6))

scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_tasks, 'interval', minutes=120)  # Clean up every 120 minutes
scheduler.add_job(cleanup_templates, 'interval', hours=24)  # test, otherwise once a day would be ok
scheduler.start()

if __name__ == "__main__":
    import uvicorn
    
    # Start the FastAPI app using the Uvicorn server
    uvicorn.run(app, host="0.0.0.0", port=8000)
