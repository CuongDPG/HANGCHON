"""Schema đọc cơ bản của crm (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import Channel
from app.modules.crm.models import (
    BroadcastKind,
    BroadcastStatus,
    NoteKind,
    NoteSource,
    ReferralUseStatus,
    ReminderStatus,
    TesterInviteStatus,
)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CustomerNoteOut(ORM):
    """Sổ khách (h4): ghi chú, quan tâm — do chị ghi hoặc AI rút từ hội thoại."""

    id: uuid.UUID
    customer_id: uuid.UUID
    kind: NoteKind
    source: NoteSource
    body: str
    ref_type: str | None
    ref_id: uuid.UUID | None
    pinned: bool
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class CustomerTagOut(ORM):
    id: uuid.UUID
    customer_id: uuid.UUID
    tag: str
    source: NoteSource
    created_at: datetime


class BroadcastOut(ORM):
    """Tin gửi nhóm khách quen / nhiều khách (h5): AI soạn, chị duyệt rồi mới gửi."""

    id: uuid.UUID
    kind: BroadcastKind
    channel: Channel
    channel_account_id: uuid.UUID | None
    drop_id: uuid.UUID | None
    title: str
    body: str
    media: list[Any]
    audience: dict[str, Any]
    status: BroadcastStatus
    scheduled_at: datetime | None
    sent_at: datetime | None
    recipient_count: int
    delivered_count: int
    ai_generated: bool
    approval_item_id: uuid.UUID | None
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class GroupDigestOut(ORM):
    """Tóm tắt thảo luận trong nhóm khách quen (h5)."""

    id: uuid.UUID
    thread_id: uuid.UUID | None
    channel_account_id: uuid.UUID | None
    period_start: datetime
    period_end: datetime
    summary: str
    highlights: list[Any]
    open_questions: list[Any]
    product_mentions: list[Any]
    ai_run_id: uuid.UUID | None
    created_at: datetime


class ReorderReminderOut(ORM):
    """Nhắc mua lại đúng lúc (h6): món tiêu hao sắp hết thì nhắc đúng người, không nhắn đại trà."""

    id: uuid.UUID
    customer_id: uuid.UUID
    product_id: uuid.UUID
    order_id: uuid.UUID | None
    order_item_id: uuid.UUID | None
    due_on: date
    reason: str | None
    channel: Channel | None
    message_body: str | None
    status: ReminderStatus
    sent_at: datetime | None
    converted_order_id: uuid.UUID | None
    approval_item_id: uuid.UUID | None
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ReferralOut(ORM):
    """Mã giới thiệu bạn (h7): quà cho cả hai. Mỗi khách giới thiệu một mã."""

    id: uuid.UUID
    code: str
    referrer_customer_id: uuid.UUID
    is_active: bool
    reward_referrer_vnd: int
    reward_referred_vnd: int
    uses_count: int
    rewarded_count: int
    expires_on: date | None
    created_at: datetime
    updated_at: datetime


class ReferralUseOut(ORM):
    id: uuid.UUID
    referral_id: uuid.UUID
    referred_customer_id: uuid.UUID
    order_id: uuid.UUID | None
    status: ReferralUseStatus
    rewarded_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TesterInviteOut(ORM):
    """Khách thử hàng cùng chị (h8): mời vài khách quen dùng thử mẫu trước khi chị quyết định chọn."""

    id: uuid.UUID
    candidate_id: uuid.UUID
    customer_id: uuid.UUID
    token: str
    status: TesterInviteStatus
    message: str | None
    invited_at: datetime | None
    responded_at: datetime | None
    sample_sent_at: datetime | None
    feedback: str | None
    feedback_rating: int | None
    feedback_media: list[Any]
    feedback_at: datetime | None
    reward_note: str | None
    trial_days: int | None
    created_at: datetime
    updated_at: datetime


# ---- schema của màn hình Khách -----------------------------------------------------------------------------------


class CustomerListItem(BaseModel):
    id: uuid.UUID
    name: str | None
    phone: str | None
    email: str | None
    channels: list[str]
    order_count: int
    total_spent_vnd: int
    last_order_at: datetime | None
    is_regular: bool
    opted_out: bool
    tags: list[str]
    summary: str | None
    created_at: datetime


class IdentityView(BaseModel):
    channel: Channel
    external_id: str
    display_name: str | None


class OrderLine(BaseModel):
    name: str
    quantity: int


class OrderBrief(BaseModel):
    id: uuid.UUID
    code: str
    status: str
    status_label: str
    placed_at: datetime
    total_vnd: int
    items: list[OrderLine]


class ThreadBrief(BaseModel):
    id: uuid.UUID
    channel: Channel
    channel_label: str
    kind: str
    snippet: str | None
    status: str
    needs_owner: bool
    last_message_at: datetime | None


class QuestionView(BaseModel):
    body: str
    sent_at: datetime
    thread_id: uuid.UUID


class ReminderView(ReorderReminderOut):
    customer_name: str | None = None
    product_name: str | None = None


class InviteView(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    candidate_title: str | None = None
    customer_id: uuid.UUID
    customer_name: str | None
    status: TesterInviteStatus
    message: str | None
    invited_at: datetime | None
    responded_at: datetime | None
    feedback: str | None
    feedback_rating: int | None
    feedback_at: datetime | None
    link: str


class CustomerProfile(CustomerListItem):
    default_address: dict[str, Any]
    first_channel: Channel | None
    identities: list[IdentityView]
    notes: list[CustomerNoteOut]
    interests: list[str]
    summary_updated_at: datetime | None
    orders: list[OrderBrief]
    threads: list[ThreadBrief]
    recent_questions: list[QuestionView]
    referral: ReferralOut | None
    reminders: list[ReminderView]
    invites: list[InviteView]


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    kind: Literal["note", "interest", "preference", "issue"] = "note"
    pinned: bool = False


class NotePatch(BaseModel):
    body: str | None = Field(default=None, min_length=1, max_length=2000)
    pinned: bool | None = None


class TagIn(BaseModel):
    tag: str = Field(min_length=1, max_length=60)


class OptOutIn(BaseModel):
    opt_out: bool


class RegularsOut(BaseModel):
    min_orders: int
    total: int
    reachable: int
    items: list[CustomerListItem]


class CrmSettingsIn(BaseModel):
    regular_min_orders: int = Field(ge=1, le=50)


class BroadcastView(BroadcastOut):
    drop_title: str | None = None


class BroadcastIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=2000)


class SendIn(BaseModel):
    body: str | None = Field(default=None, max_length=2000)


class DigestIn(BaseModel):
    text: str = Field(min_length=10, max_length=20000)
    period_start: datetime | None = None
    period_end: datetime | None = None


class ReorderRuleView(BaseModel):
    product_id: uuid.UUID
    name: str
    is_consumable: bool
    product_days: int | None
    category_days: int | None
    configured_days: int | None
    active: bool
    effective_days: int | None


class ReorderRuleIn(BaseModel):
    cycle_days: int | None = Field(default=None, ge=1, le=365)
    active: bool = True


class RunDueOut(BaseModel):
    drafted: int
    skipped: int


class ReferralView(ReferralOut):
    referrer_name: str | None = None


class ReferralUseView(ReferralUseOut):
    code: str
    referrer_name: str | None
    referred_name: str | None
    order_code: str | None


class ReferralStats(BaseModel):
    codes: int
    uses: int
    pending: int
    qualified: int
    rewarded: int
    orders_from_referrals: int
    revenue_from_referrals_vnd: int
    referred_customers: int
    referred_repeat_rate: float | None
    overall_repeat_rate: float | None


class RewardIn(BaseModel):
    note: str = Field(default="", max_length=300)


class ManualUseIn(BaseModel):
    customer_id: uuid.UUID
    order_id: uuid.UUID | None = None


class TrialNoteView(BaseModel):
    id: uuid.UUID
    kind: str
    author: str
    text: str | None
    recorded_at: datetime
    trial_day: int | None


class TrialCandidateView(BaseModel):
    id: uuid.UUID
    title: str
    image_url: str | None
    stage_changed_at: datetime | None
    notes: list[TrialNoteView]
    invites: list[InviteView]


class InviteIn(BaseModel):
    candidate_id: uuid.UUID
    customer_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    message: str | None = Field(default=None, max_length=1000)


class InviteStatusIn(BaseModel):
    status: Literal["invited", "sample_sent", "closed"]


class PublicInvite(BaseModel):
    first_name: str
    product_title: str
    image_url: str | None
    message: str | None
    status: TesterInviteStatus
    can_answer: bool
    can_feedback: bool
    feedback: str | None
    feedback_rating: int | None


class RespondIn(BaseModel):
    action: Literal["accept", "decline", "feedback"]
    feedback: str | None = Field(default=None, max_length=4000)
    rating: int | None = Field(default=None, ge=1, le=5)
