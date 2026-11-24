from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.core.enums import Actor
from app.modules.control.models import ActivityMode, AIRunStatus, ApprovalStatus, AutonomyLevel, UserRole
from app.modules.control.registry import Stat


def _email(v: str) -> str:
    v = v.strip().lower()
    local, _, domain = v.partition("@")
    if not local or "." not in domain or " " in v:
        raise ValueError("Email không hợp lệ.")
    return v


# Không dùng EmailStr: email-validator từ chối tên miền nội bộ như .local dùng khi chạy máy.
Email = Annotated[str, Field(max_length=254), AfterValidator(_email)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- xác thực / người dùng ---------------------------------------------------------------------------------------


class LoginIn(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=200)


class UserOut(ORM):
    id: uuid.UUID
    email: str
    name: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class UserCreate(BaseModel):
    email: Email
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    role: UserRole = UserRole.HELPER


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    is_active: bool | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


# ---- hàng chờ / nhật ký ------------------------------------------------------------------------------------------


class ApprovalItemOut(ORM):
    id: uuid.UUID
    action: str
    module: str
    title: str
    summary: str | None
    payload: dict[str, Any]
    preview: dict[str, Any]
    edited_payload: dict[str, Any] | None
    was_edited: bool
    status: ApprovalStatus
    priority: int
    rationale: str | None
    sources: list[Any]
    ref_type: str | None
    ref_id: uuid.UUID | None
    ai_generated: bool
    ai_run_id: uuid.UUID | None
    decision_note: str | None
    decided_at: datetime | None
    decided_by_id: uuid.UUID | None
    result: dict[str, Any] | None
    error: str | None
    attempts: int
    created_at: datetime
    updated_at: datetime


class ApproveIn(BaseModel):
    payload: dict[str, Any] | None = Field(default=None, description="Phần chị sửa (gộp nông vào payload)")
    note: str | None = Field(default=None, max_length=2000)


class ReturnIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000, description="Lời nhắn cho AI")


class ActivityOut(ORM):
    id: uuid.UUID
    action: str
    module: str
    title: str
    summary: str | None
    mode: ActivityMode
    rationale: str | None
    sources: list[Any]
    payload: dict[str, Any]
    result: dict[str, Any] | None
    ref_type: str | None
    ref_id: uuid.UUID | None
    approval_item_id: uuid.UUID | None
    ai_run_id: uuid.UUID | None
    undoable: bool
    undone_at: datetime | None
    undone_by_id: uuid.UUID | None
    created_at: datetime


# ---- mức tự chủ --------------------------------------------------------------------------------------------------


class AutonomyOut(BaseModel):
    action: str
    label: str
    group: str
    description: str
    module: str
    level: AutonomyLevel
    default_level: AutonomyLevel
    locked: bool
    customer_facing: bool
    updated_at: datetime | None


class AutonomyUpdate(BaseModel):
    level: Literal["auto", "ask", "off"]


# ---- Hôm nay -----------------------------------------------------------------------------------------------------


class PendingBlock(BaseModel):
    total: int
    items: list[ApprovalItemOut]


class DoneBlock(BaseModel):
    total: int
    items: list[ActivityOut]


class AICostBrief(BaseModel):
    month: str
    spent_vnd: int
    budget_vnd: int
    used_pct: float


class TodayOut(BaseModel):
    date: date
    pending: PendingBlock
    ai_done: DoneBlock
    stats: list[Stat]
    ai_cost: AICostBrief


# ---- chi phí AI --------------------------------------------------------------------------------------------------


class AICostByTask(BaseModel):
    task: str
    runs: int
    cost_vnd: int
    input_tokens: int
    output_tokens: int


class AICostByDay(BaseModel):
    date: date
    runs: int
    cost_vnd: int


class AICostsOut(BaseModel):
    month: str
    spent_vnd: int
    budget_vnd: int
    remaining_vnd: int
    used_pct: float
    run_count: int
    error_count: int
    blocked_count: int
    by_task: list[AICostByTask]
    by_day: list[AICostByDay]


class BudgetUpdate(BaseModel):
    monthly_budget_vnd: int = Field(ge=0)


class AIRunOut(ORM):
    id: uuid.UUID
    task: str
    provider: str
    model: str
    tier: str
    status: AIRunStatus
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    web_search_requests: int
    cost_vnd: int
    duration_ms: int | None
    stop_reason: str | None
    refusal_category: str | None
    fallback_model: str | None
    error_code: str | None
    error: str | None
    created_at: datetime


# ---- cài đặt / lưu vết -------------------------------------------------------------------------------------------


class SettingOut(BaseModel):
    key: str
    label: str
    group: str
    description: str
    default: Any
    value: Any
    is_default: bool
    updated_at: datetime | None


class SettingUpdate(BaseModel):
    value: Any


class AuditOut(ORM):
    id: uuid.UUID
    created_at: datetime
    actor_kind: Actor
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str | None
    entity_id: str | None
    summary: str | None
    data: dict[str, Any]


# ---- lệnh bằng lời -----------------------------------------------------------------------------------------------


class CommandIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict, description="Màn hình đang mở, đối tượng đang xem...")


class CommandOut(BaseModel):
    text: str
    status: Literal["done", "needs_clarification", "unknown", "failed"]
    intent: str | None
    label: str | None
    message: str
    href: str | None
    data: dict[str, Any] | None


class IntentOut(BaseModel):
    key: str
    label: str
    description: str
    examples: list[str]
