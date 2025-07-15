from typing import Generic, TypeVar, List, Dict
from pydantic.generics import GenericModel


T = TypeVar("T")


class StandardResponse(GenericModel, Generic[T]):
    status: int = 0
    response: T


StandardDictListResponse = StandardResponse[List[Dict]]