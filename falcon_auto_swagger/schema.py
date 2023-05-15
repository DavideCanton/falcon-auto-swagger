import json
from dataclasses import dataclass
from functools import lru_cache
from inspect import getclosurevars, signature
from typing import Callable, Sequence, TypedDict, get_args

from falcon.media.validators.jsonschema import validate

from falcon_auto_swagger.typed_dict_utils import get_required

from .utils import Context


@lru_cache(1)
def _jsonschema_validate_params() -> tuple[str, str]:
    s = signature(validate)
    return tuple(p for p in s.parameters)[:2]


def converter_to_json_type(type: str, *additional: str) -> dict:
    # TODO extend with converters?
    match type:
        case "int":
            return {"type": "integer"}
        case "dt":
            if additional[0] is not None:
                raise ValueError("Unsupported custom formats")
            return {"type": "string", "format": "date-time"}
        case "uuid":
            return {"type": "string", "format": "uuid"}
        case _:
            return {"type": "string"}


@dataclass
class Simple:
    base_type: str


@dataclass
class Complex:
    base_type: dict
    defs: dict


def _ref(name):
    return f"#/components/schemas/{name}"


@lru_cache(100)
def _type_to_json(param: type) -> Simple | Complex:
    # TODO extend
    match param:
        # TODO int and float should be generalized to Integral and Real maybe
        # excluding complex
        case t if issubclass(t, int):
            return Simple("integer")
        case t if issubclass(t, float):
            return Simple("number")
        case t if issubclass(t, Sequence):
            match _type_to_json(get_args(t)[0]):
                case Simple(base_type=b):
                    items = {"type": b}
                    defs = {}
                case Complex(defs=defs, base_type=base_type):
                    items = {"$ref": _ref("foo")}
            return Complex({"type": "array", "items": items}, defs | {"foo": base_type})
        case t if issubclass(t, TypedDict):
            f = get_required(t)
            return Complex(
                {
                    "type": "object",
                    "properties": {k: {"type": "integer"} for k, v in f.items()},
                },
                {},
            )
        case _:
            return Simple("string")


def create_schema(types_index: dict, type: type):
    info = _type_to_json(type)
    if isinstance(info, Simple):
        return {"type": info.base_type}

    name = type.__name__
    types_index.update(info.defs)

    return {"$ref": _ref(name)}


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
