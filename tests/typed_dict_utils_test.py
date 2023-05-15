import sys
from typing import TypedDict

from falcon_auto_swagger.typed_dict_utils import get_optional, get_required

_GT_310 = sys.version_info >= (3, 11)

if _GT_310:
    from typing import NotRequired, Required
else:
    from typing_extensions import NotRequired, Required


class C1(TypedDict):
    a: int
    b: NotRequired[list[int]]


class C2(TypedDict, total=False):
    a: Required[int]
    b: list[int]


def test_get_required():
    assert get_required(C1) == {"a": int}
    assert get_required(C2) == {"a": int}


def test_get_optional():
    assert get_optional(C1) == {"b": list[int]}
    assert get_optional(C2) == {"b": list[int]}
