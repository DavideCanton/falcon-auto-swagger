from dataclasses import dataclass
from typing import Generic, TypeVar

import falcon


@dataclass
class AppInfo:
    title: str
    description: str
    version: str


T = TypeVar("T")


class TypedRequest(Generic[T], falcon.Request):
    pass


class TypedResponse(Generic[T], falcon.Response):
    pass
