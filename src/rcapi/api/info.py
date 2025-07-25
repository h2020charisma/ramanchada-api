from fastapi import APIRouter
import subprocess

router = APIRouter()


@router.get("/info")
async def get_build_number():
    try:
        # Run the "git rev-parse HEAD" command to get the latest commit hash
        commit_hash = subprocess.check_output(
            ["git", "rev-parse", "HEAD"]).decode().strip()
        return {"build_number": commit_hash}
    except Exception as e:
        return {"error": str(e)}
