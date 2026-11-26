"""Khuôn JSON gửi cho structured outputs của Anthropic và giới hạn độ phức tạp.

Anthropic biên dịch khuôn thành ngữ pháp; khuôn phức tạp bị từ chối 400 «Schema is too complex» hoặc «Grammar
compilation timed out» — và chỉ sau 90–180 giây chờ biên dịch. Tài liệu (structured-outputs → Schema complexity limits):
- tối đa 24 tham số tuỳ chọn (thuộc tính không nằm trong `required`) cộng trên mọi khuôn của một request;
- tối đa 16 tham số kiểu hợp (`anyOf` hoặc mảng kiểu như `["string","null"]`) — tốn kém theo cấp số mũ;
- ngoài ra còn giới hạn nội bộ về kích thước ngữ pháp: tham số tuỳ chọn «nhân đôi» không gian trạng thái, lồng nhau
  làm cộng dồn. Cách giảm: đánh dấu mọi thuộc tính là required (model tự ghi giá trị mặc định), giảm kiểu hợp, làm phẳng.

Vì vậy `anthropic_schema()` đánh dấu MỌI thuộc tính là required (Pydantic vẫn kiểm lại theo model gốc, nên trường có
mặc định vẫn hợp lệ), và `check_limits()` chặn ngay — không gọi mạng — khuôn vượt ngân sách của dự án (chặt hơn giới hạn
tài liệu một chút để chừa chỗ cho giới hạn nội bộ). Test `tests/test_ai_schemas.py` soát mọi khuôn dùng với `ai.run`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

from anthropic import transform_schema
from pydantic import BaseModel, BeforeValidator, WithJsonSchema

from app.ai.errors import AIError


def _empty_to_none(v: Any) -> Any:
    return None if isinstance(v, str) and not v.strip() else v


# Chuỗi có thể vắng: trong khuôn gửi AI là chuỗi thường (không phải kiểu hợp string|null — tốn ngữ pháp), AI ghi ""
# khi không có; Pydantic đổi "" thành None nên code dùng như `str | None`.
OptStr = Annotated[
    str | None,
    BeforeValidator(_empty_to_none),
    WithJsonSchema({"type": "string", "description": 'Ghi chuỗi rỗng "" nếu không có.'}),
]

# Giới hạn ghi trong tài liệu Anthropic (cộng trên mọi khuôn strict của một request).
DOC_MAX_OPTIONAL = 24
DOC_MAX_UNION = 16
# Ngân sách của dự án: thấp hơn giới hạn tài liệu vì còn giới hạn nội bộ (BriefParse 15 tuỳ chọn + 5 hợp đã bị từ chối).
MAX_OPTIONAL = 0  # anthropic_schema() luôn đánh dấu required → phải bằng 0
MAX_UNION = 10
MAX_DEPTH = 4  # số tầng object lồng nhau (gốc = 1)
MAX_PROPERTIES = 60  # tổng thuộc tính trên mọi object của khuôn


class AISchemaTooComplex(AIError):
    status_code = 500
    code = "ai_schema_too_complex"
    message = "Khuôn kết quả AI quá phức tạp (lỗi hệ thống), cần sửa code."


@dataclass(frozen=True)
class Complexity:
    optional: int
    unions: int
    depth: int
    properties: int

    def problems(self) -> list[str]:
        out = []
        if self.optional > MAX_OPTIONAL:
            out.append(f"{self.optional} thuộc tính tuỳ chọn (tối đa {MAX_OPTIONAL})")
        if self.unions > MAX_UNION:
            out.append(f"{self.unions} thuộc tính kiểu hợp/nullable (tối đa {MAX_UNION}, tài liệu {DOC_MAX_UNION})")
        if self.depth > MAX_DEPTH:
            out.append(f"lồng {self.depth} tầng object (tối đa {MAX_DEPTH})")
        if self.properties > MAX_PROPERTIES:
            out.append(f"{self.properties} thuộc tính (tối đa {MAX_PROPERTIES})")
        return out


def _force_required(node: Any) -> None:
    if isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            node["required"] = list(node["properties"])
            node["additionalProperties"] = False
        for v in node.values():
            _force_required(v)
    elif isinstance(node, list):
        for v in node:
            _force_required(v)


@lru_cache(maxsize=512)
def anthropic_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Khuôn gửi trong `output_config.format.schema`: biến đổi của SDK (bỏ ràng buộc không hỗ trợ, đóng object)
    + mọi thuộc tính đều required. Trả bản sao để nơi gọi không sửa nhầm bản trong cache."""
    schema = transform_schema(model)
    _force_required(schema)
    return schema


def _is_union(prop: dict[str, Any]) -> bool:
    return "anyOf" in prop or isinstance(prop.get("type"), list)


def complexity(schema: dict[str, Any]) -> Complexity:
    """Đếm trên khuôn đã biến đổi; `$ref` tới cùng một `$defs` được đếm mỗi lần dùng (ngữ pháp mở rộng như vậy)."""
    defs = schema.get("$defs", {})
    optional = unions = props = 0
    max_depth = 0

    def resolve(node: dict[str, Any]) -> dict[str, Any]:
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            return defs[ref.split("/")[-1]]
        return node

    def walk(node: Any, depth: int, stack: tuple[str, ...]) -> None:
        nonlocal optional, unions, props, max_depth
        if not isinstance(node, dict):
            return
        ref = node.get("$ref")
        if isinstance(ref, str):
            if ref in stack:  # đệ quy: API không hỗ trợ, coi như quá sâu
                max_depth = max(max_depth, MAX_DEPTH + 1)
                return
            walk(resolve(node), depth, (*stack, ref))
            return
        if isinstance(node.get("properties"), dict):
            depth += 1
            max_depth = max(max_depth, depth)
            required = set(node.get("required") or [])
            for name, prop in node["properties"].items():
                props += 1
                optional += name not in required
                unions += _is_union(prop)
                walk(prop, depth, stack)
        for key in ("anyOf", "allOf"):
            for child in node.get(key) or []:
                walk(child, depth, stack)
        if isinstance(node.get("items"), dict):
            walk(node["items"], depth, stack)

    walk(schema, 0, ())
    return Complexity(optional=optional, unions=unions, depth=max_depth, properties=props)


@lru_cache(maxsize=512)
def model_complexity(model: type[BaseModel]) -> Complexity:
    return complexity(anthropic_schema(model))


def check_limits(model: type[BaseModel]) -> None:
    """Khuôn vượt ngân sách → lỗi ngay (không chờ API biên dịch 90–180 giây rồi trả 400)."""
    problems = model_complexity(model).problems()
    if problems:
        raise AISchemaTooComplex(
            f"Khuôn kết quả {model.__name__} quá phức tạp cho AI: {'; '.join(problems)} (lỗi hệ thống)."
        )


def schema_copy(model: type[BaseModel]) -> dict[str, Any]:
    return copy.deepcopy(anthropic_schema(model))
