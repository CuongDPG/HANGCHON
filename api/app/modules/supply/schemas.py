"""Schema đọc cơ bản của supply (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import Language, SourcePlatform
from app.modules.supply.models import (
    DocumentKind,
    InboundStatus,
    MessageDirection,
    POKind,
    POStatus,
    ProposalStatus,
    SupplierChannel,
    SupplierKind,
    SupplierMessageStatus,
)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SupplierOut(ORM):
    """Sổ nhà cung cấp (d1): điểm uy tín, lịch sử đặt, tỉ lệ lỗi. Liên hệ lưu dạng tuỳ chọn, không ghi dữ liệu thật vào repo."""

    id: uuid.UUID
    name: str
    name_original: str | None
    kind: SupplierKind
    platform: SourcePlatform | None
    shop_url: str | None
    external_shop_id: str | None
    country: str | None
    language: Language
    contact: dict[str, Any]
    trust_score: int | None
    order_count: int
    defect_rate: Decimal | None
    on_time_rate: Decimal | None
    avg_lead_days: Decimal | None
    agent_fee_pct: Decimal | None
    last_order_at: datetime | None
    tags: list[Any]
    notes: str | None
    is_blocked: bool
    created_at: datetime
    updated_at: datetime


class CostSheetOut(ORM):
    """Giá vốn về tay (d2): giá gốc × tỷ giá + phí mua hộ + cước + thuế + hao hụt. Tự tính lại khi tỷ giá/cước đổi."""

    id: uuid.UUID
    candidate_id: uuid.UUID | None
    product_id: uuid.UUID | None
    supplier_id: uuid.UUID | None
    is_current: bool
    version: int
    auto_update: bool
    quantity_basis: int
    unit_price_amount: Decimal
    currency: str
    fx_rate: Decimal
    fx_rate_at: datetime | None
    unit_price_vnd: int
    domestic_shipping_vnd: int
    agent_fee_pct: Decimal | None
    agent_fee_vnd: int
    weight_grams: int | None
    intl_shipping_vnd_per_kg: int | None
    intl_shipping_vnd: int
    import_tax_pct: Decimal | None
    vat_pct: Decimal | None
    tax_vnd: int
    packaging_vnd: int
    other_fees_vnd: int
    loss_pct: Decimal | None
    loss_vnd: int
    landed_cost_vnd: int
    moq: int | None
    breakdown: list[Any]
    assumptions: str | None
    recalculated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PriceProposalOut(ORM):
    """Đề xuất giá bán (d3) theo giá vốn, giá thị trường và biên lợi nhuận chị đặt. Chị duyệt."""

    id: uuid.UUID
    candidate_id: uuid.UUID | None
    product_id: uuid.UUID | None
    cost_sheet_id: uuid.UUID | None
    status: ProposalStatus
    landed_cost_vnd: int
    market_low_vnd: int | None
    market_median_vnd: int | None
    market_high_vnd: int | None
    target_margin_pct: Decimal | None
    proposed_price_vnd: int
    proposed_drop_price_vnd: int | None
    margin_pct: Decimal | None
    rationale: str | None
    approved_price_vnd: int | None
    decided_at: datetime | None
    approval_item_id: uuid.UUID | None
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PurchaseOrderOut(ORM):
    """Đơn đặt mẫu / đặt lô (d5, g3). Đặt hàng và trả tiền NCC luôn chờ chị duyệt."""

    id: uuid.UUID
    code: str
    kind: POKind
    status: POStatus
    supplier_id: uuid.UUID | None
    agent_supplier_id: uuid.UUID | None
    drop_id: uuid.UUID | None
    candidate_id: uuid.UUID | None
    currency: str
    fx_rate: Decimal | None
    subtotal_amount: Decimal
    shipping_amount: Decimal
    fees_vnd: int
    total_vnd: int
    deposit_vnd: int
    paid_vnd: int
    message_draft: str | None
    message_language: Language | None
    approval_item_id: uuid.UUID | None
    approved_at: datetime | None
    sent_at: datetime | None
    expected_at: date | None
    received_at: datetime | None
    ai_generated: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class PurchaseOrderLineOut(ORM):
    id: uuid.UUID
    purchase_order_id: uuid.UUID
    position: int
    candidate_id: uuid.UUID | None
    product_id: uuid.UUID | None
    variant_id: uuid.UUID | None
    description: str
    source_url: str | None
    variant_spec: dict[str, Any]
    quantity: int
    unit_price_amount: Decimal
    line_total_amount: Decimal
    unit_cost_vnd: int | None
    received_qty: int
    defect_qty: int
    created_at: datetime
    updated_at: datetime


class SupplierMessageOut(ORM):
    """Nhắn hỏi nhà cung cấp (d6): AI soạn tiếng Trung/Nhật, dịch câu trả lời, rút thông tin (giá, MOQ, thời gian)."""

    id: uuid.UUID
    supplier_id: uuid.UUID
    purchase_order_id: uuid.UUID | None
    candidate_id: uuid.UUID | None
    direction: MessageDirection
    channel: SupplierChannel
    language: Language
    body_original: str
    body_vi: str | None
    status: SupplierMessageStatus
    extracted: dict[str, Any]
    attachments: list[Any]
    sent_at: datetime | None
    approval_item_id: uuid.UUID | None
    ai_generated: bool
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class InboundShipmentOut(ORM):
    """Lô hàng về (d7) theo các mốc: đã đặt → kho bên bán → thông quan → về nhà."""

    id: uuid.UUID
    purchase_order_id: uuid.UUID | None
    code: str | None
    carrier: str | None
    tracking_code: str | None
    status: InboundStatus
    milestones: list[Any]
    eta: date | None
    package_count: int | None
    weight_kg: Decimal | None
    shipping_cost_vnd: int | None
    customs_cost_vnd: int | None
    received_at: datetime | None
    problem_note: str | None
    created_at: datetime
    updated_at: datetime


class ProvenanceDocumentOut(ORM):
    """Chứng từ nguồn gốc (d4): hoá đơn, tờ khai, ảnh nhãn gốc theo từng lô — phục vụ hộ kinh doanh."""

    id: uuid.UUID
    kind: DocumentKind
    purchase_order_id: uuid.UUID | None
    inbound_shipment_id: uuid.UUID | None
    product_id: uuid.UUID | None
    supplier_id: uuid.UUID | None
    storage_key: str
    filename: str
    content_type: str
    size_bytes: int
    doc_number: str | None
    doc_date: date | None
    amount: Decimal | None
    currency: str | None
    extracted: dict[str, Any]
    notes: str | None
    uploaded_by_id: uuid.UUID | None
    created_at: datetime


# ---- schema tạo/sửa và schema cho màn hình (d1–d7) ----------------------------------------------------------------


class SupplierIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    name_original: str | None = Field(default=None, max_length=200)
    kind: SupplierKind = SupplierKind.SHOP
    platform: SourcePlatform | None = None
    shop_url: str | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)
    language: Language = Language.ZH
    contact: dict[str, Any] = Field(default_factory=dict)
    agent_fee_pct: Decimal | None = Field(default=None, ge=0, le=100)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    name_original: str | None = None
    kind: SupplierKind | None = None
    platform: SourcePlatform | None = None
    shop_url: str | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)
    language: Language | None = None
    contact: dict[str, Any] | None = None
    agent_fee_pct: Decimal | None = Field(default=None, ge=0, le=100)
    tags: list[str] | None = None
    notes: str | None = None
    is_blocked: bool | None = None


class SupplierView(SupplierOut):
    trust_label: str
    trust_basis: str
    open_orders: int


class CostParams(BaseModel):
    """Tham số mặc định tính giá vốn về tay (d2). Lưu ở `app_settings["supply.cost_params"]`."""

    fx_rates: dict[str, Decimal] = Field(description="VND cho 1 đơn vị ngoại tệ: CNY, JPY, USD")
    intl_vnd_per_kg: dict[str, int] = Field(description="Cước quốc tế theo nước gửi: CN, JP")
    agent_fee_pct: Decimal = Field(ge=0, le=100)
    domestic_shipping_vnd: int = Field(ge=0, description="Cước nội địa bên bán, chia cho mỗi cái")
    import_tax_pct: Decimal = Field(ge=0, le=100)
    vat_pct: Decimal = Field(ge=0, le=100)
    loss_pct: Decimal = Field(ge=0, le=100, description="Hao hụt, đổi trả dự phòng")
    packaging_vnd: int = Field(ge=0)
    target_margin_pct: Decimal = Field(ge=0, lt=100, description="Biên lợi nhuận mục tiêu khi đề xuất giá bán")


class CostParamsOut(CostParams):
    recalculated: int = 0


class CostSheetIn(BaseModel):
    candidate_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    unit_price_amount: Decimal = Field(gt=0)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    weight_grams: int | None = Field(default=None, ge=0)
    domestic_shipping_vnd: int | None = Field(default=None, ge=0)
    packaging_vnd: int | None = Field(default=None, ge=0)
    other_fees_vnd: int = Field(default=0, ge=0)
    moq: int | None = Field(default=None, ge=1)
    auto_update: bool = True
    country: str | None = Field(default=None, min_length=2, max_length=2, description="Nước gửi; trống = theo tiền tệ")
    # chỉ dùng khi auto_update = false (tham số riêng cho món này)
    fx_rate: Decimal | None = Field(default=None, gt=0)
    intl_shipping_vnd_per_kg: int | None = Field(default=None, ge=0)
    agent_fee_pct: Decimal | None = Field(default=None, ge=0, le=100)
    import_tax_pct: Decimal | None = Field(default=None, ge=0, le=100)
    vat_pct: Decimal | None = Field(default=None, ge=0, le=100)
    loss_pct: Decimal | None = Field(default=None, ge=0, le=100)
    assumptions: str | None = None


class CostLine(BaseModel):
    key: str
    label: str
    amount_vnd: int
    formula: str


class CostPreview(BaseModel):
    landed_cost_vnd: int
    breakdown: list[CostLine]


class PriceProposalIn(BaseModel):
    candidate_id: uuid.UUID
    target_margin_pct: Decimal | None = Field(default=None, ge=0, lt=100)


class PriceProposalView(PriceProposalOut):
    market_samples: int


class POLineIn(BaseModel):
    candidate_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    source_url: str | None = None
    variant_spec: dict[str, Any] = Field(default_factory=dict)
    quantity: int = Field(ge=1)
    unit_price_amount: Decimal = Field(ge=0)


class PurchaseOrderIn(BaseModel):
    kind: POKind = POKind.SAMPLE
    supplier_id: uuid.UUID | None = None
    agent_supplier_id: uuid.UUID | None = None
    candidate_id: uuid.UUID | None = None
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    shipping_amount: Decimal = Field(default=Decimal(0), ge=0)
    fees_vnd: int = Field(default=0, ge=0)
    expected_at: date | None = None
    notes: str | None = None
    lines: list[POLineIn] = Field(min_length=1)


class SampleOrderIn(BaseModel):
    candidate_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=50)
    supplier_id: uuid.UUID | None = None


class PurchaseOrderUpdate(BaseModel):
    message_draft: str | None = None
    notes: str | None = None
    expected_at: date | None = None
    supplier_id: uuid.UUID | None = None
    agent_supplier_id: uuid.UUID | None = None
    shipping_amount: Decimal | None = Field(default=None, ge=0)
    fees_vnd: int | None = Field(default=None, ge=0)


class POStatusIn(BaseModel):
    to: Literal["sent", "confirmed", "cancelled"]
    note: str | None = None


class PaymentIn(BaseModel):
    amount_vnd: int = Field(gt=0)
    kind: Literal["deposit", "payment", "shipping", "fee"] = "payment"
    paid_on: date | None = None
    note: str | None = Field(default=None, max_length=500)


class ReceiveLine(BaseModel):
    line_id: uuid.UUID
    received_qty: int = Field(ge=0)
    defect_qty: int = Field(default=0, ge=0)


class ReceiveIn(BaseModel):
    lines: list[ReceiveLine] = Field(min_length=1)


class InboundLite(BaseModel):
    id: uuid.UUID
    status: InboundStatus
    tracking_code: str | None
    eta: date | None


class PurchaseOrderView(PurchaseOrderOut):
    lines: list[PurchaseOrderLineOut]
    supplier_name: str | None
    agent_name: str | None
    candidate_title: str | None
    inbound: list[InboundLite]
    document_kinds: list[str]
    missing_documents: list[str]


class InboundIn(BaseModel):
    purchase_order_id: uuid.UUID | None = None
    code: str | None = Field(default=None, max_length=60)
    carrier: str | None = Field(default=None, max_length=80)
    tracking_code: str | None = Field(default=None, max_length=120)
    eta: date | None = None
    package_count: int | None = Field(default=None, ge=0)
    weight_kg: Decimal | None = Field(default=None, ge=0)


class InboundUpdate(InboundIn):
    shipping_cost_vnd: int | None = Field(default=None, ge=0)
    customs_cost_vnd: int | None = Field(default=None, ge=0)
    problem_note: str | None = None


class MilestoneIn(BaseModel):
    status: InboundStatus
    note: str | None = Field(default=None, max_length=500)
    at: datetime | None = None


class InboundView(InboundShipmentOut):
    po_code: str | None
    supplier_name: str | None
    document_kinds: list[str]
    missing_documents: list[str]


class DocumentView(ProvenanceDocumentOut):
    url: str | None


class ExtractedPatch(BaseModel):
    """Chị sửa phần AI đọc từ chứng từ (d4)."""

    product_name: str | None = Field(default=None, max_length=300)
    product_name_vi: str | None = Field(default=None, max_length=300)
    manufacturer: str | None = Field(default=None, max_length=300)
    origin_country: str | None = Field(default=None, max_length=60)
    lot_number: str | None = Field(default=None, max_length=100)
    production_date: str | None = Field(default=None, max_length=30)
    expiry_date: str | None = Field(default=None, max_length=30)
    certifications: list[str] | None = Field(default=None, max_length=20)
    summary: str | None = Field(default=None, max_length=500)


class DocumentPatch(BaseModel):
    kind: DocumentKind | None = None
    doc_number: str | None = Field(default=None, max_length=100)
    doc_date: date | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: str | None = Field(default=None, max_length=2000)
    extracted: ExtractedPatch | None = None


class DocumentWarning(BaseModel):
    purchase_order_id: uuid.UUID
    po_code: str
    kind: POKind
    status: POStatus
    supplier_name: str | None
    missing: list[str]
    missing_labels: list[str]


class InquiryIn(BaseModel):
    candidate_id: uuid.UUID | None = None
    purchase_order_id: uuid.UUID | None = None
    topics: list[Literal["price", "moq", "lead_time", "shipping", "sample", "custom"]] = Field(
        default_factory=lambda: ["price", "moq", "lead_time"]
    )
    quantity: int | None = Field(default=None, ge=1)
    extra: str | None = Field(default=None, max_length=1000, description="Điều chị muốn hỏi thêm, viết tiếng Việt")


class ReplyIn(BaseModel):
    body_original: str = Field(min_length=1, max_length=8000)
    candidate_id: uuid.UUID | None = None
    purchase_order_id: uuid.UUID | None = None


class MessageSentIn(BaseModel):
    channel: SupplierChannel = SupplierChannel.MANUAL


class CostSheetView(CostSheetOut):
    candidate_title: str | None
    candidate_stage: str | None
