from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

import falcon


@dataclass
class AppInfo:
    title: str
    description: str
    version: str


T = TypeVar("T")


class TypedRequest(Generic[T], falcon.Request):
    media: T


class TypedResponse(Generic[T], falcon.Response):
    media: T


@dataclass
class Context:
    paths: dict = field(default_factory=dict)
    schemas: dict[str, Any] = field(default_factory=dict)
