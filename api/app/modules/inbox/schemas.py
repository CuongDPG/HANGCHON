"""Schema đọc cơ bản của inbox (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.enums import Actor, Channel
from app.modules.inbox.models import (
    AccountStatus,
    Direction,
    EscalationReason,
    Intent,
    MessageStatus,
    ReplyKind,
    ReplyStatus,
    ThreadKind,
    ThreadStatus,
)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ChannelAccountOut(ORM):
    """Trang/tài khoản của chị trên từng kênh. Không lưu token ở đây — token nằm trong env/kho bí mật."""

    id: uuid.UUID
    channel: Channel
    name: str
    external_id: str
    driver: str
    status: AccountStatus
    can_publish: bool
    can_message: bool
    settings: dict[str, Any]
    connected_at: datetime | None
    last_synced_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class ThreadOut(ORM):
    id: uuid.UUID
    channel_account_id: uuid.UUID | None
    channel: Channel
    kind: ThreadKind
    external_thread_id: str
    external_post_id: str | None
    scheduled_post_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    participant_name: str | None
    participant_external_id: str | None
    status: ThreadStatus
    needs_owner: bool
    escalation_reason: EscalationReason | None
    last_intent: Intent | None
    snippet: str | None
    last_message_at: datetime | None
    last_inbound_at: datetime | None
    unread_count: int
    product_id: uuid.UUID | None
    order_id: uuid.UUID | None
    assigned_user_id: uuid.UUID | None
    summary: str | None
    created_at: datetime
    updated_at: datetime


class MessageOut(ORM):
    id: uuid.UUID
    thread_id: uuid.UUID
    direction: Direction
    sender: Actor
    external_message_id: str | None
    author_name: str | None
    body: str
    attachments: list[Any]
    sent_at: datetime
    status: MessageStatus
    intent: Intent | None
    intent_confidence: Decimal | None
    extracted: dict[str, Any]
    ai_generated: bool
    read_at: datetime | None
    error: str | None
    created_at: datetime


class ReplyDraftOut(ORM):
    """Câu trả lời AI soạn sẵn (h2). Loại `instant` có thể tự gửi theo mức tự chủ; còn lại chờ chị."""

    id: uuid.UUID
    thread_id: uuid.UUID
    reply_to_message_id: uuid.UUID | None
    kind: ReplyKind
    intent: Intent | None
    body: str
    status: ReplyStatus
    confidence: Decimal | None
    sources: list[Any]
    draft_order: dict[str, Any]
    missing_info: list[Any]
    sent_message_id: uuid.UUID | None
    approval_item_id: uuid.UUID | None
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
