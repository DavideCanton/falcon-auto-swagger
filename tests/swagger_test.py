import json
from pathlib import Path

import falcon
import pytest
from falcon.media.validators import jsonschema

from falcon_auto_swagger import AppInfo, TypedRequest
from falcon_auto_swagger.swagger import _generate_swagger


def read_json(path: str) -> dict:
    f = Path(__file__).parent / "schemas" / path
    with f.open() as fo:
        return json.load(fo)


class Res:
    def on_get(self, request: TypedRequest[int], response):
        "GET"

    @jsonschema.validate(
        req_schema=read_json("req_schema.json"),
        resp_schema=read_json("req_schema.json"),
    )
    def on_post(self, request, response) -> None:
        "POST"

    def on_get_id(self, request, response):
        "GET ID"

    def on_get_id2(self, request, response):
        "GET ID2"


app = falcon.App()
app.add_route("/res", res := Res())
app.add_route("/res/{id}", res, suffix="id")
app.add_route("/res/{id}/foo/{id2:int}", res, suffix="id2")


def test_foo():
    pytest.skip()
    info = AppInfo(title="foo", description="bar", version="0.1.0")
    sw = _generate_swagger(app, info)
    assert sw == {}
