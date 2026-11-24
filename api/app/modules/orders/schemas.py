"""Schema đọc cơ bản của orders (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.enums import Actor, Carrier, Channel, ShippingStatus
from app.modules.orders.models import (
    FulfillmentSource,
    ListingStatus,
    MatchMethod,
    NotificationEvent,
    NotificationStatus,
    OrderStatus,
    PaymentDirection,
    PaymentMethod,
    PaymentState,
    PaymentStatus,
    ReturnKind,
    ReturnReason,
    ReturnStatus,
)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CustomerOut(ORM):
    """Khách (h4 sổ khách đọc từ đây + crm). Không cần tài khoản: nhận diện bằng SĐT và định danh theo kênh."""

    id: uuid.UUID
    name: str | None
    phone: str | None
    email: str | None
    default_address: dict[str, Any]
    first_channel: Channel | None
    first_order_at: datetime | None
    last_order_at: datetime | None
    order_count: int
    total_spent_vnd: int
    interests: list[Any]
    profile_summary: str | None
    is_regular: bool
    marketing_opt_in: bool
    is_blocked: bool
    merged_into_id: uuid.UUID | None
    referred_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class CustomerIdentityOut(ORM):
    """Định danh của khách trên từng kênh (PSID Facebook, IG id, Zalo id...) để hộp thư gộp nhận ra cùng một người."""

    id: uuid.UUID
    customer_id: uuid.UUID
    channel: Channel
    external_id: str
    display_name: str | None
    profile_url: str | None
    created_at: datetime


class OrderOut(ORM):
    """Đơn hàng từ mọi kênh (g1). Tra cứu công khai bằng SĐT + mã đơn (e5)."""

    id: uuid.UUID
    code: str
    customer_id: uuid.UUID | None
    channel: Channel
    external_id: str | None
    thread_id: uuid.UUID | None
    drop_id: uuid.UUID | None
    status: OrderStatus
    payment_method: PaymentMethod
    payment_state: PaymentState
    transfer_content: str | None
    recipient_name: str
    recipient_phone: str
    address_line: str | None
    ward: str | None
    district: str | None
    province: str | None
    address_codes: dict[str, Any]
    subtotal_vnd: int
    shipping_fee_vnd: int
    discount_vnd: int
    total_vnd: int
    paid_vnd: int
    refunded_vnd: int
    deposit_required_vnd: int
    cod_amount_vnd: int
    referral_code: str | None
    placed_at: datetime
    confirmed_at: datetime | None
    paid_at: datetime | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    payment_due_at: datetime | None
    customer_note: str | None
    internal_note: str | None
    ai_generated: bool
    approval_item_id: uuid.UUID | None
    raw: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class OrderItemOut(ORM):
    id: uuid.UUID
    order_id: uuid.UUID
    position: int
    product_id: uuid.UUID | None
    variant_id: uuid.UUID | None
    drop_item_id: uuid.UUID | None
    fulfillment_source: FulfillmentSource
    name: str
    variant_name: str | None
    sku: str | None
    quantity: int
    unit_price_vnd: int
    discount_vnd: int
    line_total_vnd: int
    unit_cost_vnd: int | None
    created_at: datetime
    updated_at: datetime


class OrderEventOut(ORM):
    """Hành trình đơn (e5): mốc hiển thị cho khách và nhật ký nội bộ."""

    id: uuid.UUID
    order_id: uuid.UUID
    kind: str
    status: OrderStatus | None
    title: str
    detail: str | None
    visible_to_customer: bool
    actor: Actor
    occurred_at: datetime
    data: dict[str, Any]


class PaymentOut(ORM):
    """Khoản tiền vào/ra. Tiền chuyển khoản tới trước, khớp đơn sau (g2); hoàn tiền là direction=out."""

    id: uuid.UUID
    order_id: uuid.UUID | None
    direction: PaymentDirection
    method: PaymentMethod
    provider: str
    external_id: str | None
    status: PaymentStatus
    amount_vnd: int
    content: str | None
    payer_name: str | None
    payer_account: str | None
    received_at: datetime
    matched_at: datetime | None
    match_method: MatchMethod | None
    match_confidence: Decimal | None
    refund_of_id: uuid.UUID | None
    return_id: uuid.UUID | None
    note: str | None
    raw: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ShipmentOut(ORM):
    """Vận đơn (g4): chọn hãng theo phí + thời gian, in nhãn, theo dõi."""

    id: uuid.UUID
    order_id: uuid.UUID | None
    tester_invite_id: uuid.UUID | None
    return_id: uuid.UUID | None
    carrier: Carrier
    service: str | None
    tracking_code: str | None
    status: ShippingStatus
    fee_vnd: int
    cod_amount_vnd: int
    weight_grams: int | None
    label_url: str | None
    label_storage_key: str | None
    quotes: list[Any]
    selection_reason: str | None
    expected_delivery_at: datetime | None
    picked_up_at: datetime | None
    delivered_at: datetime | None
    last_synced_at: datetime | None
    raw: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ShipmentEventOut(ORM):
    id: uuid.UUID
    shipment_id: uuid.UUID
    status: ShippingStatus
    description: str
    location: str | None
    occurred_at: datetime
    raw: dict[str, Any]
    created_at: datetime


class ReturnOut(ORM):
    """Đổi trả, hoàn tiền (g7): AI kiểm điều kiện và soạn phương án; chị quyết (luôn khoá ở mức hỏi)."""

    id: uuid.UUID
    code: str
    order_id: uuid.UUID
    order_item_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    thread_id: uuid.UUID | None
    kind: ReturnKind
    reason: ReturnReason
    description: str | None
    photos: list[Any]
    quantity: int
    status: ReturnStatus
    eligibility: dict[str, Any]
    proposal: str | None
    decision_note: str | None
    refund_amount_vnd: int
    decided_at: datetime | None
    decided_by_id: uuid.UUID | None
    approval_item_id: uuid.UUID | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NotificationOut(ORM):
    """Tin báo khách (g5) và các tin tự động khác; `dedupe_key` chống gửi trùng một mốc."""

    id: uuid.UUID
    customer_id: uuid.UUID | None
    order_id: uuid.UUID | None
    event: NotificationEvent
    channel: Channel
    recipient: str
    subject: str | None
    body: str
    status: NotificationStatus
    dedupe_key: str | None
    scheduled_at: datetime | None
    sent_at: datetime | None
    external_id: str | None
    error: str | None
    attempts: int
    ai_generated: bool
    created_at: datetime
    updated_at: datetime


class MarketplaceListingOut(ORM):
    """Bán trên TikTok Shop, Shopee (g9): ánh xạ sản phẩm ↔ mã trên sàn."""

    id: uuid.UUID
    marketplace: Channel
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    external_id: str | None
    status: ListingStatus
    price_vnd: int | None
    synced_stock: int | None
    last_synced_at: datetime | None
    error: str | None
    data: dict[str, Any]
    created_at: datetime
    updated_at: datetime
