"""Schema đọc cơ bản của selection (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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


# ---- schema tạo/sửa và schema cho màn hình (c1–c6) ----------------------------------------------------------------

StageName = Literal["candidate", "sample", "trial", "selected", "rejected"]
PointKind = Literal["good", "bad", "measure"]


class StageChangeIn(BaseModel):
    """Hợp đồng cố định (module sourcing gọi từ trang hồ sơ thẩm định): `{to, reason?}`.
    `reason_tags` (nhóm lý do loại) và `position` (thứ tự trong cột) là tuỳ chọn thêm."""

    to: StageName
    reason: str | None = Field(default=None, max_length=2000)
    reason_tags: list[str] | None = None
    position: int | None = Field(default=None, ge=0)


class NotePoint(BaseModel):
    kind: PointKind
    text: str


class SealCount(BaseModel):
    chosen: int
    total: int


class BoardCard(BaseModel):
    id: uuid.UUID
    title: str
    image_url: str | None
    source_platform: str
    price_vnd_estimate: int | None
    ai_score: int | None
    stage: StageName
    stage_changed_at: datetime | None
    board_position: int
    brief_id: uuid.UUID | None
    category_id: uuid.UUID | None
    trial_day: int | None
    trial_days: int
    note_count: int
    last_note: str | None
    last_note_at: datetime | None
    landed_cost_vnd: int | None
    seal: SealCount | None
    decision_id: uuid.UUID | None
    decision_summary: str | None
    draft_status: DraftStatus | None


class BoardOut(BaseModel):
    trial_days: int
    counts: dict[str, int]
    columns: dict[str, list[BoardCard]]


class TrialNoteView(TrialNoteOut):
    points: list[NotePoint]
    photo_urls: list[str]
    audio_url: str | None


class DecisionView(SelectionDecisionOut):
    reasons_list: list[str]
    not_satisfied_list: list[str]
    draft_reasons_list: list[str]
    draft_not_satisfied_list: list[str]
    rejection_groups: list[dict[str, str]]


class CandidateDetail(BaseModel):
    card: BoardCard
    title_original: str | None
    source_url: str | None
    description_vi: str | None
    seller_name: str | None
    supplier_id: uuid.UUID | None
    price_amount: Decimal | None
    price_currency: str | None
    weight_grams: int | None
    rank_reason: str | None
    notes: list[TrialNoteView]
    decision: DecisionView | None
    history: list[DecisionView]


class NoteUpdate(BaseModel):
    text: str | None = Field(default=None, max_length=5000)
    candidate_id: uuid.UUID | None = None
    points: list[NotePoint] | None = None


class ApproveReasonsIn(BaseModel):
    reason_selected: list[str] = Field(min_length=1, max_length=5)
    not_satisfied: list[str] = Field(default_factory=list, max_length=5)


class RedraftIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class RejectionUpdate(BaseModel):
    rejection_reason: str | None = Field(default=None, min_length=2, max_length=2000)
    rejection_tags: list[str] | None = None
    show_on_profile: bool | None = None


class ReasonGroup(BaseModel):
    key: str
    label: str


class FrequentReason(BaseModel):
    text: str
    group: str
    count: int


class RejectReasonsOut(BaseModel):
    groups: list[ReasonGroup]
    frequent: list[FrequentReason]


class RejectionStat(BaseModel):
    key: str
    label: str
    count: int


class RejectionStatsOut(BaseModel):
    total: int
    groups: list[RejectionStat]
    summary: str


class PrincipleIn(BaseModel):
    kind: PrincipleKind
    text: str = Field(min_length=3, max_length=1000)
    category_id: uuid.UUID | None = None
    priority: int = 0
    is_active: bool = True
    structured: dict[str, Any] = Field(default_factory=dict)


class PrincipleUpdate(BaseModel):
    kind: PrincipleKind | None = None
    text: str | None = Field(default=None, min_length=3, max_length=1000)
    category_id: uuid.UUID | None = None
    clear_category: bool = False
    priority: int | None = None
    is_active: bool | None = None


class Trait(BaseModel):
    trait: str = Field(min_length=1, max_length=200)
    weight: float = Field(ge=-1, le=1)


class TasteProfileView(TasteProfileOut):
    category_name: str | None
    likes: list[Trait]
    dislikes: list[Trait]
    pending_count: int
    owner_edited: bool


class TasteProfileUpdate(BaseModel):
    summary: str | None = Field(default=None, max_length=3000)
    likes: list[Trait] | None = None
    dislikes: list[Trait] | None = None


class RetrainIn(BaseModel):
    category_id: uuid.UUID | None = None
    all: bool = False


class CategoryLite(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class SelectionSettings(BaseModel):
    trial_days: int = Field(ge=1, le=90)


class StageChangeOut(BaseModel):
    card: BoardCard
    decision: DecisionView | None
