"""assistant — trợ lý hỏi đáp trên web (e7): trả lời từ hồ sơ thẩm định, có dẫn nguồn; không biết thì chuyển chị."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, CreatedAt, Timestamps, UUIDPk, count, enum_col, fk, flag, json_list
from app.core.enums import StrEnum


class ConversationStatus(StrEnum):
    OPEN = "open"
    HANDED_OFF = "handed_off"  # đã chuyển chị (tạo thread trong hộp thư)
    CLOSED = "closed"


class AssistantRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    OWNER = "owner"  # chị trả lời thay trong cùng khung chat


class AnswerBasis(StrEnum):
    PRODUCT = "product"
    ASSESSMENT = "assessment"
    REVIEWS = "reviews"
    POLICY = "policy"  # chính sách giao hàng / đổi trả
    ORDER = "order"
    NONE = "none"  # không có căn cứ → nói không biết


class Feedback(StrEnum):
    UP = "up"
    DOWN = "down"


class AssistantConversation(UUIDPk, Timestamps, Base):
    __tablename__ = "assistant_conversations"
    __table_args__ = (Index("ix_assistant_conversations_session", "session_key", "created_at"),)

    session_key: Mapped[str] = mapped_column(String(64), comment="Mã phiên ẩn danh (cookie) của khách")
    customer_id: Mapped[uuid.UUID | None] = fk("customers")
    product_id: Mapped[uuid.UUID | None] = fk("products", comment="Đang hỏi về món nào")
    page_path: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[ConversationStatus] = mapped_column(enum_col(ConversationStatus), default=ConversationStatus.OPEN)
    handed_off_at: Mapped[datetime | None]
    handoff_reason: Mapped[str | None] = mapped_column(Text)
    thread_id: Mapped[uuid.UUID | None] = fk("threads", comment="Thread hộp thư khi chuyển chị")
    contact: Mapped[str | None] = mapped_column(String(200), comment="Khách để lại SĐT/Zalo để chị trả lời")
    message_count: Mapped[int] = count()
    last_message_at: Mapped[datetime | None]
    ip_hash: Mapped[str | None] = mapped_column(String(64), comment="Chống lạm dụng, không lưu IP thô")

    messages: Mapped[list[AssistantMessage]] = relationship(
        back_populates="conversation",
        lazy="raise",
        cascade="all, delete-orphan",
        order_by="AssistantMessage.created_at",
    )


class AssistantMessage(UUIDPk, CreatedAt, Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (Index("ix_assistant_messages_conversation", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = fk("assistant_conversations", ondelete="CASCADE", nullable=False, index=False)
    role: Mapped[AssistantRole] = mapped_column(enum_col(AssistantRole))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[Any]] = json_list(comment='[{"type":"assessment|product|review_digest","id","quote"}]')
    basis: Mapped[AnswerBasis | None] = mapped_column(enum_col(AnswerBasis))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    unknown: Mapped[bool] = flag(comment="AI không biết → đề nghị chuyển chị")
    feedback: Mapped[Feedback | None] = mapped_column(enum_col(Feedback))
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)

    conversation: Mapped[AssistantConversation] = relationship(back_populates="messages", lazy="raise")
