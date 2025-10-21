from typing import Generic, TypeVar, List, Dict
from pydantic import BaseModel


T = TypeVar("T")


class StandardResponse(BaseModel, Generic[T]):
    status: int = 0
    numFound: int = 0
    start: int = 0
    response: T


StandardDictListResponse = StandardResponse[List[Dict]]