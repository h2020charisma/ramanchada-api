import re

from fastapi import APIRouter
from rcapi.config.app_config import initialize_dirs

config, UPLOAD_DIR, NEXUS_DI, TEMPLATE_DIR = initialize_dirs()
router = APIRouter()


@router.get("/info")
async def get_build_number():
    try:
        with open("__rcapi_version__.txt") as f:
            rcapi_version_raw = f.readline().strip("\n")
            # Very basic sanitization, just in case.
            rcapi_version = re.sub(r"[^ -~]", "", rcapi_version_raw)
        return {"build_number": rcapi_version, "config": config}
    except FileNotFoundError:
        return {"build_number": "unknown", "config": config}
    except Exception as e:
        return {"error": str(e)}
