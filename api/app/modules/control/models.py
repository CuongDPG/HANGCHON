"""control — người dùng, mức tự chủ, hàng chờ duyệt, nhật ký AI, chi phí AI, cài đặt, lưu vết (i1–i4, i6, k2, k3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, Timestamps, UUIDPk, enum_col
from app.core.enums import Actor, StrEnum


class UserRole(StrEnum):
    OWNER = "owner"  # chị
    HELPER = "helper"  # người phụ giúp (k4)


class AutonomyLevel(StrEnum):
    AUTO = "auto"  # AI tự làm, ghi nhật ký
    ASK = "ask"  # AI làm, chị duyệt
    OFF = "off"  # tắt
    LOCKED_ASK = "locked_ask"  # luôn hỏi, không đổi được


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"  # đã duyệt và thực thi xong
    RETURNED = "returned"  # chị trả lại kèm lời nhắn
    FAILED = "failed"  # đã duyệt nhưng thực thi lỗi (duyệt lại được)
    CANCELLED = "cancelled"  # hệ thống huỷ (việc không còn cần)
    EXPIRED = "expired"


class ActivityMode(StrEnum):
    AUTO = "auto"  # AI tự làm theo mức tự chủ
    APPROVED = "approved"  # thực thi sau khi chị duyệt


class AIRunStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    REFUSED = "refused"
    BLOCKED = "blocked"  # chặn vì chạm trần ngân sách


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(enum_col(UserRole), default=UserRole.HELPER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    last_login_at: Mapped[datetime | None]


class AutonomySetting(Base):
    """Mức tự chủ chị đã đặt. Không có dòng = dùng mức mặc định trong sổ đăng ký hành động."""

    __tablename__ = "autonomy_settings"

    action: Mapped[str] = mapped_column(String(100), primary_key=True)
    level: Mapped[AutonomyLevel] = mapped_column(enum_col(AutonomyLevel))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AIRun(UUIDPk, CreatedAt, Base):
    """Mỗi lần gọi model một dòng (kể cả lỗi / bị chặn)."""

    __tablename__ = "ai_runs"

    task: Mapped[str] = mapped_column(String(100), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(80))
    tier: Mapped[str] = mapped_column(String(10))
    status: Mapped[AIRunStatus] = mapped_column(enum_col(AIRunStatus), index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    web_search_requests: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    web_fetch_requests: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0, server_default="0")
    cost_vnd: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    stop_reason: Mapped[str | None] = mapped_column(String(40))
    refusal_category: Mapped[str | None] = mapped_column(String(40))
    fallback_model: Mapped[str | None] = mapped_column(String(80))
    request_id: Mapped[str | None] = mapped_column(String(100))
    error_code: Mapped[str | None] = mapped_column(String(60))
    error: Mapped[str | None] = mapped_column(Text)
    input_chars: Mapped[int | None] = mapped_column(Integer)
    output: Mapped[dict[str, Any] | None]


class ApprovalItem(UUIDPk, Timestamps, Base):
    """Hàng chờ duyệt (i2): việc AI đã làm xong cần chị gật."""

    __tablename__ = "approval_items"
    __table_args__ = (
        Index("ix_approval_items_status_created", "status", "created_at"),
        Index(
            "uq_approval_items_pending_dedupe",
            "action",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status = 'pending' AND dedupe_key IS NOT NULL"),
        ),
        Index("ix_approval_items_ref", "ref_type", "ref_id"),
    )

    action: Mapped[str] = mapped_column(String(100), index=True)
    module: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'::jsonb"))
    preview: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'::jsonb"))
    edited_payload: Mapped[dict[str, Any] | None]
    status: Mapped[ApprovalStatus] = mapped_column(enum_col(ApprovalStatus), default=ApprovalStatus.PENDING)
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rationale: Mapped[str | None] = mapped_column(Text, comment="Căn cứ AI nêu")
    sources: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'::jsonb"))
    ref_type: Mapped[str | None] = mapped_column(String(60))
    ref_id: Mapped[uuid.UUID | None]
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_runs.id", ondelete="SET NULL"))
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    decision_note: Mapped[str | None] = mapped_column(Text, comment="Lời nhắn khi trả lại / ghi chú khi duyệt")
    decided_at: Mapped[datetime | None]
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    result: Mapped[dict[str, Any] | None]
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    expires_at: Mapped[datetime | None]

    @property
    def was_edited(self) -> bool:
        return bool(self.edited_payload)


class AIActivity(UUIDPk, CreatedAt, Base):
    """Nhật ký AI (i4): mọi việc AI đã thực thi (tự làm hoặc sau khi duyệt), kèm căn cứ và dữ liệu hoàn tác."""

    __tablename__ = "ai_activity"
    __table_args__ = (Index("ix_ai_activity_ref", "ref_type", "ref_id"),)

    action: Mapped[str] = mapped_column(String(100), index=True)
    module: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[ActivityMode] = mapped_column(enum_col(ActivityMode))
    rationale: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'::jsonb"))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'::jsonb"))
    result: Mapped[dict[str, Any] | None]
    ref_type: Mapped[str | None] = mapped_column(String(60))
    ref_id: Mapped[uuid.UUID | None]
    approval_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("approval_items.id", ondelete="SET NULL"))
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_runs.id", ondelete="SET NULL"))
    undo_data: Mapped[dict[str, Any] | None]
    undoable: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    undone_at: Mapped[datetime | None]
    undone_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AuditLog(UUIDPk, CreatedAt, Base):
    """Lưu vết (k3): ai duyệt gì, đổi gì, lúc nào."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id"),)

    actor_kind: Mapped[Actor] = mapped_column(enum_col(Actor))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    summary: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'::jsonb"))
    ip: Mapped[str | None] = mapped_column(String(64))
