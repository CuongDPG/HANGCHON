"""Schema đọc cơ bản của assistant (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.modules.assistant.models import AnswerBasis, AssistantRole, ConversationStatus, Feedback


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AssistantConversationOut(ORM):
    id: uuid.UUID
    session_key: str
    customer_id: uuid.UUID | None
    product_id: uuid.UUID | None
    page_path: str | None
    status: ConversationStatus
    handed_off_at: datetime | None
    handoff_reason: str | None
    thread_id: uuid.UUID | None
    contact: str | None
    message_count: int
    last_message_at: datetime | None
    ip_hash: str | None
    created_at: datetime
    updated_at: datetime


class AssistantMessageOut(ORM):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: AssistantRole
    content: str
    citations: list[Any]
    basis: AnswerBasis | None
    confidence: Decimal | None
    unknown: bool
    feedback: Feedback | None
    ai_run_id: uuid.UUID | None
    created_at: datetime
