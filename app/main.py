from fastapi import FastAPI
from app.api import upload, process  # Import your endpoint modules
import os

app = FastAPI()

# Include your application configuration here if needed

# Include your API endpoint routers here
app.include_router(upload.router, prefix="", tags=["dataset"])
app.include_router(process.router, prefix="", tags=["process"])

for route in app.routes:
    print(f"Route: {route.path} | Methods: {route.methods}")

if __name__ == "__main__":
    import uvicorn
    
    # Start the FastAPI app using the Uvicorn server
    uvicorn.run(app, host="0.0.0.0", port=8000)