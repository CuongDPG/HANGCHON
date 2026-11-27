"""crm — chăm khách và cộng đồng (h4–h8): ghi chú + nhãn khách, tin gửi nhóm/khách quen, tóm tắt nhóm,
nhắc mua lại, giới thiệu bạn, mời khách thử hàng."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, Index, Integer, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import (
    Base,
    CreatedAt,
    Timestamps,
    UUIDPk,
    count,
    enum_col,
    fk,
    flag,
    json_list,
    json_obj,
    money,
    money_opt,
)
from app.core.enums import Channel, StrEnum


class NoteKind(StrEnum):
    NOTE = "note"
    INTEREST = "interest"  # quan tâm gì
    PREFERENCE = "preference"
    ISSUE = "issue"  # từng gặp vấn đề
    AI_SUMMARY = "ai_summary"


class NoteSource(StrEnum):
    OWNER = "owner"
    AI = "ai"


class BroadcastKind(StrEnum):
    DROP_ANNOUNCEMENT = "drop_announcement"  # báo đợt mới (h5)
    RESTOCK = "restock"
    GENERAL = "general"


class BroadcastStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReminderStatus(StrEnum):
    SCHEDULED = "scheduled"  # tính ngày sắp hết
    PENDING_REVIEW = "pending_review"  # AI soạn tin, chờ chị (h6)
    SENT = "sent"
    SKIPPED = "skipped"  # khách không đồng ý nhận / đã mua lại
    CONVERTED = "converted"  # khách mua lại sau nhắc
    CANCELLED = "cancelled"


class ReferralUseStatus(StrEnum):
    PENDING = "pending"  # đã dùng mã, chờ đơn hoàn tất
    QUALIFIED = "qualified"
    REWARDED = "rewarded"
    VOID = "void"


class TesterInviteStatus(StrEnum):
    DRAFT = "draft"
    INVITED = "invited"
    ACCEPTED = "accepted"
    DECLINED = "declined"  # h8: khách không nhận · «Mời thử cùng»: chị không chọn người đăng ký
    SAMPLE_SENT = "sample_sent"  # «Mời thử cùng»: đã gửi hàng, bắt đầu tính hạn gửi cảm nhận
    FEEDBACK_RECEIVED = "feedback_received"
    CLOSED = "closed"
    # «Mời thử cùng» (27/11): applied → selected → paid → sample_sent → feedback_received → refund_proposed → refunded
    APPLIED = "applied"
    SELECTED = "selected"
    PAID = "paid"
    REFUND_PROPOSED = "refund_proposed"
    REFUNDED = "refunded"
    FEEDBACK_MISSED = "feedback_missed"  # quá hạn chưa gửi cảm nhận → không hoàn tiền, sổ người dùng thử gắn «loại trừ»


class CotrialOfferStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class CustomerNote(UUIDPk, Timestamps, Base):
    """Sổ khách (h4): ghi chú, quan tâm — do chị ghi hoặc AI rút từ hội thoại."""

    __tablename__ = "customer_notes"
    __table_args__ = (Index("ix_customer_notes_customer", "customer_id", "created_at"),)

    customer_id: Mapped[uuid.UUID] = fk("customers", ondelete="CASCADE", nullable=False, index=False)
    kind: Mapped[NoteKind] = mapped_column(enum_col(NoteKind), default=NoteKind.NOTE)
    source: Mapped[NoteSource] = mapped_column(enum_col(NoteSource), default=NoteSource.OWNER)
    body: Mapped[str] = mapped_column(Text)
    ref_type: Mapped[str | None] = mapped_column(String(60), comment="Rút từ đâu: messages, orders...")
    ref_id: Mapped[uuid.UUID | None]
    pinned: Mapped[bool] = flag()
    created_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)


class CustomerTag(UUIDPk, CreatedAt, Base):
    __tablename__ = "customer_tags"
    __table_args__ = (UniqueConstraint("customer_id", "tag", name="uq_customer_tags_tag"),)

    customer_id: Mapped[uuid.UUID] = fk("customers", ondelete="CASCADE", nullable=False)
    tag: Mapped[str] = mapped_column(String(60), index=True)
    source: Mapped[NoteSource] = mapped_column(enum_col(NoteSource), default=NoteSource.OWNER)


class Broadcast(UUIDPk, Timestamps, Base):
    """Tin gửi nhóm khách quen / nhiều khách (h5): AI soạn, chị duyệt rồi mới gửi."""

    __tablename__ = "broadcasts"

    kind: Mapped[BroadcastKind] = mapped_column(enum_col(BroadcastKind), default=BroadcastKind.GENERAL)
    channel: Mapped[Channel] = mapped_column(enum_col(Channel))
    channel_account_id: Mapped[uuid.UUID | None] = fk("channel_accounts")
    drop_id: Mapped[uuid.UUID | None] = fk("drops")
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    media: Mapped[list[Any]] = json_list()
    audience: Mapped[dict[str, Any]] = json_obj(comment='{"tags": [...], "is_regular": true, "group": "..."}')
    status: Mapped[BroadcastStatus] = mapped_column(enum_col(BroadcastStatus), default=BroadcastStatus.DRAFT)
    scheduled_at: Mapped[datetime | None]
    sent_at: Mapped[datetime | None]
    recipient_count: Mapped[int] = count()
    delivered_count: Mapped[int] = count()
    ai_generated: Mapped[bool] = flag()
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)


class GroupDigest(UUIDPk, CreatedAt, Base):
    """Tóm tắt thảo luận trong nhóm khách quen (h5)."""

    __tablename__ = "group_digests"

    thread_id: Mapped[uuid.UUID | None] = fk("threads", comment="Thread nhóm trong hộp thư")
    channel_account_id: Mapped[uuid.UUID | None] = fk("channel_accounts")
    period_start: Mapped[datetime]
    period_end: Mapped[datetime]
    summary: Mapped[str] = mapped_column(Text)
    highlights: Mapped[list[Any]] = json_list()
    open_questions: Mapped[list[Any]] = json_list(comment="Câu hỏi chưa ai trả lời")
    product_mentions: Mapped[list[Any]] = json_list()
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)


class ReorderReminder(UUIDPk, Timestamps, Base):
    """Nhắc mua lại đúng lúc (h6): món tiêu hao sắp hết thì nhắc đúng người, không nhắn đại trà."""

    __tablename__ = "reorder_reminders"
    __table_args__ = (
        UniqueConstraint("order_item_id", name="uq_reorder_reminders_order_item"),
        Index("ix_reorder_reminders_status_due", "status", "due_on"),
    )

    customer_id: Mapped[uuid.UUID] = fk("customers", ondelete="CASCADE", nullable=False)
    product_id: Mapped[uuid.UUID] = fk("products", ondelete="CASCADE", nullable=False)
    order_id: Mapped[uuid.UUID | None] = fk("orders")
    order_item_id: Mapped[uuid.UUID | None] = fk("order_items", index=False)
    due_on: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text, comment="Vì sao nhắc lúc này")
    channel: Mapped[Channel | None] = mapped_column(enum_col(Channel))
    message_body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ReminderStatus] = mapped_column(enum_col(ReminderStatus), default=ReminderStatus.SCHEDULED)
    sent_at: Mapped[datetime | None]
    converted_order_id: Mapped[uuid.UUID | None] = fk("orders")
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)


class Referral(UUIDPk, Timestamps, Base):
    """Mã giới thiệu bạn (h7): quà cho cả hai. Mỗi khách giới thiệu một mã."""

    __tablename__ = "referrals"

    code: Mapped[str] = mapped_column(String(30), unique=True)
    referrer_customer_id: Mapped[uuid.UUID] = fk("customers", ondelete="CASCADE", nullable=False, unique=True)
    is_active: Mapped[bool] = flag(True)
    reward_referrer_vnd: Mapped[int] = money()
    reward_referred_vnd: Mapped[int] = money()
    uses_count: Mapped[int] = count()
    rewarded_count: Mapped[int] = count()
    expires_on: Mapped[date | None] = mapped_column(Date)


class ReferralUse(UUIDPk, Timestamps, Base):
    __tablename__ = "referral_uses"
    __table_args__ = (UniqueConstraint("referred_customer_id", name="uq_referral_uses_referred"),)

    referral_id: Mapped[uuid.UUID] = fk("referrals", ondelete="CASCADE", nullable=False)
    referred_customer_id: Mapped[uuid.UUID] = fk("customers", ondelete="CASCADE", nullable=False, index=False)
    order_id: Mapped[uuid.UUID | None] = fk("orders")
    status: Mapped[ReferralUseStatus] = mapped_column(enum_col(ReferralUseStatus), default=ReferralUseStatus.PENDING)
    rewarded_at: Mapped[datetime | None]


class TesterInvite(UUIDPk, Timestamps, Base):
    """Khách thử hàng cùng chị (h8): mời vài khách quen dùng thử mẫu trước khi chị quyết định chọn."""

    __tablename__ = "tester_invites"
    __table_args__ = (UniqueConstraint("candidate_id", "customer_id", name="uq_tester_invites_pair"),)

    candidate_id: Mapped[uuid.UUID] = fk("candidates", ondelete="CASCADE", nullable=False)
    customer_id: Mapped[uuid.UUID] = fk("customers", ondelete="CASCADE", nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, comment="Đường link gửi cảm nhận")
    status: Mapped[TesterInviteStatus] = mapped_column(enum_col(TesterInviteStatus), default=TesterInviteStatus.DRAFT)
    message: Mapped[str | None] = mapped_column(Text)
    invited_at: Mapped[datetime | None]
    responded_at: Mapped[datetime | None]
    sample_sent_at: Mapped[datetime | None]
    feedback: Mapped[str | None] = mapped_column(Text)
    feedback_rating: Mapped[int | None] = mapped_column(SmallInteger)
    feedback_media: Mapped[list[Any]] = json_list()
    feedback_at: Mapped[datetime | None]
    reward_note: Mapped[str | None] = mapped_column(String(300))
    trial_days: Mapped[int | None] = mapped_column(Integer)
    # «Mời thử cùng» (27/11): một dòng = một người đăng ký thử một lời mời; tiền theo dõi tay, không qua orders
    offer_id: Mapped[uuid.UUID | None] = fk("cotrial_offers", ondelete="CASCADE", comment="Null = lời mời h8 cũ")
    selected_at: Mapped[datetime | None]
    paid_at: Mapped[datetime | None]
    paid_vnd: Mapped[int | None] = money_opt(comment="Chị xác nhận đã nhận (giá thường của lời mời)")
    feedback_due_at: Mapped[datetime | None] = mapped_column(comment="Hạn gửi cảm nhận = lúc gửi hàng + số ngày")
    reminded_at: Mapped[datetime | None]
    feedback_answers: Mapped[dict[str, Any]] = json_obj(
        comment='{"liked","disliked","would_buy","refund_account"} — chỉ ở desk, không ra website'
    )
    refund_vnd: Mapped[int | None] = money_opt()
    refund_approval_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    refunded_at: Mapped[datetime | None]


class TesterProfile(UUIDPk, Timestamps, Base):
    """Sổ người dùng thử (27/11): khách đăng ký một lần ở /dung-thu, đồng ý điều kiện «Mời thử cùng»."""

    __tablename__ = "tester_profiles"

    customer_id: Mapped[uuid.UUID] = fk("customers", ondelete="CASCADE", nullable=False, unique=True, index=False)
    interests: Mapped[list[Any]] = json_list(comment="Nhóm hàng quan tâm (slug danh mục)")
    agreed_at: Mapped[datetime] = mapped_column(comment="Lúc đồng ý điều kiện: mua giá thường, gửi cảm nhận đúng hạn")
    excluded: Mapped[bool] = flag(comment="Lỡ hạn cảm nhận → không chọn ở lời mời sau (chị bỏ qua được)")
    excluded_reason: Mapped[str | None] = mapped_column(String(300))


class CotrialOffer(UUIDPk, Timestamps, Base):
    """Lời mời «Mời thử cùng» cho một món đang thử: link riêng /dung-thu/m/<token>, không liệt kê ở đâu."""

    __tablename__ = "cotrial_offers"

    candidate_id: Mapped[uuid.UUID] = fk("candidates", ondelete="CASCADE", nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, comment="Link riêng chị tự gửi (Zalo...)")
    status: Mapped[CotrialOfferStatus] = mapped_column(enum_col(CotrialOfferStatus), default=CotrialOfferStatus.OPEN)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    photos: Mapped[list[Any]] = json_list(comment='Bản sao công khai chị chọn (đã bỏ EXIF) [{"files": {...}}]')
    price_vnd: Mapped[int] = money(comment="Giá thường người thử trả")
    refund_vnd: Mapped[int | None] = money_opt(comment="Hoàn lại khi gửi cảm nhận đủ (số tiền)")
    refund_pct: Mapped[int | None] = mapped_column(SmallInteger, comment="…hoặc theo % giá")
    ask_price_vnd: Mapped[int | None] = money_opt(comment="Câu hỏi «Giá X bạn có mua không?» (trống = giá thường)")
    slots: Mapped[int] = mapped_column(SmallInteger, default=3, server_default="3")
    feedback_days: Mapped[int] = mapped_column(SmallInteger, default=10, server_default="10")
    created_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)
