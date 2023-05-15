import sys
from inspect import get_annotations
from typing import TypedDict, get_args, get_origin

_GT_310 = sys.version_info >= (3, 11)


if _GT_310:

    def get_required(class_: type[TypedDict]) -> dict[str, type]:
        return class_.__required_keys__

    def get_optional(class_: type[TypedDict]) -> dict[str, type]:
        return class_.__optional_keys__

else:
    from typing_extensions import NotRequired, Required

    def get_required(class_: type[TypedDict]) -> dict[str, type]:
        ann = get_annotations(class_)

        ret = {}
        total = class_.__total__

        for k, v in ann.items():
            orig = get_origin(v)
            if orig is Required:
                ret[k] = get_args(v)[0]
            elif orig is not NotRequired and total:
                ret[k] = v

        return ret

    def get_optional(class_: type[TypedDict]) -> dict[str, type]:
        ann = get_annotations(class_)

        ret = {}
        total = class_.__total__

        for k, v in ann.items():
            orig = get_origin(v)
            if orig is NotRequired:
                ret[k] = get_args(v)[0]
            elif orig is not Required and not total:
                ret[k] = v

        return ret
