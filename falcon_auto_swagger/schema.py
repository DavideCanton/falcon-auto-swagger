from typing import Sequence


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
