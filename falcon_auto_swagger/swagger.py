import json
from dataclasses import dataclass, field
from inspect import getclosurevars, signature
from pathlib import Path
from typing import Any, Callable, get_args, get_origin

import falcon

from .schema import create_schema, param_type_to_json
from .utils import AppInfo, TypedRequest, TypedResponse

_ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}


@dataclass
class Context:
    paths: dict = field(default_factory=dict)
    schemas: dict[str, Any] = field(default_factory=dict)


def _process_schema(s: dict, context: Context):
    # TODO improve
    new_schema = json.loads(json.dumps(s).replace("#/definitions", "#/components/schemas"))

    for k, v in new_schema.pop("definitions", {}).items():
        if k not in context.schemas:
            context.schemas[k] = v

    return new_schema


def _gen(
    context: Context,
    route_def: dict[str, Any],
    http_method: str,
    func: Callable,
    vars: list[str],
):
    obj = {
        "description": func.__doc__,
        "responses": {"200": {}},
    }

    nl = getclosurevars(func).nonlocals
    req_schema = nl.get("req_schema")
    resp_schema = nl.get("resp_schema")

    s = signature(func)
    k = list(s.parameters)
    req_param = k[0]
    res_param = k[1]
    req = res = None

    if req_schema is not None or resp_schema is not None:
        req = _process_schema(req_schema, context)
        res = _process_schema(resp_schema, context)

    else:
        rqa = s.parameters[req_param].annotation
        if get_origin(rqa) == TypedRequest:
            req = create_schema(context.schemas, get_args(rqa)[0])

        rsa = s.parameters[res_param].annotation
        if get_origin(rsa) == TypedResponse:
            res = create_schema(context.schemas, get_args(rsa)[0])

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

    route_def[http_method.lower()] = obj

    _add_parameters(route_def, func, vars)


def _add_parameters(route_def, func, vars):
    if vars:
        s = signature(func)
        route_def["parameters"] = [
            {
                "name": var,
                "in": "path",
                "description": var,
                "required": True,
                "schema": {
                    "type": param_type_to_json(s.parameters[var].annotation),
                },
                "style": "simple",
            }
            for var in vars
        ]


def _generate_paths(cur, context: Context, path=[], vars=[]):
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

            _gen(context, route_def, http_method, func, vars)

        context.paths["/" + "/".join(path)] = route_def

    for child in cur.children:
        _generate_paths(child, context, path, vars)


def _generate_swagger(app: falcon.App, app_info: AppInfo):
    context = Context()
    for root in app._router._roots:
        _generate_paths(root, context)

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
