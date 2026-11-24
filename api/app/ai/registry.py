"""Đăng ký tác vụ AI, hàm giả (provider `fake`) và móc khi chạm trần ngân sách."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.ai.types import TaskSpec, Tier

TASKS: dict[str, TaskSpec] = {}
FAKES: dict[str, Callable[..., Any]] = {}
_budget_hooks: list[Callable[[str, int, int], Awaitable[None]]] = []


def task(
    name: str,
    *,
    system: str = "",
    tier: Tier = "fast",
    web: bool = False,
    max_tokens: int | None = None,
    effort: str | None = None,
    description: str = "",
) -> TaskSpec:
    """Khai báo tác vụ (gọi ở mức module trong `ai_tasks.py`). Prompt hệ thống phải ổn định để tận dụng cache."""
    spec = TaskSpec(
        name=name, system=system, tier=tier, web=web, max_tokens=max_tokens, effort=effort, description=description
    )
    TASKS[name] = spec
    return spec


def fake(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Hàm giả cho provider `fake`: nhận `input` (đúng kiểu đã truyền vào ai.run), trả Pydantic hoặc dict hợp schema.
    Hàm có thể sync hoặc async. Không đăng ký thì dùng hàm giả mặc định sinh dữ liệu theo schema."""

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        FAKES[name] = fn
        return fn

    return deco


def on_budget_exceeded(fn: Callable[[str, int, int], Awaitable[None]]) -> Callable[[str, int, int], Awaitable[None]]:
    """Đăng ký hàm gọi khi chạm trần: fn(month_key, spent_vnd, budget_vnd)."""
    _budget_hooks.append(fn)
    return fn


def budget_hooks() -> list[Callable[[str, int, int], Awaitable[None]]]:
    return list(_budget_hooks)
