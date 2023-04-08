import json
from inspect import Signature, signature
from pathlib import Path
from typing import Callable, cast, get_args, get_origin

from falcon import App
from falcon.responders import create_method_not_allowed
from falcon.routing.compiled import CompiledRouter, CompiledRouterNode

from .schema import (
    converter_to_json_type,
    create_schema,
    try_get_jsonschema_from_decorator,
)
from .utils import AppInfo, Context, TypedRequest, TypedResponse

_ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}
_NOT_ALLOWED_RESPONDERS = {
    create_method_not_allowed([], asgi=asgi).__name__ for asgi in (True, False)
}
_var_type = tuple[str, ...]


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


def _resp_message_for_status(status: int) -> str:
    return f"Response for HTTP {status}"


def _generate_method_info(
    context: Context,
    http_method: str,
    func: Callable,
    vars: list[_var_type],
    *,
    add_parameters: bool,
):
    obj = {"description": func.__doc__, "responses": {}}

    if jsonschemas := try_get_jsonschema_from_decorator(context, func):
        req, res = jsonschemas
    else:
        func_sign = signature(func)
        req, res = _infer_jsonschema(context, func_sign)

    if req:
        obj["requestBody"] = {
            "description": "request",
            "required": True,
            "content": {"application/json": {"schema": req}},
        }

    if res:
        obj["responses"]["200"] = {
            "description": _resp_message_for_status(200),
            "content": {"application/json": {"schema": res}},
        }

    ret = {http_method.lower(): obj}

    if add_parameters:
        ret["parameters"] = _generate_route_parameters(vars)

    return ret


def _generate_route_parameters(vars: list[_var_type]):
    return [
        {
            "name": var,
            "in": "path",
            "description": var,
            "required": True,
            "schema": {
                # TODO infer more type properties from the converter specified in the route
                # like "id:int(2, min=50)"
                **converter_to_json_type(*rest),
            },
            "style": "simple",
        }
        for var, *rest in vars
    ]


def _generate_paths(
    cur: CompiledRouterNode,
    context: Context,
    path: list[str],
    vars: list[_var_type],
):
    # TODO check this method logic to avoid unnecessary concatenation of lists
    # and in general to avoid recursion

    if cur.is_var:
        if cur.var_converter_map:
            # cur.var_converter_map is a list with a single tuple
            # containing (var name, converter name, converter args csv list)
            # TODO check if many tuples in this list can appear
            var = cast(_var_type, cur.var_converter_map[0])
        else:
            # if cur.var_converter_map is empty, consider the variable as a string
            var = cast(_var_type, (cur.var_name, "str"))

        name = var[0]
        vars = vars + [var]
        part = [f"{{{name}}}"]
    else:
        part = [cur.raw_segment]

    path = path + part

    if method_map := cur.method_map:
        method_map: dict[str, Callable]

        route_def = {}

        for http_method, func in method_map.items():
            if (
                func.__name__ in _NOT_ALLOWED_RESPONDERS
                or http_method not in _ALLOWED_METHODS
            ):
                continue

            route_def.update(
                _generate_method_info(
                    context,
                    http_method,
                    func,
                    vars,
                    add_parameters="parameters" not in route_def,
                )
            )

        if not route_def.get("parameters"):
            route_def.pop("parameters", None)

        context.paths["/" + "/".join(path)] = route_def

    for child in cur.children:
        _generate_paths(child, context, path, vars)


def _generate_swagger(app: App, app_info: AppInfo):
    context = Context()
    router = app._router

    # TODO error if router is not a compiled or check if it works with other routers
    assert isinstance(router, CompiledRouter)

    for root in router._roots:
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
    app: App,
    app_info: AppInfo,
    static_path: str | Path,
    url_prefix: str = "/api/docs/",
):
    if isinstance(static_path, str):
        static_path = Path(static_path)

    static_path = static_path.absolute()

    with (static_path / "swagger.json").open("w") as out_file:
        swagger_json = _generate_swagger(app, app_info)
        json.dump(swagger_json, out_file, indent=4)

    app.add_static_route(url_prefix, str(static_path), fallback_filename="index.html")
