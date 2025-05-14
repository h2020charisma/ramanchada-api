from pydantic import BaseModel
from typing import Dict, Optional


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
    result_uuid: Optional[str] = None
    errorCause: Optional[str] = None


tasks_db: Dict[str, Task] = {}
