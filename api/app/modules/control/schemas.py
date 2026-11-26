from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, computed_field

from app.core.enums import Actor
from app.modules.control.models import ActivityMode, AIRunStatus, ApprovalStatus, AutonomyLevel, UserRole
from app.modules.control.registry import ACTIONS, Stat


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
    href: str | None = Field(default=None, description="Màn hình của đối tượng liên quan (để bấm tới)")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def action_label(self) -> str:
        spec = ACTIONS.get(self.action)
        return spec.label if spec else self.action

    @computed_field  # type: ignore[prop-decorator]
    @property
    def action_group(self) -> str | None:
        spec = ACTIONS.get(self.action)
        return spec.group if spec else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def locked(self) -> bool:
        """Việc «Chị quyết» (luôn hỏi: khiếu nại, đổi trả, hoàn tiền, đặt hàng/trả tiền NCC...)."""
        spec = ACTIONS.get(self.action)
        return bool(spec and spec.locked)


class ApproveIn(BaseModel):
    payload: dict[str, Any] | None = Field(default=None, description="Phần chị sửa (gộp nông vào payload)")
    note: str | None = Field(default=None, max_length=2000)


class ReturnIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000, description="Lời nhắn cho AI")


class BatchApproveIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=2000)


class BatchApproveResult(BaseModel):
    id: uuid.UUID
    status: ApprovalStatus | None
    error: str | None = None


class BatchApproveOut(BaseModel):
    approved: int
    failed: int
    results: list[BatchApproveResult]


class ApprovalGroupOut(BaseModel):
    """Số việc đang chờ theo loại việc (để lọc và duyệt hàng loạt)."""

    action: str
    label: str
    group: str | None
    locked: bool
    count: int


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
    href: str | None = Field(default=None, description="Màn hình của đối tượng liên quan")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def action_label(self) -> str:
        spec = ACTIONS.get(self.action)
        return spec.label if spec else self.action


# ---- mức tự chủ --------------------------------------------------------------------------------------------------


class AutonomyHistory(BaseModel):
    """Lịch sử duyệt gần đây của một hành động (căn cứ gợi ý nới mức tự chủ)."""

    approved: int  # trong các lần quyết gần nhất
    edited: int
    returned: int
    streak: int  # số lần duyệt liền gần nhất không sửa, không trả lại


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
    history: AutonomyHistory
    suggest_auto: bool = Field(description="Gợi ý nới: chị duyệt liên tục không sửa")


class AutonomyUpdate(BaseModel):
    level: Literal["auto", "ask", "off"]


# ---- Hôm nay -----------------------------------------------------------------------------------------------------


class PendingBlock(BaseModel):
    total: int
    items: list[ApprovalItemOut]


class DoneGroup(BaseModel):
    action: str
    label: str
    count: int


class DoneBlock(BaseModel):
    total: int
    items: list[ActivityOut]
    auto_total: int = 0  # riêng việc AI tự làm (không tính việc thực thi sau khi chị duyệt)
    groups: list[DoneGroup] = Field(default_factory=list, description="Việc AI tự làm hôm nay, gom theo loại")


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
    label: str = ""
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


# ---- cấu hình AI (Cài đặt → AI và khoá API) ---------------------------------------------------------------------

AIEffort = Literal["low", "medium", "high", "max"]
ConfigSource = Literal["settings", "env"]


def _blank_none(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


def _key(v: str | None) -> str | None:
    v = _blank_none(v)
    if v is not None and any(c.isspace() for c in v):
        raise ValueError("Khoá API không được chứa khoảng trắng.")
    return v


def _url(v: str | None) -> str | None:
    v = _blank_none(v)
    if v is not None and not re.match(r"^https?://[^\s]+$", v):
        raise ValueError("Base URL phải bắt đầu bằng http:// hoặc https://.")
    return v


ModelName = Annotated[str | None, Field(max_length=120, pattern=r"^[A-Za-z0-9._:/@+-]*$"), AfterValidator(_blank_none)]


class AIProviderOut(BaseModel):
    name: str
    label: str
    needs_key: bool
    supports_web: bool
    needs_base_url: bool
    default_base_url: str | None
    model_suggestions: list[str]
    key_placeholder: str
    saved: bool = Field(description="Đã có dòng cấu hình trong CSDL")
    has_key: bool
    key_hint: str | None = Field(description="Dạng che, vd sk-ant-…8AAA; không bao giờ trả khoá thật")
    key_source: ConfigSource | None
    key_updated_at: datetime | None
    key_updated_by: str | None
    base_url: str | None
    model_smart: str
    model_fast: str
    effort_smart: str | None
    effort_fast: str | None


class AIConfigOut(BaseModel):
    provider: str = Field(description="Provider đang dùng")
    source: ConfigSource = Field(description="settings = chị lưu ở Cài đặt; env = biến môi trường / mặc định")
    providers: list[AIProviderOut]
    efforts: list[str]
    monthly_budget_vnd: int
    budget_source: ConfigSource


class AIConfigIn(BaseModel):
    provider: str = Field(max_length=30)
    api_key: Annotated[str | None, Field(max_length=500), AfterValidator(_key)] = Field(
        default=None, description="Để trống = giữ khoá đã lưu"
    )
    base_url: Annotated[str | None, Field(max_length=300), AfterValidator(_url)] = None
    model_smart: ModelName = None
    model_fast: ModelName = None
    effort_smart: AIEffort | None = None
    effort_fast: AIEffort | None = None
    monthly_budget_vnd: int | None = Field(default=None, ge=0)
    activate: bool = Field(default=True, description="Lưu xong chuyển sang dùng provider này (False = chỉ lưu sẵn)")


class AITestResult(BaseModel):
    tier: Literal["fast", "smart"]
    ok: bool
    model: str
    latency_ms: int
    cost_vnd: int = 0
    error: str | None = None
    code: str | None = None


class AITestOut(BaseModel):
    provider: str
    results: list[AITestResult]


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


class SettingsBulkUpdate(BaseModel):
    values: dict[str, Any] = Field(min_length=1)


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
    actor_name: str | None = None


class IntegrationOut(BaseModel):
    kind: str
    label: str
    driver: str
    is_mock: bool = Field(description="Mọi kênh của tích hợp này đều đang chạy giả lập")
    partly_mock: bool = Field(default=False, description="Có kênh thật, có kênh còn giả lập")
    drivers: list[str] = Field(default_factory=list, description="Các driver đang dùng (gồm driver theo kênh)")
    mock_effect: str | None = Field(default=None, description="Giả lập nghĩa là gì với chị (vd tin không tới khách)")
    blocked_in_prod: bool = Field(default=False, description="Bản chạy thật từ chối dùng driver giả này")
    available: list[str]


# ---- lệnh bằng lời -----------------------------------------------------------------------------------------------


class CommandIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict, description="Màn hình đang mở, đối tượng đang xem...")


class CommandOut(BaseModel):
    text: str
    status: Literal["done", "pending", "needs_clarification", "unknown", "failed"]
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


# ---- tài khoản kênh (Cài đặt → Mạng xã hội) ----------------------------------------------------------------------


class ChannelFieldOut(BaseModel):
    key: str
    label: str
    secret: bool
    required: bool
    oauth: bool = Field(description="Do nút «Kết nối» điền")
    hint: str = ""
    value: str | None = Field(default=None, description="Chỉ có với ô không bí mật")
    masked: str | None = Field(default=None, description="Bí mật: chỉ 4 ký tự cuối")
    is_set: bool
    source: Literal["settings", "env"] | None = None


class ChannelSharedOut(BaseModel):
    channel: str
    key: str
    label: str
    is_set: bool


class ChannelCheckOut(BaseModel):
    ok: bool
    message: str
    account_name: str | None = None
    at: str | None = None


class ChannelOAuthOut(BaseModel):
    supported: bool
    redirect_uri: str | None = None
    connected: bool = False
    expires_at: float | None = None
    refresh_expires_at: float | None = None


class ChannelLinkOut(BaseModel):
    label: str
    url: str


class ChannelGuideOut(BaseModel):
    needs: list[str]
    steps: list[str]
    limits: list[str]
    links: list[ChannelLinkOut]


class ChannelAccountOut(BaseModel):
    channel: str
    label: str
    kind: Literal["social", "marketplaces", "manual"]
    driver: str
    mode: Literal["mock", "real"]
    mode_source: Literal["settings", "env"]
    status: Literal["manual", "mock", "connected", "not_connected"]
    ready: bool = Field(description="Đã đủ các ô bắt buộc")
    account_name: str | None = None
    fields: list[ChannelFieldOut]
    shared: list[ChannelSharedOut]
    check: ChannelCheckOut | None = None
    oauth: ChannelOAuthOut
    guide: ChannelGuideOut


class ChannelAccountIn(BaseModel):
    mode: Literal["mock", "real"] | None = None
    values: dict[str, str] = Field(default_factory=dict, description="Ô bí mật để trống = giữ giá trị cũ")
    clear: list[str] = Field(default_factory=list, description="Xoá giá trị đã lưu (về biến môi trường)")


class ChannelCheckIn(BaseModel):
    values: dict[str, str] = Field(default_factory=dict, description="Giá trị đang nhập, chưa lưu")


class ChannelConnectOut(BaseModel):
    url: str
    redirect_uri: str


# ---- nguồn hàng (Cài đặt → Nguồn hàng) ---------------------------------------------------------------------------


class SourceDriverOption(BaseModel):
    driver: str
    label: str


class SourcePlatformOut(BaseModel):
    platform: str
    label: str
    driver: str = Field(description="mock | web | onebound | rakuten")
    driver_source: Literal["settings", "env"]
    status: Literal["mock", "web", "connected", "not_connected"]
    account: str | None = Field(default=None, description="Tài khoản dịch vụ khi lấy qua tài khoản")
    options: list[SourceDriverOption]
    notes: list[str]
    warning: str | None = None


class SourceGuideOut(ChannelGuideOut):
    cost: list[str]


class SourceCheckOut(BaseModel):
    ok: bool
    message: str
    at: str | None = None


class SourceAccountOut(BaseModel):
    account: str
    label: str
    driver: str
    platforms: list[str]
    used_by: list[str] = Field(description="Các sàn đang lấy hàng qua tài khoản này")
    ready: bool
    verified: bool = Field(description="Đã thử với khoá thật")
    fields: list[ChannelFieldOut]
    check: SourceCheckOut | None = None
    guide: SourceGuideOut


class SourcesOverviewOut(BaseModel):
    platforms: list[SourcePlatformOut]
    accounts: list[SourceAccountOut]
    general_driver: str = Field(description="Driver cho xu hướng, giá sàn VN, link trang lạ")


class SourceRouteIn(BaseModel):
    driver: str | None = Field(description="mock | web | driver tài khoản; null = theo SOURCES_DRIVER")


class SourceAccountIn(BaseModel):
    values: dict[str, str] = Field(default_factory=dict, description="Ô bí mật để trống = giữ giá trị cũ")
    clear: list[str] = Field(default_factory=list, description="Xoá giá trị đã lưu (về biến môi trường)")
