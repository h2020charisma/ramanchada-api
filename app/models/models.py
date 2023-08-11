from pydantic import BaseModel
from typing import Dict, Optional, Union


class Task(BaseModel):
    uri: Optional[str] = None
    id: str
    name: str
    error: Optional[str] = None
    policyError: Optional[str] = None
    status: str
    started: int
    completed: Optional[str] = None
    result: str
    errorCause: Optional[str] = None

tasks_db: Dict[str, Task] = {}    