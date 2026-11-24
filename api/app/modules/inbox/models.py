"""inbox — hộp thư gộp (h1–h3, g6): tài khoản kênh của chị, hội thoại, tin nhắn/bình luận, câu trả lời AI soạn."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, CreatedAt, Timestamps, UUIDPk, count, enum_col, fk, flag, json_list, json_obj
from app.core.enums import Actor, Channel, StrEnum


class AccountStatus(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    MOCK = "mock"


class ThreadKind(StrEnum):
    COMMENT = "comment"  # chuỗi bình luận dưới một bài
    DIRECT_MESSAGE = "direct_message"
    GROUP = "group"  # nhóm Zalo khách quen
    WEB_CHAT = "web_chat"  # chuyển từ trợ lý web


class ThreadStatus(StrEnum):
    OPEN = "open"
    NEEDS_OWNER = "needs_owner"  # chuyển cho chị (h3): khiếu nại, hàng lỗi, sức khoẻ
    WAITING_CUSTOMER = "waiting_customer"
    AI_HANDLED = "ai_handled"
    CLOSED = "closed"
    SPAM = "spam"


class EscalationReason(StrEnum):
    COMPLAINT = "complaint"
    DEFECT = "defect"
    HEALTH = "health"
    REFUND = "refund"
    LOW_CONFIDENCE = "low_confidence"
    OTHER = "other"


class Intent(StrEnum):
    ASK_PRICE = "ask_price"
    ASK_STOCK = "ask_stock"
    ASK_SHIPPING = "ask_shipping"
    ASK_PRODUCT = "ask_product"
    PURCHASE = "purchase"  # muốn mua (g6)
    ORDER_STATUS = "order_status"
    COMPLAINT = "complaint"
    FIND_REQUEST = "find_request"  # nhờ tìm món (→ a6)
    SMALL_TALK = "small_talk"
    OTHER = "other"


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus(StrEnum):
    RECEIVED = "received"
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class ReplyKind(StrEnum):
    INSTANT = "instant"  # câu giá / còn hàng / phí giao: AI trả lời ngay (h2)
    DRAFT = "draft"  # AI soạn nháp chờ chị


class ReplyStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SENT = "sent"
    AUTO_SENT = "auto_sent"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"  # có tin mới, bản nháp cũ hết hợp


class ChannelAccount(UUIDPk, Timestamps, Base):
    """Trang/tài khoản của chị trên từng kênh. Không lưu token ở đây — token nằm trong env/kho bí mật."""

    __tablename__ = "channel_accounts"
    __table_args__ = (UniqueConstraint("channel", "external_id", name="uq_channel_accounts_external"),)

    channel: Mapped[Channel] = mapped_column(enum_col(Channel))
    name: Mapped[str] = mapped_column(String(200))
    external_id: Mapped[str] = mapped_column(String(200))
    driver: Mapped[str] = mapped_column(String(30), default="mock")
    status: Mapped[AccountStatus] = mapped_column(enum_col(AccountStatus), default=AccountStatus.MOCK)
    can_publish: Mapped[bool] = flag(True)
    can_message: Mapped[bool] = flag(True)
    settings: Mapped[dict[str, Any]] = json_obj()
    connected_at: Mapped[datetime | None]
    last_synced_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)


class Thread(UUIDPk, Timestamps, Base):
    __tablename__ = "threads"
    __table_args__ = (
        UniqueConstraint("channel_account_id", "external_thread_id", name="uq_threads_external"),
        Index("ix_threads_status_last", "status", "last_message_at"),
    )

    channel_account_id: Mapped[uuid.UUID | None] = fk("channel_accounts", index=False)
    channel: Mapped[Channel] = mapped_column(enum_col(Channel))
    kind: Mapped[ThreadKind] = mapped_column(enum_col(ThreadKind))
    external_thread_id: Mapped[str] = mapped_column(String(200))
    external_post_id: Mapped[str | None] = mapped_column(String(200))
    scheduled_post_id: Mapped[uuid.UUID | None] = fk("scheduled_posts", comment="Bình luận dưới bài nào của mình")
    customer_id: Mapped[uuid.UUID | None] = fk("customers")
    participant_name: Mapped[str | None] = mapped_column(String(200))
    participant_external_id: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[ThreadStatus] = mapped_column(enum_col(ThreadStatus), default=ThreadStatus.OPEN)
    needs_owner: Mapped[bool] = flag()
    escalation_reason: Mapped[EscalationReason | None] = mapped_column(enum_col(EscalationReason))
    last_intent: Mapped[Intent | None] = mapped_column(enum_col(Intent))
    snippet: Mapped[str | None] = mapped_column(String(300))
    last_message_at: Mapped[datetime | None]
    last_inbound_at: Mapped[datetime | None]
    unread_count: Mapped[int] = count()
    product_id: Mapped[uuid.UUID | None] = fk("products", comment="Đang hỏi về món nào")
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL", use_alter=True), index=True, comment="Đơn chốt từ hội thoại (g6)"
    )
    assigned_user_id: Mapped[uuid.UUID | None] = fk("users", index=False)
    summary: Mapped[str | None] = mapped_column(Text, comment="AI tóm tắt hội thoại (nhóm khách quen h5)")

    messages: Mapped[list[Message]] = relationship(
        back_populates="thread", lazy="raise", cascade="all, delete-orphan", order_by="Message.sent_at"
    )


class Message(UUIDPk, CreatedAt, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("thread_id", "external_message_id", name="uq_messages_external"),
        Index("ix_messages_thread_sent", "thread_id", "sent_at"),
    )

    thread_id: Mapped[uuid.UUID] = fk("threads", ondelete="CASCADE", nullable=False, index=False)
    direction: Mapped[Direction] = mapped_column(enum_col(Direction))
    sender: Mapped[Actor] = mapped_column(enum_col(Actor), comment="customer / owner / helper / ai")
    external_message_id: Mapped[str | None] = mapped_column(String(200))
    author_name: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    attachments: Mapped[list[Any]] = json_list()
    sent_at: Mapped[datetime]
    status: Mapped[MessageStatus] = mapped_column(enum_col(MessageStatus), default=MessageStatus.RECEIVED)
    intent: Mapped[Intent | None] = mapped_column(enum_col(Intent))
    intent_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    extracted: Mapped[dict[str, Any]] = json_obj(comment="Thông tin rút được: món, số lượng, SĐT, địa chỉ (g6)")
    ai_generated: Mapped[bool] = flag()
    read_at: Mapped[datetime | None]
    error: Mapped[str | None] = mapped_column(Text)

    thread: Mapped[Thread] = relationship(back_populates="messages", lazy="raise")


class ReplyDraft(UUIDPk, Timestamps, Base):
    """Câu trả lời AI soạn sẵn (h2). Loại `instant` có thể tự gửi theo mức tự chủ; còn lại chờ chị."""

    __tablename__ = "reply_drafts"
    __table_args__ = (Index("ix_reply_drafts_thread_status", "thread_id", "status"),)

    thread_id: Mapped[uuid.UUID] = fk("threads", ondelete="CASCADE", nullable=False, index=False)
    reply_to_message_id: Mapped[uuid.UUID | None] = fk("messages")
    kind: Mapped[ReplyKind] = mapped_column(enum_col(ReplyKind))
    intent: Mapped[Intent | None] = mapped_column(enum_col(Intent))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[ReplyStatus] = mapped_column(enum_col(ReplyStatus), default=ReplyStatus.PENDING_REVIEW)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    sources: Mapped[list[Any]] = json_list(comment="Căn cứ: sản phẩm, tồn kho, bảng phí giao")
    draft_order: Mapped[dict[str, Any]] = json_obj(comment="Đơn nháp đề xuất khi khách muốn mua (g6)")
    missing_info: Mapped[list[Any]] = json_list(comment="Còn thiếu gì để chốt đơn")
    sent_message_id: Mapped[uuid.UUID | None] = fk("messages", index=False)
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)
