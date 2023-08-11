from pydantic import BaseModel
from typing import Dict, Optional, Union

tasks_db = {}

class Task(BaseModel):
    uri: Optional[str] = None
    id: str
    name: str
    error: Optional[str] = None
    policyError: Optional[str] = None
    status: str
    started: int
    completed: int
    result: str
    errorCause: Optional[str] = None