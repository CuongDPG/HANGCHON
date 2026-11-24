"""Schema đọc cơ bản của selection (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.modules.selection.models import (
    Decision,
    DraftStatus,
    NoteAuthor,
    PrincipleKind,
    PrincipleSource,
    ProcessingStatus,
    TrialNoteKind,
)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TrialNoteOut(ORM):
    """Nhật ký thử hàng (c2): chị nói vài câu + chụp ảnh lúc dùng; AI chép lời và xếp vào đúng món."""

    id: uuid.UUID
    candidate_id: uuid.UUID | None
    kind: TrialNoteKind
    author: NoteAuthor
    tester_invite_id: uuid.UUID | None
    text: str | None
    audio_storage_key: str | None
    media: list[Any]
    duration_seconds: int | None
    recorded_at: datetime
    trial_day: int | None
    processing_status: ProcessingStatus
    ai_assigned: bool
    assignment_confidence: Decimal | None
    sentiment: str | None
    tags: list[Any]
    created_by_id: uuid.UUID | None
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class SelectionDecisionOut(ORM):
    """Quyết định chọn hoặc loại (c3, c4). Một ứng viên có thể có nhiều dòng (đổi ý); dòng mới nhất là hiện hành."""

    id: uuid.UUID
    candidate_id: uuid.UUID
    brief_id: uuid.UUID | None
    decision: Decision
    decided_at: datetime
    decided_by_id: uuid.UUID | None
    trial_days: int | None
    trial_started_at: datetime | None
    trial_ended_at: datetime | None
    reason_selected: str | None
    not_satisfied: str | None
    draft_reason_selected: str | None
    draft_not_satisfied: str | None
    draft_status: DraftStatus
    approval_item_id: uuid.UUID | None
    rejection_reason: str | None
    rejection_tags: list[Any]
    show_on_profile: bool
    product_id: uuid.UUID | None
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class SelectionPrincipleOut(ORM):
    """Bộ nguyên tắc của chị (c5) theo nhóm hàng; AI dùng để lọc từ đầu."""

    id: uuid.UUID
    category_id: uuid.UUID | None
    kind: PrincipleKind
    text: str
    structured: dict[str, Any]
    priority: int
    is_active: bool
    source: PrincipleSource
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class TasteProfileOut(ORM):
    """Gu của chị (c6): AI chỉnh cách xếp hạng sau mỗi lần chọn/loại. Một hồ sơ cho mỗi nhóm hàng (+ một chung)."""

    id: uuid.UUID
    category_id: uuid.UUID | None
    summary: str | None
    weights: dict[str, Any]
    examples: dict[str, Any]
    sample_count: int
    version: int
    trained_at: datetime | None
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
