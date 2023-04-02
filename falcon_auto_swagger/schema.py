import json
from functools import lru_cache
from inspect import getclosurevars, signature
from typing import Callable, Sequence

from falcon.media.validators.jsonschema import validate

from .utils import Context


@lru_cache(1)
def _jsonschema_validate_params() -> tuple[str, str]:
    s = signature(validate)
    return tuple(p for p in s.parameters)[:2]


def param_type_to_json(param: str | type):
    # TODO extend?
    match param:
        case t if t == "int" or issubclass(t, int):
            return "integer"
        case _:
            return "string"


def type_to_json(param: type):
    # TODO extend
    match param:
        case t if issubclass(t, int):
            return "integer"
        case t if issubclass(t, Sequence):
            return "array"
        case _:
            return "object"


def create_schema(types_index: dict, type: type):
    if (t := type_to_json(type)) not in {"array", "object"}:
        return {"type": t}

    name = type.__name__
    types_index.update({})

    return {"$ref": f"#/components/schemas/{name}"}


def process_schema(s: dict, context: Context) -> dict:
    # TODO improve
    new_schema = json.loads(
        json.dumps(s).replace("#/definitions", "#/components/schemas")
    )

    for k, v in new_schema.pop("definitions", {}).items():
        if k not in context.schemas:
            context.schemas[k] = v

    return new_schema


def try_get_jsonschema_from_decorator(
    context: Context,
    func: Callable,
) -> tuple[dict | None, dict | None] | None:
    """Retrieves the json schema from the decorator specified on route responder method."

    Args:
        func (Callable): the route responder.

    Returns:
        tuple[dict | None, dict | None] | None: the json schemas for request and response.
        Returns None if there is no decorator on the route.
    """

    cur = func

    while cur:
        closure = getclosurevars(cur)
        # use the presence of falcon.media.validators.jsonschema.validate between
        # globals of the func as heuristic
        if closure.globals.get("validate") is validate:
            nonlocals = closure.nonlocals
            return tuple(
                process_schema(nonlocals.get(p), context)
                for p in _jsonschema_validate_params()
            )
        else:
            cur = getattr(cur, "__wrapped__", None)

    return None
