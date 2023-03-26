import json
from dataclasses import dataclass, field
from functools import lru_cache
from inspect import Signature, getclosurevars, signature
from pathlib import Path
from typing import Any, Callable, get_args, get_origin

import falcon
from falcon.media.validators import jsonschema

from .schema import create_schema, param_type_to_json
from .utils import AppInfo, TypedRequest, TypedResponse

_ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}


@dataclass
class Context:
    paths: dict = field(default_factory=dict)
    schemas: dict[str, Any] = field(default_factory=dict)


def _process_schema(s: dict, context: Context):
    # TODO improve
    new_schema = json.loads(
        json.dumps(s).replace("#/definitions", "#/components/schemas")
    )

    for k, v in new_schema.pop("definitions", {}).items():
        if k not in context.schemas:
            context.schemas[k] = v

    return new_schema


@lru_cache(1)
def _jsonschema_validate_params() -> tuple[str, str]:
    s = signature(jsonschema.validate)
    return tuple(p for p in s.parameters)[:2]


def _try_get_jsonschema_from_decorator(
    func: Callable,
) -> tuple[dict | None, dict | None]:
    nonlocals = getclosurevars(func).nonlocals
    return tuple(nonlocals.get(p) for p in _jsonschema_validate_params())


def _infer_jsonschema(
    context: Context, func_sign: Signature
) -> tuple[dict | None, dict | None]:
    req_param, res_param, *_ = list(func_sign.parameters)

    res = []

    for param, exp_origin in [(req_param, TypedRequest), (res_param, TypedResponse)]:
        annotation = func_sign.parameters[param].annotation
        if get_origin(annotation) == exp_origin:
            res.append(create_schema(context.schemas, get_args(annotation)[0]))
        else:
            res.append(None)

    return tuple(res)


def _generate_method_info(
    context: Context,
    http_method: str,
    func: Callable,
    vars: list[str],
    *,
    add_parameters: bool,
):
    obj = {
        "description": func.__doc__,
        "responses": {"200": {}},
    }

    req = res = None
    func_sign = signature(func)

    jsonschemas = _try_get_jsonschema_from_decorator(func)
    if any(s is not None for s in jsonschemas):
        [req, res] = [_process_schema(s, context) for s in jsonschemas]
    else:
        req, res = _infer_jsonschema(context, func_sign)

    if req:
        obj["requestBody"] = {
            "description": "request",
            "required": True,
            "content": {"application/json": {"schema": req}},
        }

    if res:
        obj["responses"]["200"] = {
            "description": "response",
            "content": {"application/json": {"schema": res}},
        }

    ret = {http_method.lower(): obj}

    if add_parameters:
        ret["parameters"] = _generate_route_parameters(func_sign, vars)

    return ret


def _generate_route_parameters(func_sign: Signature, vars: list[str]):
    return [
        {
            "name": var,
            "in": "path",
            "description": var,
            "required": True,
            "schema": {
                "type": param_type_to_json(func_sign.parameters[var].annotation),
            },
            "style": "simple",
        }
        for var in vars
    ]


def _generate_paths(cur, context: Context, path, vars):
    if cur.is_var:
        name = cur.var_name
        vars = vars + [name]
        part = [f"{{{name}}}"]
    else:
        part = [cur.raw_segment]

    path = path + part

    if cur.method_map:
        route_def = {}

        for http_method, func in cur.method_map.items():
            if (
                func.__name__ == "method_not_allowed"
                or http_method not in _ALLOWED_METHODS
            ):
                continue

            route_def.update(
                _generate_method_info(
                    context,
                    http_method,
                    func,
                    vars,
                    add_parameters="parameters" in route_def,
                )
            )

        if not route_def.get("parameters"):
            route_def.pop("parameters", None)

        context.paths["/" + "/".join(path)] = route_def

    for child in cur.children:
        _generate_paths(child, context, path, vars)


def _generate_swagger(app: falcon.App, app_info: AppInfo):
    context = Context()
    for root in app._router._roots:
        _generate_paths(root, context, [], [])

    res = {
        "openapi": "3.0.3",
        "info": {
            "title": app_info.title,
            "description": app_info.description,
            "version": app_info.version,
        },
        "paths": context.paths,
    }
    if context.schemas:
        res["components"] = {"schemas": context.schemas}
    return res


def register_swagger(
    app: falcon.App,
    app_info: AppInfo,
    static_path: str | Path = "falcon_auto_swagger/static",
    url_prefix: str = "/api/docs/",
):
    if isinstance(static_path, str):
        static_path = Path(static_path)

    static_path = static_path.absolute()

    with (static_path / "swagger.json").open("w") as fo:
        j = _generate_swagger(app, app_info)
        json.dump(j, fo, indent=4)

    app.add_static_route(url_prefix, str(static_path), fallback_filename="index.html")
