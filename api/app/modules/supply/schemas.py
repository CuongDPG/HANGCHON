"""Schema đọc cơ bản của supply (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

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
