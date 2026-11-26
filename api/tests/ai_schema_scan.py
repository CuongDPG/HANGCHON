"""Tìm mọi khuôn ra (tham số thứ ba / `output=`) của các lời gọi `ai.run(...)` trong `app/` bằng AST.

Dùng chung cho test `test_ai_schemas.py`. Trả [(vị trí, model)] hoặc ném lỗi khi không xác định được khuôn — để một lời
gọi mới không lọt khỏi phép soát.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

from pydantic import BaseModel

APP = Path(__file__).resolve().parents[1] / "app"


def _module_name(path: Path) -> str:
    rel = path.relative_to(APP.parent).with_suffix("")
    return ".".join(rel.parts)


def _is_ai_run(call: ast.Call) -> bool:
    f = call.func
    return isinstance(f, ast.Attribute) and f.attr == "run" and isinstance(f.value, ast.Name) and f.value.id == "ai"


def _output_expr(call: ast.Call) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == "output":
            return kw.value
    return call.args[2] if len(call.args) >= 3 else None


def find_output_models() -> list[tuple[str, type[BaseModel]]]:
    found: list[tuple[str, type[BaseModel]]] = []
    unresolved: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _is_ai_run(n)]
        if not calls:
            continue
        mod = importlib.import_module(_module_name(path))
        # tên nhập trong thân hàm (`from app.modules.x.ai_io import Out` đặt trong hàm) cũng tính
        local_imports = {
            (a.asname or a.name): n.module
            for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom) and n.module
            for a in n.names
        }
        for call in calls:
            where = f"{path.relative_to(APP.parent)}:{call.lineno}"
            expr = _output_expr(call)
            obj = None
            if isinstance(expr, ast.Name):
                obj = getattr(mod, expr.id, None)
                if obj is None and expr.id in local_imports:
                    obj = getattr(importlib.import_module(local_imports[expr.id]), expr.id, None)
            elif isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
                obj = getattr(getattr(mod, expr.value.id, None), expr.attr, None)
            if isinstance(obj, type) and issubclass(obj, BaseModel):
                found.append((where, obj))
            else:
                unresolved.append(where)
    if unresolved:
        raise AssertionError("Không xác định được khuôn ra của ai.run tại: " + ", ".join(unresolved))
    return found
