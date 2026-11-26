"""Mọi khuôn ra dùng với `ai.run` phải nằm trong giới hạn độ phức tạp của structured outputs (app/ai/schema.py).

Lần chạy thật đầu tiên: BriefParse (15 trường tuỳ chọn) và _ProductOut (23 tuỳ chọn, 15 kiểu hợp) bị Anthropic trả 400
«Schema is too complex» sau 90–180 giây — test với provider fake không bắt được. Test này soát tĩnh khuôn thật sự gửi đi.
"""

from __future__ import annotations

from typing import Any

from app.ai.schema import DOC_MAX_OPTIONAL, DOC_MAX_UNION, anthropic_schema, model_complexity
from tests.ai_schema_scan import find_output_models

UNSUPPORTED = ("minimum", "maximum", "minLength", "maxLength", "oneOf", "not", "pattern")


def _schema_problems(node: Any, path: str) -> list[str]:
    out: list[str] = []
    if isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            if node.get("additionalProperties") is not False:
                out.append(f"{path}: object chưa đóng")
            if set(node.get("required") or []) != set(node["properties"]):
                out.append(f"{path}: còn thuộc tính tuỳ chọn")
        out += [f"{path}: {k}" for k in UNSUPPORTED if k in node]
        for k, v in node.items():
            if k in ("properties", "$defs"):  # bảng tên → khuôn: tên thuộc tính không phải từ khoá
                for name, child in v.items():
                    out += _schema_problems(child, f"{path}/{k}/{name}")
            else:
                out += _schema_problems(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += _schema_problems(v, f"{path}/{i}")
    return out


def test_every_ai_output_schema_within_limits() -> None:
    found = find_output_models()
    assert len(found) >= 40  # quét được các lời gọi (đừng để phép soát rỗng)
    bad = {}
    for where, model in found:
        c = model_complexity(model)
        problems = c.problems()
        if c.unions > DOC_MAX_UNION or c.optional > DOC_MAX_OPTIONAL:
            problems.append("vượt giới hạn tài liệu Anthropic")
        if problems:
            bad[f"{model.__name__} ({where})"] = problems
    assert not bad, bad


def test_every_ai_output_schema_is_strict_and_supported() -> None:
    bad = {}
    for where, model in find_output_models():
        problems = _schema_problems(anthropic_schema(model), model.__name__)
        if problems:
            bad[where] = problems
    assert not bad, bad
