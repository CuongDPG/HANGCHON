"""orders — đơn hàng và vận hành (e4, e5, g1–g9): khách, đơn, dòng hàng, hành trình đơn, thanh toán, vận đơn,
đổi trả, báo tin, đồng bộ sàn."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
from app.core.enums import Actor, Carrier, Channel, ShippingStatus, StrEnum


class OrderStatus(StrEnum):
    DRAFT = "draft"  # đơn nháp AI tạo từ tin nhắn (g6), chờ chị
    PENDING_PAYMENT = "pending_payment"  # chờ chuyển khoản
    CONFIRMED = "confirmed"  # đã nhận đơn (đã trả tiền hoặc COD)
    AWAITING_STOCK = "awaiting_stock"  # hàng đang về (đơn trong đợt)
    READY_TO_SHIP = "ready_to_ship"
    SHIPPING = "shipping"
    DELIVERED = "delivered"
    COMPLETED = "completed"  # hết hạn đổi trả
    CANCELLED = "cancelled"
    RETURNED = "returned"


# Một cách tính suất/tồn duy nhất (orders + catalog): đơn còn sống mà chưa trả (`paid_at` trống) do orders cộng
# «giữ tạm» khi kiểm còn hàng; đơn đã trả do catalog ghi vào `drop_items.slots_reserved` / `inventory_items.reserved`.
RELEASED_STATUSES = (OrderStatus.CANCELLED, OrderStatus.RETURNED)  # đơn đã nhả suất/tồn
PRE_SHIP_STATUSES = (  # đơn chưa rời kho (món giữ sẵn còn nằm trong `on_hand`)
    OrderStatus.PENDING_PAYMENT,
    OrderStatus.CONFIRMED,
    OrderStatus.AWAITING_STOCK,
    OrderStatus.READY_TO_SHIP,
)


class PaymentMethod(StrEnum):
    BANK_TRANSFER = "bank_transfer"  # VietQR, tự xác nhận
    COD = "cod"
    MARKETPLACE = "marketplace"  # sàn thu hộ
    CASH = "cash"


class PaymentState(StrEnum):
    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentStatus(StrEnum):
    """Trạng thái một khoản tiền."""

    RECEIVED = "received"  # tiền đã về, chưa khớp đơn
    MATCHED = "matched"  # đã khớp đơn (g2)
    NEEDS_REVIEW = "needs_review"  # khớp không chắc (sai số tiền, nội dung lạ)
    IGNORED = "ignored"  # không phải tiền đơn hàng
    REFUNDED = "refunded"
    FAILED = "failed"


class PaymentDirection(StrEnum):
    IN = "in"
    OUT = "out"  # hoàn tiền


class MatchMethod(StrEnum):
    AUTO_CODE = "auto_code"  # khớp theo nội dung chuyển khoản
    AUTO_AMOUNT = "auto_amount"  # khớp theo số tiền + thời gian
    MANUAL = "manual"
    COD_SETTLEMENT = "cod_settlement"


class FulfillmentSource(StrEnum):
    DROP = "drop"
    STOCK = "stock"


class ReturnKind(StrEnum):
    RETURN = "return"
    EXCHANGE = "exchange"
    REFUND_ONLY = "refund_only"


class ReturnReason(StrEnum):
    DEFECT = "defect"
    WRONG_ITEM = "wrong_item"
    DAMAGED_IN_SHIPPING = "damaged_in_shipping"
    NOT_AS_DESCRIBED = "not_as_described"
    CHANGED_MIND = "changed_mind"
    OTHER = "other"


class ReturnStatus(StrEnum):
    REQUESTED = "requested"
    PENDING_DECISION = "pending_decision"  # AI đã kiểm điều kiện + soạn phương án, chờ chị (g7, locked)
    APPROVED = "approved"
    REJECTED = "rejected"
    AWAITING_ITEM = "awaiting_item"
    RECEIVED = "received"
    REFUNDED = "refunded"
    EXCHANGED = "exchanged"
    CLOSED = "closed"


class NotificationEvent(StrEnum):
    ORDER_RECEIVED = "order_received"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PAYMENT_REMINDER = "payment_reminder"
    STOCK_ARRIVING = "stock_arriving"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    REVIEW_REQUEST = "review_request"
    RETURN_UPDATE = "return_update"
    REORDER_REMINDER = "reorder_reminder"
    BROADCAST = "broadcast"
    FIND_REQUEST_FOUND = "find_request_found"
    OTHER = "other"


class NotificationStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"  # khách không có kênh / không đồng ý nhận


class ListingStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class Customer(UUIDPk, Timestamps, Base):
    """Khách (h4 sổ khách đọc từ đây + crm). Không cần tài khoản: nhận diện bằng SĐT và định danh theo kênh."""

    __tablename__ = "customers"

    name: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, comment="Chuẩn hoá dạng 0xxxxxxxxx")
    email: Mapped[str | None] = mapped_column(String(254), index=True)
    default_address: Mapped[dict[str, Any]] = json_obj()
    first_channel: Mapped[Channel | None] = mapped_column(enum_col(Channel))
    first_order_at: Mapped[datetime | None]
    last_order_at: Mapped[datetime | None] = mapped_column(index=True)
    order_count: Mapped[int] = count()
    total_spent_vnd: Mapped[int] = money()
    interests: Mapped[list[Any]] = json_list(comment="AI tóm tắt quan tâm gì")
    profile_summary: Mapped[str | None] = mapped_column(Text, comment="AI: đã mua gì, hỏi gì, quan tâm gì")
    is_regular: Mapped[bool] = flag(comment="Khách quen (h5)")
    marketing_opt_in: Mapped[bool] = flag(comment="Đồng ý nhận tin đợt mới / nhắc mua lại")
    is_blocked: Mapped[bool] = flag()
    merged_into_id: Mapped[uuid.UUID | None] = fk("customers", comment="Gộp hồ sơ trùng giữa các kênh")
    referred_by_id: Mapped[uuid.UUID | None] = fk("customers")

    identities: Mapped[list[CustomerIdentity]] = relationship(
        back_populates="customer", lazy="selectin", cascade="all, delete-orphan"
    )


class CustomerIdentity(UUIDPk, CreatedAt, Base):
    """Định danh của khách trên từng kênh (PSID Facebook, IG id, Zalo id...) để hộp thư gộp nhận ra cùng một người."""

    __tablename__ = "customer_identities"
    __table_args__ = (UniqueConstraint("channel", "external_id", name="uq_customer_identities_channel_external"),)

    customer_id: Mapped[uuid.UUID] = fk("customers", ondelete="CASCADE", nullable=False)
    channel: Mapped[Channel] = mapped_column(enum_col(Channel))
    external_id: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str | None] = mapped_column(String(200))
    profile_url: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer] = relationship(back_populates="identities", lazy="raise")


class Order(UUIDPk, Timestamps, Base):
    """Đơn hàng từ mọi kênh (g1). Tra cứu công khai bằng SĐT + mã đơn (e5)."""

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_status_placed", "status", "placed_at"),
        Index("ix_orders_phone_code", "recipient_phone", "code"),
        UniqueConstraint("channel", "external_id", name="uq_orders_channel_external"),
    )

    code: Mapped[str] = mapped_column(String(20), unique=True, comment="Mã đơn cho khách, vd HC2611250001")
    customer_id: Mapped[uuid.UUID | None] = fk("customers")
    channel: Mapped[Channel] = mapped_column(enum_col(Channel), default=Channel.WEB)
    external_id: Mapped[str | None] = mapped_column(String(120), comment="Mã đơn trên sàn (g9)")
    thread_id: Mapped[uuid.UUID | None] = fk("threads", comment="Tin nhắn/bình luận đã chốt đơn (g6)")
    drop_id: Mapped[uuid.UUID | None] = fk("drops")
    status: Mapped[OrderStatus] = mapped_column(enum_col(OrderStatus), default=OrderStatus.PENDING_PAYMENT)
    payment_method: Mapped[PaymentMethod] = mapped_column(enum_col(PaymentMethod), default=PaymentMethod.BANK_TRANSFER)
    payment_state: Mapped[PaymentState] = mapped_column(enum_col(PaymentState), default=PaymentState.UNPAID)
    transfer_content: Mapped[str | None] = mapped_column(String(60), unique=True, comment="Nội dung CK để khớp (g2)")
    # người nhận
    recipient_name: Mapped[str] = mapped_column(String(120))
    recipient_phone: Mapped[str] = mapped_column(String(20))
    address_line: Mapped[str | None] = mapped_column(String(300))
    ward: Mapped[str | None] = mapped_column(String(120))
    district: Mapped[str | None] = mapped_column(String(120))
    province: Mapped[str | None] = mapped_column(String(120))
    address_codes: Mapped[dict[str, Any]] = json_obj(comment="Mã hành chính theo hãng vận chuyển")
    # tiền
    subtotal_vnd: Mapped[int] = money()
    shipping_fee_vnd: Mapped[int] = money()
    discount_vnd: Mapped[int] = money()
    total_vnd: Mapped[int] = money()
    paid_vnd: Mapped[int] = money()
    refunded_vnd: Mapped[int] = money()
    deposit_required_vnd: Mapped[int] = money(comment="Cọc yêu cầu với đơn trong đợt")
    cod_amount_vnd: Mapped[int] = money()
    referral_code: Mapped[str | None] = mapped_column(String(30), index=True)
    # mốc
    placed_at: Mapped[datetime]
    confirmed_at: Mapped[datetime | None]
    paid_at: Mapped[datetime | None]
    shipped_at: Mapped[datetime | None]
    delivered_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    payment_due_at: Mapped[datetime | None]
    customer_note: Mapped[str | None] = mapped_column(Text)
    internal_note: Mapped[str | None] = mapped_column(Text)
    ai_generated: Mapped[bool] = flag(comment="AI tạo từ tin nhắn (g6)")
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    raw: Mapped[dict[str, Any]] = json_obj()

    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", lazy="selectin", cascade="all, delete-orphan", order_by="OrderItem.position"
    )
    events: Mapped[list[OrderEvent]] = relationship(
        back_populates="order", lazy="raise", cascade="all, delete-orphan", order_by="OrderEvent.occurred_at"
    )


class OrderItem(UUIDPk, Timestamps, Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    order_id: Mapped[uuid.UUID] = fk("orders", ondelete="CASCADE", nullable=False)
    position: Mapped[int] = count()
    product_id: Mapped[uuid.UUID | None] = fk("products")
    variant_id: Mapped[uuid.UUID | None] = fk("product_variants")
    drop_item_id: Mapped[uuid.UUID | None] = fk("drop_items")
    fulfillment_source: Mapped[FulfillmentSource] = mapped_column(
        enum_col(FulfillmentSource), default=FulfillmentSource.DROP
    )
    name: Mapped[str] = mapped_column(String(300), comment="Ảnh chụp tên lúc đặt")
    variant_name: Mapped[str | None] = mapped_column(String(120))
    sku: Mapped[str | None] = mapped_column(String(60))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_vnd: Mapped[int] = money()
    discount_vnd: Mapped[int] = money()
    line_total_vnd: Mapped[int] = money()
    unit_cost_vnd: Mapped[int | None] = money_opt(comment="Giá vốn lúc bán (biên lợi nhuận i5, sổ k1)")

    order: Mapped[Order] = relationship(back_populates="items", lazy="raise")


class OrderEvent(UUIDPk, Base):
    """Hành trình đơn (e5): mốc hiển thị cho khách và nhật ký nội bộ."""

    __tablename__ = "order_events"
    __table_args__ = (Index("ix_order_events_order", "order_id", "occurred_at"),)

    order_id: Mapped[uuid.UUID] = fk("orders", ondelete="CASCADE", nullable=False, index=False)
    kind: Mapped[str] = mapped_column(String(40), comment="status_changed, payment_received, shipment_update, note...")
    status: Mapped[OrderStatus | None] = mapped_column(enum_col(OrderStatus))
    title: Mapped[str] = mapped_column(String(200), comment="Câu tiếng Việt cho khách")
    detail: Mapped[str | None] = mapped_column(Text)
    visible_to_customer: Mapped[bool] = flag(True)
    actor: Mapped[Actor] = mapped_column(enum_col(Actor), default=Actor.SYSTEM)
    occurred_at: Mapped[datetime]
    data: Mapped[dict[str, Any]] = json_obj()

    order: Mapped[Order] = relationship(back_populates="events", lazy="raise")


class Payment(UUIDPk, Timestamps, Base):
    """Khoản tiền vào/ra. Tiền chuyển khoản tới trước, khớp đơn sau (g2); hoàn tiền là direction=out."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_payments_provider_external"),
        Index("ix_payments_status_received", "status", "received_at"),
    )

    order_id: Mapped[uuid.UUID | None] = fk("orders")
    direction: Mapped[PaymentDirection] = mapped_column(enum_col(PaymentDirection), default=PaymentDirection.IN)
    method: Mapped[PaymentMethod] = mapped_column(enum_col(PaymentMethod))
    provider: Mapped[str] = mapped_column(String(30), comment="mock / sepay / cod / manual")
    external_id: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[PaymentStatus] = mapped_column(enum_col(PaymentStatus), default=PaymentStatus.RECEIVED)
    amount_vnd: Mapped[int] = money()
    content: Mapped[str | None] = mapped_column(Text, comment="Nội dung chuyển khoản")
    payer_name: Mapped[str | None] = mapped_column(String(200))
    payer_account: Mapped[str | None] = mapped_column(String(60))
    received_at: Mapped[datetime]
    matched_at: Mapped[datetime | None]
    match_method: Mapped[MatchMethod | None] = mapped_column(enum_col(MatchMethod))
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    refund_of_id: Mapped[uuid.UUID | None] = fk("payments")
    return_id: Mapped[uuid.UUID | None] = fk("returns")
    note: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict[str, Any]] = json_obj()


class Shipment(UUIDPk, Timestamps, Base):
    """Vận đơn (g4): chọn hãng theo phí + thời gian, in nhãn, theo dõi."""

    __tablename__ = "shipments"
    __table_args__ = (UniqueConstraint("carrier", "tracking_code", name="uq_shipments_carrier_tracking"),)

    order_id: Mapped[uuid.UUID | None] = fk("orders", ondelete="CASCADE")
    tester_invite_id: Mapped[uuid.UUID | None] = fk("tester_invites", comment="Gửi mẫu cho khách thử (h8)")
    return_id: Mapped[uuid.UUID | None] = fk("returns", comment="Vận đơn hoàn / đổi")
    carrier: Mapped[Carrier] = mapped_column(enum_col(Carrier))
    service: Mapped[str | None] = mapped_column(String(60))
    tracking_code: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[ShippingStatus] = mapped_column(enum_col(ShippingStatus), default=ShippingStatus.PENDING, index=True)
    fee_vnd: Mapped[int] = money()
    cod_amount_vnd: Mapped[int] = money()
    weight_grams: Mapped[int | None] = mapped_column(Integer)
    label_url: Mapped[str | None] = mapped_column(Text)
    label_storage_key: Mapped[str | None] = mapped_column(String(300))
    quotes: Mapped[list[Any]] = json_list(comment="Các báo giá đã so khi chọn hãng")
    selection_reason: Mapped[str | None] = mapped_column(Text)
    expected_delivery_at: Mapped[datetime | None]
    picked_up_at: Mapped[datetime | None]
    delivered_at: Mapped[datetime | None]
    last_synced_at: Mapped[datetime | None]
    raw: Mapped[dict[str, Any]] = json_obj()

    events: Mapped[list[ShipmentEvent]] = relationship(
        back_populates="shipment", lazy="selectin", cascade="all, delete-orphan", order_by="ShipmentEvent.occurred_at"
    )


class ShipmentEvent(UUIDPk, CreatedAt, Base):
    __tablename__ = "shipment_events"
    __table_args__ = (UniqueConstraint("shipment_id", "status", "occurred_at", name="uq_shipment_events_status_time"),)

    shipment_id: Mapped[uuid.UUID] = fk("shipments", ondelete="CASCADE", nullable=False)
    status: Mapped[ShippingStatus] = mapped_column(enum_col(ShippingStatus))
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200))
    occurred_at: Mapped[datetime]
    raw: Mapped[dict[str, Any]] = json_obj()

    shipment: Mapped[Shipment] = relationship(back_populates="events", lazy="raise")


class Return(UUIDPk, Timestamps, Base):
    """Đổi trả, hoàn tiền (g7): AI kiểm điều kiện và soạn phương án; chị quyết (luôn khoá ở mức hỏi)."""

    __tablename__ = "returns"

    code: Mapped[str] = mapped_column(String(20), unique=True)
    order_id: Mapped[uuid.UUID] = fk("orders", ondelete="CASCADE", nullable=False)
    order_item_id: Mapped[uuid.UUID | None] = fk("order_items")
    customer_id: Mapped[uuid.UUID | None] = fk("customers")
    thread_id: Mapped[uuid.UUID | None] = fk("threads")
    kind: Mapped[ReturnKind] = mapped_column(enum_col(ReturnKind))
    reason: Mapped[ReturnReason] = mapped_column(enum_col(ReturnReason))
    description: Mapped[str | None] = mapped_column(Text)
    photos: Mapped[list[Any]] = json_list()
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[ReturnStatus] = mapped_column(enum_col(ReturnStatus), default=ReturnStatus.REQUESTED, index=True)
    eligibility: Mapped[dict[str, Any]] = json_obj(comment="AI kiểm: trong hạn, đúng điều kiện, căn cứ chính sách")
    proposal: Mapped[str | None] = mapped_column(Text, comment="Phương án AI soạn")
    decision_note: Mapped[str | None] = mapped_column(Text)
    refund_amount_vnd: Mapped[int] = money()
    decided_at: Mapped[datetime | None]
    decided_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    closed_at: Mapped[datetime | None]


class Notification(UUIDPk, Timestamps, Base):
    """Tin báo khách (g5) và các tin tự động khác; `dedupe_key` chống gửi trùng một mốc."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_status_created", "status", "created_at"),)

    customer_id: Mapped[uuid.UUID | None] = fk("customers")
    order_id: Mapped[uuid.UUID | None] = fk("orders", ondelete="CASCADE")
    event: Mapped[NotificationEvent] = mapped_column(enum_col(NotificationEvent))
    channel: Mapped[Channel] = mapped_column(enum_col(Channel))
    recipient: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[NotificationStatus] = mapped_column(enum_col(NotificationStatus), default=NotificationStatus.QUEUED)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    scheduled_at: Mapped[datetime | None]
    sent_at: Mapped[datetime | None]
    external_id: Mapped[str | None] = mapped_column(String(120))
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = count()
    ai_generated: Mapped[bool] = flag()


class CustomerLoginCode(UUIDPk, CreatedAt, Base):
    """Mã đăng nhập một lần của khách trên website («Của tôi» → Đơn của tôi): 6 chữ số gửi qua `notify`, chỉ lưu
    bản băm (HMAC), hết hạn sau 10 phút, sai quá số lần thì bỏ. Không gắn khách: liên hệ lạ cũng có dòng (không gửi
    tin) để câu trả lời không lộ số/email nào đã mua."""

    __tablename__ = "customer_login_codes"
    __table_args__ = (Index("ix_customer_login_codes_contact", "contact", "created_at"),)

    contact_kind: Mapped[str] = mapped_column(String(10), comment="phone | email")
    contact: Mapped[str] = mapped_column(String(254), comment="SĐT chuẩn hoá 0xxxxxxxxx hoặc email chữ thường")
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime]
    attempts: Mapped[int] = count()
    consumed_at: Mapped[datetime | None] = mapped_column(comment="Đã dùng / bị thay bằng mã mới / sai quá số lần")


class MarketplaceListing(UUIDPk, Timestamps, Base):
    """Bán trên TikTok Shop, Shopee (g9): ánh xạ sản phẩm ↔ mã trên sàn."""

    __tablename__ = "marketplace_listings"
    __table_args__ = (
        UniqueConstraint("marketplace", "external_id", name="uq_marketplace_listings_external"),
        UniqueConstraint(
            "marketplace", "product_id", "variant_id", name="uq_marketplace_listings_product",
            postgresql_nulls_not_distinct=True,
        ),
    )  # fmt: skip

    marketplace: Mapped[Channel] = mapped_column(enum_col(Channel))
    product_id: Mapped[uuid.UUID] = fk("products", ondelete="CASCADE", nullable=False)
    variant_id: Mapped[uuid.UUID | None] = fk("product_variants")
    external_id: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[ListingStatus] = mapped_column(enum_col(ListingStatus), default=ListingStatus.PENDING)
    price_vnd: Mapped[int | None] = money_opt()
    synced_stock: Mapped[int | None] = mapped_column(Integer)
    last_synced_at: Mapped[datetime | None]
    error: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = json_obj()
