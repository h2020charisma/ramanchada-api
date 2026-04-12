from fastapi import FastAPI, Request
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import timedelta
from importlib.metadata import version
import time
from rcapi.api import (
    convertor, upload, process, info, tasks, query, hsds_dataset,
    mcp, aop
)
from rcapi.models.models import tasks_db
import os.path
from .config.app_config import initialize_dirs
from fastapi.responses import JSONResponse
import logging
import traceback
from h5grove import fastapi_utils

config, UPLOAD_DIR, NEXUS_DIR, TEMPLATE_DIR = initialize_dirs(migrate=True)

try:
    package_version = version('ramanchada-api')
except Exception:
    package_version = 'Unknown'


app = FastAPI(
     title="Ramanchada API",
     version=package_version,
     description="A web API for the RamanChada 2 Raman spectroscopy harmonisation library, incorporating the AMBIT/eNanoMapper data model"
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    stack_trace = traceback.format_exc()
    logging.error(f"Unhandled exception: {str(exc)}\nStack trace:\n{stack_trace}")
    print(f"Unhandled exception: {str(exc)}\nStack trace:\n{stack_trace}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )


def cleanup_tasks():
    current_time = int(time.time()*1000)
    two_hours_ago = current_time - (2 * 60 * 60 * 1000)
    tasks_to_remove = [
        task_id for task_id, task_data in tasks_db.items()
        if task_data.completed < two_hours_ago and task_data.status != "Running"
    ]
    for task_id in tasks_to_remove:
        tasks_db.pop(task_id)


fastapi_utils.settings.base_dir = os.path.abspath(NEXUS_DIR)
app.include_router(upload.router, prefix="", tags=["dataset"])
app.include_router(process.router, prefix="", tags=["process"])
app.include_router(tasks.router, prefix="", tags=["task"])
app.include_router(info.router, prefix="", tags=["info"])
app.include_router(query.router, prefix="/db", tags=["db"])
app.include_router(convertor.router, prefix="/db", tags=["db"])
app.include_router(hsds_dataset.router, prefix="/db", tags=["db"])
app.include_router(aop.router, prefix="/db", tags=["aop"])        # ← new
app.include_router(fastapi_utils.router, prefix="/h5grove", tags=["h5grove"])
app.include_router(mcp.router, tags=["mcp"])

for route in app.routes:
    print(f"Route: {route.path} | Methods: {route.methods}")


scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_tasks, 'interval', minutes=120)
scheduler.start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
