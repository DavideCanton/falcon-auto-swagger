import json
from inspect import Signature, signature
from pathlib import Path
from typing import Callable, get_args, get_origin

from falcon import App
from falcon.responders import create_method_not_allowed
from falcon.routing.compiled import CompiledRouter, CompiledRouterNode

from .schema import create_schema, param_type_to_json, try_get_jsonschema_from_decorator
from .utils import AppInfo, Context, TypedRequest, TypedResponse

_ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}
_NOT_ALLOWED_RESPONDERS = {
    create_method_not_allowed([], asgi=asgi).__name__ for asgi in (True, False)
}


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
    vars: list[str],
    *,
    add_parameters: bool,
):
    obj = {"description": func.__doc__, "responses": {}}

    func_sign = signature(func)

    if jsonschemas := try_get_jsonschema_from_decorator(context, func):
        req, res = jsonschemas
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
            "description": _resp_message_for_status(200),
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
                # TODO infer more type properties from the converter specified in the route
                # like "id:int(2, min=50)"
                "type": param_type_to_json(func_sign.parameters[var].annotation),
            },
            "style": "simple",
        }
        for var in vars
    ]


def _generate_paths(
    cur: CompiledRouterNode,
    context: Context,
    path: list[str],
    vars: list[str],
):
    if cur.is_var:
        name = cur.var_name
        vars = vars + [name]
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
    # TODO error
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
