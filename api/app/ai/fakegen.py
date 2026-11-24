"""Sinh dữ liệu giả hợp schema Pydantic (xác định) cho provider `fake` khi tác vụ chưa có hàm giả riêng."""

from __future__ import annotations

import datetime as dt
import enum
import types
import typing
import uuid
from decimal import Decimal
from typing import Any

import annotated_types as at
from pydantic import BaseModel
from pydantic.fields import FieldInfo


def _bounds(meta: list[Any]) -> dict[str, Any]:
    b: dict[str, Any] = {}
    for m in meta:
        for attr in ("ge", "gt", "le", "lt", "min_length", "max_length"):
            v = getattr(m, attr, None)
            if v is not None:
                b[attr] = v
        if isinstance(m, at.Interval):
            for attr in ("ge", "gt", "le", "lt"):
                if getattr(m, attr, None) is not None:
                    b[attr] = getattr(m, attr)
    return b


def _number(b: dict[str, Any], default: float) -> float:
    lo = b.get("ge", b["gt"] + 1 if "gt" in b else None)
    hi = b.get("le", b["lt"] - 1 if "lt" in b else None)
    if lo is not None and hi is not None:
        return (lo + hi) / 2
    if lo is not None:
        return max(lo, default)
    if hi is not None:
        return min(hi, default)
    return default


def fake_value(tp: Any, name: str = "giá trị", meta: list[Any] | None = None, depth: int = 0) -> Any:
    meta = list(meta or [])
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin is typing.Annotated:
        return fake_value(args[0], name, meta + list(args[1:]), depth)
    if origin in (typing.Union, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        return fake_value(non_none[0], name, meta, depth) if non_none else None
    if origin is typing.Literal:
        return args[0]
    b = _bounds(meta)
    if tp is Any:
        return f"Mẫu {name}"
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return fake_model(tp, depth + 1)
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        return next(iter(tp)).value
    if tp is bool:
        return False
    if tp is int:
        return int(_number(b, 1))
    if tp is float:
        return float(_number(b, 0.5))
    if tp is Decimal:
        return Decimal(str(_number(b, 1)))
    if tp is str:
        s = f"Mẫu {name}"
        if "max_length" in b:
            s = s[: b["max_length"]]
        if len(s) < b.get("min_length", 0):
            s = s.ljust(b["min_length"], ".")
        return s
    if tp is uuid.UUID:
        return uuid.UUID(int=depth + 1)
    if tp is dt.datetime:
        return dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    if tp is dt.date:
        return dt.date(2026, 1, 1)
    if origin in (list, set, tuple, typing.Sequence) or tp in (list, set, tuple):
        inner = args[0] if args else str
        n = max(1, b.get("min_length", 1)) if depth < 3 else b.get("min_length", 0)
        return [fake_value(inner, name, None, depth + 1) for _ in range(n)]
    if origin is dict or tp is dict:
        return {}
    return None


def fake_model[T: BaseModel](model: type[T], depth: int = 0) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for fname, info in model.model_fields.items():
        assert isinstance(info, FieldInfo)
        if not info.is_required():
            default = info.get_default(call_default_factory=True)
            if default is not None and default != [] and default != {}:
                out[fname] = default
                continue
        out[fname] = fake_value(info.annotation, fname, list(info.metadata), depth)
    return out


def fake_output[T: BaseModel](model: type[T]) -> T:
    return model.model_validate(fake_model(model))
