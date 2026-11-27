"""selection — bàn chọn (c1–c6): nhật ký thử hàng, quyết định chọn/loại kèm lý do, bộ nguyên tắc, gu của chị.

Giai đoạn trên bảng chọn là `candidates.stage` (module sourcing)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk, count, enum_col, fk, flag, json_list, json_obj
from app.core.enums import StrEnum


class TrialNoteKind(StrEnum):
    VOICE = "voice"
    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"  # đang chép lời / xếp vào món
    DONE = "done"
    FAILED = "failed"


class NoteAuthor(StrEnum):
    OWNER = "owner"
    TESTER = "tester"  # khách thử hàng cùng chị (h8)


class Decision(StrEnum):
    SELECTED = "selected"
    REJECTED = "rejected"


class DraftStatus(StrEnum):
    NONE = "none"
    DRAFTING = "drafting"
    PENDING_REVIEW = "pending_review"  # AI soạn xong lý do chọn / điều chưa ưng, chờ chị sửa lời (c3)
    APPROVED = "approved"


class PrincipleKind(StrEnum):
    MUST = "must"
    MUST_NOT = "must_not"
    PREFER = "prefer"
    AVOID = "avoid"


class PrincipleSource(StrEnum):
    OWNER = "owner"
    AI_SUGGESTED = "ai_suggested"


class TrialNote(UUIDPk, Timestamps, Base):
    """Nhật ký thử hàng (c2): chị nói vài câu + chụp ảnh lúc dùng; AI chép lời và xếp vào đúng món."""

    __tablename__ = "trial_notes"
    __table_args__ = (Index("ix_trial_notes_candidate_recorded", "candidate_id", "recorded_at"),)

    candidate_id: Mapped[uuid.UUID | None] = fk(
        "candidates", ondelete="CASCADE", index=False, comment="Null khi AI chưa xếp được vào món"
    )
    kind: Mapped[TrialNoteKind] = mapped_column(enum_col(TrialNoteKind))
    author: Mapped[NoteAuthor] = mapped_column(enum_col(NoteAuthor), default=NoteAuthor.OWNER)
    tester_invite_id: Mapped[uuid.UUID | None] = fk("tester_invites")
    author_name: Mapped[str | None] = mapped_column(String(120), comment="Tên khách thử (author=tester, h8)")
    text: Mapped[str | None] = mapped_column(Text, comment="Chị gõ, hoặc lời đã chép")
    audio_storage_key: Mapped[str | None] = mapped_column(String(300))
    media: Mapped[list[Any]] = json_list(comment='[{"storage_key","content_type","width","height"}]')
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    recorded_at: Mapped[datetime]
    trial_day: Mapped[int | None] = mapped_column(Integer, comment="Ngày thử thứ mấy")
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        enum_col(ProcessingStatus), default=ProcessingStatus.PENDING
    )
    ai_assigned: Mapped[bool] = flag(comment="AI tự xếp vào món (chị có thể chuyển)")
    assignment_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    sentiment: Mapped[str | None] = mapped_column(String(20), comment="positive / negative / mixed")
    tags: Mapped[list[Any]] = json_list()
    # «Ghi chú dùng thử» trên website (27/11): chị tích từng ghi chú; chỉ ghi chú của chị, không bao giờ của khách thử
    is_public: Mapped[bool] = flag(comment="Chị tích «Đưa lên website»")
    public_text: Mapped[str | None] = mapped_column(Text, comment="Lời hiện trên website (chị sửa được, khác lời gốc)")
    public_photos: Mapped[list[Any]] = json_list(
        comment='Ảnh chị tích kèm: bản sao công khai đã bỏ EXIF [{"files": {"800": {"webp","jpg"}}}]'
    )
    created_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)


class SelectionDecision(UUIDPk, Timestamps, Base):
    """Quyết định chọn hoặc loại (c3, c4). Một ứng viên có thể có nhiều dòng (đổi ý); dòng mới nhất là hiện hành.

    Chọn: AI soạn nháp `draft_*` từ ghi chú thử → chị sửa lời → `reason_selected`/`not_satisfied` lên trang sản phẩm.
    Loại: `rejection_reason` thành dữ liệu cho trang Hồ sơ chọn (các món đã loại)."""

    __tablename__ = "selection_decisions"
    __table_args__ = (Index("ix_selection_decisions_candidate", "candidate_id", "decided_at"),)

    candidate_id: Mapped[uuid.UUID] = fk("candidates", ondelete="CASCADE", nullable=False, index=False)
    brief_id: Mapped[uuid.UUID | None] = fk("sourcing_briefs")
    decision: Mapped[Decision] = mapped_column(enum_col(Decision), index=True)
    decided_at: Mapped[datetime]
    decided_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)
    trial_days: Mapped[int | None] = mapped_column(Integer, comment="Thời gian thử (hiện trên con dấu)")
    trial_started_at: Mapped[datetime | None]
    trial_ended_at: Mapped[datetime | None]
    # chọn (c3)
    reason_selected: Mapped[str | None] = mapped_column(Text)
    not_satisfied: Mapped[str | None] = mapped_column(Text, comment="Điều chưa ưng")
    draft_reason_selected: Mapped[str | None] = mapped_column(Text)
    draft_not_satisfied: Mapped[str | None] = mapped_column(Text)
    draft_status: Mapped[DraftStatus] = mapped_column(enum_col(DraftStatus), default=DraftStatus.NONE)
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    # loại (c4)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    rejection_tags: Mapped[list[Any]] = json_list(comment="vd: chat_lieu, gia, mui, do_ben")
    show_on_profile: Mapped[bool] = flag(True, comment="Hiện ở trang Hồ sơ chọn")
    product_id: Mapped[uuid.UUID | None] = fk("products")
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)


class SelectionPrinciple(UUIDPk, Timestamps, Base):
    """Bộ nguyên tắc của chị (c5) theo nhóm hàng; AI dùng để lọc từ đầu."""

    __tablename__ = "selection_principles"

    category_id: Mapped[uuid.UUID | None] = fk("categories", comment="Null = áp cho mọi nhóm")
    kind: Mapped[PrincipleKind] = mapped_column(enum_col(PrincipleKind))
    text: Mapped[str] = mapped_column(Text)
    structured: Mapped[dict[str, Any]] = json_obj(comment="Dạng máy đọc: field/op/value nếu AI chuyển được")
    priority: Mapped[int] = count()
    is_active: Mapped[bool] = flag(True)
    source: Mapped[PrincipleSource] = mapped_column(enum_col(PrincipleSource), default=PrincipleSource.OWNER)
    created_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)


class TasteProfile(UUIDPk, Timestamps, Base):
    """Gu của chị (c6): AI chỉnh cách xếp hạng sau mỗi lần chọn/loại. Một hồ sơ cho mỗi nhóm hàng (+ một chung)."""

    __tablename__ = "taste_profiles"
    __table_args__ = (
        UniqueConstraint("category_id", name="uq_taste_profiles_category", postgresql_nulls_not_distinct=True),
    )

    category_id: Mapped[uuid.UUID | None] = fk("categories", index=False)
    summary: Mapped[str | None] = mapped_column(Text, comment="AI mô tả gu bằng lời")
    weights: Mapped[dict[str, Any]] = json_obj(comment="Đặc điểm → trọng số")
    examples: Mapped[dict[str, Any]] = json_obj(comment='{"selected": [candidate_id], "rejected": [...]}')
    sample_count: Mapped[int] = count()
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    trained_at: Mapped[datetime | None]
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)
