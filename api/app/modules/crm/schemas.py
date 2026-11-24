"""Schema đọc cơ bản của crm (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

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
