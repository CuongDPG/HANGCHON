"""Sổ đăng ký của control: hành động (+ handler/hoàn tác/trả lại), stat provider cho «Hôm nay», lệnh bằng lời, cài đặt.

Module khai báo trong `app/modules/<ten>/actions.py` (tự nạp khi khởi động)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.control.models import AutonomyLevel

if TYPE_CHECKING:
    from app.modules.control.models import AIActivity, ApprovalItem, User


# ---- hành động ---------------------------------------------------------------------------------------------------


@dataclass
class ActionContext:
    """Truyền vào handler. `payload` đã gộp phần chị sửa (nếu có)."""

    db: AsyncSession
    action: str
    payload: dict[str, Any]
    preview: dict[str, Any]
    mode: Literal["auto", "approved"]
    item: ApprovalItem | None = None
    user: User | None = None
    ref_type: str | None = None
    ref_id: uuid.UUID | None = None


@dataclass
class HandlerResult:
    result: dict[str, Any] | None = None
    undo: dict[str, Any] | None = None  # dữ liệu cho hàm hoàn tác; None = không hoàn tác được
    summary: str | None = None
    ref_type: str | None = None
    ref_id: uuid.UUID | None = None


@dataclass
class UndoContext:
    db: AsyncSession
    activity: AIActivity
    undo: dict[str, Any]
    user: User | None


@dataclass
class ReturnContext:
    """Truyền vào hàm xử lý khi chị trả lại: module có thể soạn lại theo lời nhắn."""

    db: AsyncSession
    item: ApprovalItem
    note: str
    user: User | None


Handler = Callable[[ActionContext], Awaitable[HandlerResult | dict[str, Any] | None]]
Undoer = Callable[[UndoContext], Awaitable[None]]
OnReturn = Callable[[ReturnContext], Awaitable[None]]


@dataclass
class ActionSpec:
    key: str
    label: str
    group: str
    default_level: AutonomyLevel = AutonomyLevel.ASK
    locked: bool = False
    customer_facing: bool = False
    description: str = ""
    handler: Handler | None = None
    undo: Undoer | None = None
    on_return: OnReturn | None = None

    @property
    def module(self) -> str:
        return self.key.split(".", 1)[0]


ACTIONS: dict[str, ActionSpec] = {}


def register_action(
    key: str,
    label: str,
    group: str,
    *,
    default: AutonomyLevel | str = AutonomyLevel.ASK,
    locked: bool = False,
    customer_facing: bool = False,
    description: str = "",
) -> ActionSpec:
    """Khai báo hành động. `locked=True` → luôn hỏi chị (khiếu nại/đổi trả/hoàn tiền, đặt hàng/trả tiền NCC).

    Quy tắc thận trọng: việc nội bộ `default="auto"`, mọi thứ khách nhìn thấy `customer_facing=True, default="ask"`."""
    if "." not in key:
        raise ValueError("Khoá hành động phải dạng '<module>.<viec>'")
    level = AutonomyLevel(default)
    if locked:
        level = AutonomyLevel.LOCKED_ASK
    elif level == AutonomyLevel.LOCKED_ASK:
        locked = True
    existing = ACTIONS.get(key)
    spec = ActionSpec(
        key=key,
        label=label,
        group=group,
        default_level=level,
        locked=locked,
        customer_facing=customer_facing,
        description=description,
        handler=existing.handler if existing else None,
        undo=existing.undo if existing else None,
        on_return=existing.on_return if existing else None,
    )
    ACTIONS[key] = spec
    return spec


def _spec(key: str) -> ActionSpec:
    if key not in ACTIONS:
        raise KeyError(f"Hành động chưa đăng ký: {key} (gọi register_action trước)")
    return ACTIONS[key]


def handler(action: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _spec(action).handler = fn
        return fn

    return deco


def undoer(action: str) -> Callable[[Undoer], Undoer]:
    def deco(fn: Undoer) -> Undoer:
        _spec(action).undo = fn
        return fn

    return deco


def on_returned(action: str) -> Callable[[OnReturn], OnReturn]:
    def deco(fn: OnReturn) -> OnReturn:
        _spec(action).on_return = fn
        return fn

    return deco


# ---- số liệu «Hôm nay» -------------------------------------------------------------------------------------------


class Stat(BaseModel):
    key: str
    label: str
    value: int | float | str
    format: Literal["number", "vnd", "percent", "text"] = "number"
    hint: str | None = None
    href: str | None = None
    order: int = 100


StatFn = Callable[[AsyncSession], Awaitable[list[Stat] | Stat]]


@dataclass
class StatProvider:
    key: str
    fn: StatFn
    order: int = 100


STAT_PROVIDERS: dict[str, StatProvider] = {}


def stat_provider(key: str, *, order: int = 100) -> Callable[[StatFn], StatFn]:
    """fn(db) -> Stat | list[Stat]. Lỗi trong một provider không làm hỏng màn hình «Hôm nay»."""

    def deco(fn: StatFn) -> StatFn:
        STAT_PROVIDERS[key] = StatProvider(key=key, fn=fn, order=order)
        return fn

    return deco


# ---- lệnh bằng lời (i6) ------------------------------------------------------------------------------------------


@dataclass
class CommandContext:
    db: AsyncSession
    user: User
    text: str
    context: dict[str, Any] = field(default_factory=dict)


class CommandResult(BaseModel):
    """`done` = đã làm xong / đã trả lời; `pending` = đã đưa vào hàng chờ, chờ chị duyệt (lệnh đổi dữ liệu đi qua
    control.propose theo mức tự chủ); `needs_clarification` = chưa rõ đối tượng (không thấy hoặc nhiều lựa chọn)."""

    message: str
    status: Literal["done", "pending", "needs_clarification"] = "done"
    href: str | None = None
    data: dict[str, Any] | None = None

    @classmethod
    def from_outcome(cls, outcome: Any, *, done: str, pending: str, href: str | None = None,
                     data: dict[str, Any] | None = None) -> CommandResult:  # fmt: skip
        """Kết quả lệnh theo `ProposeOutcome`: applied → done, pending → pending; blocked/failed → lỗi (lệnh «chưa làm
        được» kèm lý do, mọi thay đổi trong lệnh được huỷ)."""
        extra = {**(data or {}), "outcome": outcome.status}
        if outcome.item_id:
            extra["approval_item_id"] = str(outcome.item_id)
        if outcome.status == "applied":
            return cls(message=done, href=href, data=extra)
        if outcome.status == "pending":
            return cls(message=pending, status="pending", href=href, data=extra)
        from app.core.errors import AppError

        if outcome.status == "blocked":
            raise AppError("Việc này đang tắt trong bảng mức tự chủ nên em không làm.", code="command_blocked")
        raise AppError(outcome.error or "Em làm chưa được, chị thử lại sau.", code="command_failed")


IntentFn = Callable[[CommandContext, Any], Awaitable[CommandResult]]


@dataclass
class IntentSpec:
    key: str
    label: str
    description: str
    params: type[BaseModel] | None
    examples: list[str]
    fn: IntentFn


INTENTS: dict[str, IntentSpec] = {}


def intent(
    key: str,
    label: str,
    description: str,
    *,
    params: type[BaseModel] | None = None,
    examples: list[str] | None = None,
) -> Callable[[IntentFn], IntentFn]:
    """Đăng ký một loại lệnh: fn(ctx: CommandContext, params: <params> | None) -> CommandResult.
    Lệnh có tác dụng phụ mà khách nhìn thấy phải đi qua control.propose bên trong fn."""

    def deco(fn: IntentFn) -> IntentFn:
        INTENTS[key] = IntentSpec(
            key=key, label=label, description=description, params=params, examples=examples or [], fn=fn
        )
        return fn

    return deco


# ---- cài đặt -----------------------------------------------------------------------------------------------------


@dataclass
class SettingSpec:
    key: str
    label: str
    default: Any
    group: str = "Chung"
    description: str = ""


SETTINGS: dict[str, SettingSpec] = {}


def register_setting(key: str, label: str, default: Any, *, group: str = "Chung", description: str = "") -> SettingSpec:
    spec = SettingSpec(key=key, label=label, default=default, group=group, description=description)
    SETTINGS[key] = spec
    return spec
