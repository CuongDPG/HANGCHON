"""Schema đọc cơ bản của orders (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


# ======================================================================================================================
# Schema nghiệp vụ (viết tay) — store (khách), desk (chị), hooks.
# ======================================================================================================================

CheckoutPayment = Literal["bank_transfer", "cod"]
StepStatus = Literal["done", "current", "todo"]


class CartLineIn(BaseModel):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    drop_id: uuid.UUID | None = Field(default=None, description="Có = đặt trong đợt; không = hàng giữ sẵn")
    quantity: int = Field(ge=1, le=99)


class AddressFields(BaseModel):
    address_line: str | None = Field(default=None, max_length=300)
    ward: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    province: str | None = Field(default=None, max_length=120)

    @field_validator("address_line", "ward", "district", "province", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return v.strip() or None if isinstance(v, str) else v


class QuoteIn(AddressFields):
    items: list[CartLineIn] = Field(min_length=1, max_length=30)
    payment_method: CheckoutPayment = "bank_transfer"


class CheckoutIn(AddressFields):
    items: list[CartLineIn] = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=8, max_length=20)
    payment_method: CheckoutPayment = "bank_transfer"
    note: str | None = Field(default=None, max_length=500)
    client_ref: str | None = Field(default=None, max_length=64, description="Chống bấm đặt hai lần")
    marketing_opt_in: bool = False
    src: str | None = Field(default=None, max_length=40, description="Mã bài dẫn khách tới (?src= trong link bài đăng)")
    referral_code: str | None = Field(default=None, max_length=30, description="Mã giới thiệu (?ref=)")


class DropBrief(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    status: str
    closes_at: datetime | None
    expected_arrival_date: date | None


class QuoteLineOut(BaseModel):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    drop_id: uuid.UUID | None
    drop_item_id: uuid.UUID | None
    fulfillment_source: FulfillmentSource
    name: str
    variant_name: str | None
    slug: str | None
    image_url: str | None
    unit_price_vnd: int
    quantity: int
    line_total_vnd: int
    available: int | None = Field(description="Số suất/món còn đặt được (null = không giới hạn)")
    ok: bool
    problem: str | None = None


class ShippingOption(BaseModel):
    carrier: Carrier
    driver: str
    service: str
    service_name: str
    fee_vnd: int
    eta_days_min: int
    eta_days_max: int


class QuoteOut(BaseModel):
    lines: list[QuoteLineOut]
    subtotal_vnd: int
    shipping_fee_vnd: int
    shipping_estimated: bool = Field(description="True = chưa đủ địa chỉ, phí giao là ước tính")
    total_vnd: int
    deposit_required_vnd: int
    drops: list[DropBrief]
    delivery_hint: str | None
    problems: list[str]
    ok: bool


class PaymentInfo(BaseModel):
    method: PaymentMethod
    transfer_content: str | None
    bank_code: str | None
    account_no: str | None
    account_name: str | None
    amount_due_vnd: int
    qr_url: str | None
    qr_payload: str | None
    due_at: datetime | None


class TimelineStep(BaseModel):
    key: str
    title: str
    status: StepStatus
    at: datetime | None = None
    meta: str | None = None


class PublicItem(BaseModel):
    name: str
    variant_name: str | None
    quantity: int
    unit_price_vnd: int
    line_total_vnd: int
    image_url: str | None
    slug: str | None


class PublicEvent(BaseModel):
    title: str
    detail: str | None
    occurred_at: datetime


class PublicShipment(BaseModel):
    carrier: Carrier
    tracking_code: str | None
    status: ShippingStatus


class PublicReturn(BaseModel):
    code: str
    kind: ReturnKind
    status: ReturnStatus
    created_at: datetime


class PublicReviewLink(BaseModel):
    """e8: món đã nhận đang chờ khách đánh giá (đọc bảng `reviews` của catalog)."""

    name: str
    token: str
    status: str


class PublicOrderOut(BaseModel):
    code: str
    token: str
    status: OrderStatus
    status_label: str
    headline: str
    channel: Channel
    payment_method: PaymentMethod
    payment_state: PaymentState
    items: list[PublicItem]
    subtotal_vnd: int
    shipping_fee_vnd: int
    discount_vnd: int
    total_vnd: int
    paid_vnd: int
    refunded_vnd: int
    deposit_required_vnd: int
    cod_amount_vnd: int
    recipient_name: str
    recipient_phone: str
    address_line: str | None
    ward: str | None
    district: str | None
    province: str | None
    customer_note: str | None
    placed_at: datetime
    payment: PaymentInfo | None
    drop: DropBrief | None
    timeline: list[TimelineStep]
    events: list[PublicEvent]
    shipment: PublicShipment | None
    returns: list[PublicReturn]
    can_change_address: bool
    can_request_return: bool
    notify_hint: str | None
    reviews: list[PublicReviewLink] = Field(default_factory=list)


class LookupIn(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    code: str = Field(min_length=3, max_length=20)


class LookupOut(BaseModel):
    code: str
    token: str


class TokenIn(BaseModel):
    t: str = Field(min_length=8, max_length=64)


class QuestionIn(TokenIn):
    message: str = Field(min_length=2, max_length=1000)


class AddressChangeIn(TokenIn, AddressFields):
    recipient_name: str | None = Field(default=None, max_length=120)


class PublicReturnIn(TokenIn):
    kind: ReturnKind = ReturnKind.RETURN
    reason: ReturnReason
    description: str | None = Field(default=None, max_length=1500)
    order_item_index: int | None = Field(default=None, ge=0, description="Dòng hàng thứ mấy (0 = dòng đầu)")
    quantity: int = Field(default=1, ge=1, le=99)


class ProvinceSuggestion(BaseModel):
    name: str
    code: str | None = None


# ---- desk ------------------------------------------------------------------------------------------------------------

StatusGroup = Literal["nhap", "cho_thanh_toan", "cho_hang", "cho_giao", "dang_giao", "xong", "huy", "tat_ca"]


class OrderListItem(BaseModel):
    id: uuid.UUID
    code: str
    channel: Channel
    status: OrderStatus
    status_label: str
    payment_method: PaymentMethod
    payment_state: PaymentState
    recipient_name: str
    recipient_phone: str
    province: str | None
    total_vnd: int
    paid_vnd: int
    items_summary: str
    item_count: int
    placed_at: datetime
    payment_due_at: datetime | None
    drop_id: uuid.UUID | None
    drop_code: str | None
    ai_generated: bool
    tracking_code: str | None
    missing_info: list[str]


class OrderCounts(BaseModel):
    nhap: int
    cho_thanh_toan: int
    cho_hang: int
    cho_giao: int
    dang_giao: int
    xong: int
    huy: int
    tat_ca: int
    new_today: int
    payments_to_review: int
    returns_open: int


class ShipmentWithEvents(ShipmentOut):
    events: list[ShipmentEventOut]


class OrderDetailOut(OrderOut):
    status_label: str
    items: list[OrderItemOut]
    events: list[OrderEventOut]
    payments: list[PaymentOut]
    shipments: list[ShipmentWithEvents]
    notifications: list[NotificationOut]
    returns: list[ReturnOut]
    drop: DropBrief | None
    customer: CustomerOut | None
    public_url: str
    missing_info: list[str]
    amount_due_vnd: int
    can_cancel: bool
    can_ship: bool
    can_edit_address: bool


class ManualLineIn(CartLineIn):
    unit_price_vnd: int | None = Field(default=None, ge=0, description="Bỏ trống = giá trong đợt / giá bán")


class ManualOrderIn(AddressFields):
    items: list[ManualLineIn] = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=8, max_length=20)
    channel: Channel = Channel.MANUAL
    payment_method: PaymentMethod = PaymentMethod.BANK_TRANSFER
    shipping_fee_vnd: int | None = Field(default=None, ge=0, description="Bỏ trống = tính qua hãng giao")
    discount_vnd: int = Field(default=0, ge=0)
    customer_note: str | None = Field(default=None, max_length=500)
    internal_note: str | None = Field(default=None, max_length=1000)
    already_paid: bool = Field(default=False, description="Chị đã nhận đủ tiền (tiền mặt / chuyển khoản trước)")


class OrderPatchIn(AddressFields):
    recipient_name: str | None = Field(default=None, max_length=120)
    recipient_phone: str | None = Field(default=None, max_length=20)
    customer_note: str | None = Field(default=None, max_length=500)
    internal_note: str | None = Field(default=None, max_length=1000)


class DraftConfirmIn(OrderPatchIn):
    payment_method: PaymentMethod | None = None
    items: list[ManualLineIn] | None = Field(default=None, max_length=30)


class CancelIn(BaseModel):
    reason: str = Field(min_length=2, max_length=500)
    notify_customer: bool = True


class ManualPaymentIn(BaseModel):
    amount_vnd: int = Field(gt=0)
    method: Literal["bank_transfer", "cash"] = "cash"
    note: str | None = Field(default=None, max_length=500)


class PaymentMatchIn(BaseModel):
    order_code: str = Field(min_length=3, max_length=20)


class PaymentRowOut(PaymentOut):
    order_code: str | None


class CreateShipmentsIn(BaseModel):
    order_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    driver: str | None = Field(default=None, description="Bỏ trống = AI chọn theo phí + thời gian")
    service: str | None = None


class ShipmentResult(BaseModel):
    order_id: uuid.UUID
    code: str
    status: Literal["applied", "pending", "blocked", "failed", "skipped"]
    shipment_id: uuid.UUID | None = None
    tracking_code: str | None = None
    carrier: Carrier | None = None
    fee_vnd: int | None = None
    message: str | None = None


class ShipmentsResultOut(BaseModel):
    results: list[ShipmentResult]


class LabelOut(BaseModel):
    order_id: uuid.UUID
    code: str
    recipient_name: str
    recipient_phone: str
    address: str
    carrier: Carrier
    service: str | None
    tracking_code: str | None
    cod_amount_vnd: int
    weight_grams: int | None
    items_summary: str
    note: str | None
    label_url: str | None


class DeskReturnIn(BaseModel):
    kind: ReturnKind = ReturnKind.RETURN
    reason: ReturnReason
    description: str | None = Field(default=None, max_length=1500)
    order_item_id: uuid.UUID | None = None
    quantity: int = Field(default=1, ge=1, le=99)


class ReturnRowOut(ReturnOut):
    order_code: str
    recipient_name: str


class TemplatesOut(BaseModel):
    templates: dict[str, str]
    defaults: dict[str, str]
    labels: dict[str, str]
    placeholders: dict[str, str]


class TemplatesIn(BaseModel):
    templates: dict[str, str]


class DropItemStat(BaseModel):
    drop_item_id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    name: str
    price_vnd: int
    slots_total: int | None
    quantity_confirmed: int
    quantity_pending: int
    min_total_to_order: int | None


class InboundBrief(BaseModel):
    id: uuid.UUID
    code: str | None
    status: str
    status_label: str
    eta: date | None
    last_note: str | None
    last_at: datetime | None


class DropOverview(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    status: str
    closes_at: datetime | None
    expected_arrival_date: date | None
    orders_total: int
    orders_confirmed: int
    orders_pending: int
    revenue_vnd: int
    slots_total: int | None
    slots_taken: int
    items: list[DropItemStat]
    inbound: list[InboundBrief]


class InventoryRow(BaseModel):
    inventory_item_id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    name: str
    on_hand: int
    reserved: int
    pending_orders_qty: int
    available: int
    low_stock_threshold: int | None
    low: bool


class ListingRow(MarketplaceListingOut):
    product_name: str


class MarketplaceSyncOut(BaseModel):
    synced: int = 0
    created_orders: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)


class SimulateMarketplaceOrderIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=20)


class WebhookAck(BaseModel):
    success: bool = True
    received: int = 0


class SimulateTransferIn(BaseModel):
    amount_vnd: int = Field(gt=0)
    content: str = Field(default="", max_length=200)


class SellableDrop(BaseModel):
    drop_id: uuid.UUID
    code: str
    status: str
    price_vnd: int
    available: int | None


class SellableProduct(BaseModel):
    product_id: uuid.UUID
    name: str
    slug: str
    price_vnd: int
    sale_mode: str
    image_url: str | None
    stock_available: int | None
    drops: list[SellableDrop]
