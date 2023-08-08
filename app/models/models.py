from pydantic import BaseModel
from typing import Dict, Optional, Union

class Task(BaseModel):
    uri: str
    id: str
    name: str
    error: Optional[str] = None
    policyError: Optional[str] = None
    status: str
    started: int
    completed: int
    result: str
    errorCause: Optional[str] = None