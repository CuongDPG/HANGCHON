"""supply — nguồn cung và giá vốn (d1–d7): nhà cung cấp, bảng giá vốn về tay, đề xuất giá bán, đơn đặt mẫu/lô,
tin nhắn nhà cung cấp, lô hàng về, chứng từ nguồn gốc."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, Index, Integer, Numeric, String, Text
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
from app.core.enums import Language, SourcePlatform, StrEnum


class SupplierKind(StrEnum):
    FACTORY = "factory"  # xưởng
    SHOP = "shop"  # shop trên sàn
    TRADING = "trading"
    PURCHASING_AGENT = "purchasing_agent"  # đơn vị mua hộ
    FORWARDER = "forwarder"  # vận chuyển / gom hàng
    LOCAL_WHOLESALER = "local_wholesaler"  # sỉ trong nước


class ProposalStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class POKind(StrEnum):
    SAMPLE = "sample"  # đặt mẫu
    BATCH = "batch"  # đặt lô theo đợt (g3)
    RESTOCK = "restock"  # bổ sung hàng giữ sẵn (g8)


class POStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"  # luôn chờ chị (locked_ask)
    APPROVED = "approved"
    SENT = "sent"  # đã gửi bên mua hộ / NCC
    CONFIRMED = "confirmed"
    PAID = "paid"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class MessageDirection(StrEnum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class SupplierMessageStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SENT = "sent"
    RECEIVED = "received"
    FAILED = "failed"


class SupplierChannel(StrEnum):
    MANUAL = "manual"  # chị tự gửi (copy)
    PLATFORM_CHAT = "platform_chat"  # chat trên 1688/Taobao
    WECHAT = "wechat"
    LINE = "line"
    EMAIL = "email"
    ZALO = "zalo"


class InboundStatus(StrEnum):
    """Các mốc lô hàng về (d7)."""

    ORDERED = "ordered"  # đã đặt
    SELLER_SHIPPED = "seller_shipped"
    AT_AGENT_WAREHOUSE = "at_agent_warehouse"  # về kho bên bán / kho mua hộ
    INTERNATIONAL_TRANSIT = "international_transit"
    CUSTOMS = "customs"  # thông quan
    DOMESTIC_TRANSIT = "domestic_transit"
    DELIVERED = "delivered"  # về nhà
    PROBLEM = "problem"


class DocumentKind(StrEnum):
    INVOICE = "invoice"  # hoá đơn mua
    CUSTOMS_DECLARATION = "customs_declaration"  # tờ khai
    ORIGINAL_LABEL = "original_label"  # ảnh nhãn gốc
    PACKING_LIST = "packing_list"
    PAYMENT_RECEIPT = "payment_receipt"
    CERTIFICATE = "certificate"  # công bố, kiểm nghiệm
    CONTRACT = "contract"
    OTHER = "other"


class Supplier(UUIDPk, Timestamps, Base):
    """Sổ nhà cung cấp (d1): điểm uy tín, lịch sử đặt, tỉ lệ lỗi. Liên hệ lưu dạng tuỳ chọn, không ghi dữ liệu thật vào repo."""

    __tablename__ = "suppliers"
    __table_args__ = (Index("ix_suppliers_platform_shop", "platform", "external_shop_id"),)

    name: Mapped[str] = mapped_column(String(200))
    name_original: Mapped[str | None] = mapped_column(String(200))
    kind: Mapped[SupplierKind] = mapped_column(enum_col(SupplierKind), default=SupplierKind.SHOP)
    platform: Mapped[SourcePlatform | None] = mapped_column(enum_col(SourcePlatform))
    shop_url: Mapped[str | None] = mapped_column(Text)
    external_shop_id: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(2), comment="ISO: CN, JP, VN...")
    language: Mapped[Language] = mapped_column(enum_col(Language), default=Language.ZH)
    contact: Mapped[dict[str, Any]] = json_obj(comment="wechat / line / email / người liên hệ")
    trust_score: Mapped[int | None] = mapped_column(Integer, comment="0–100")
    order_count: Mapped[int] = count()
    defect_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    on_time_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    avg_lead_days: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    agent_fee_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), comment="Phí mua hộ mặc định")
    last_order_at: Mapped[datetime | None]
    tags: Mapped[list[Any]] = json_list()
    notes: Mapped[str | None] = mapped_column(Text)
    is_blocked: Mapped[bool] = flag()


class CostSheet(UUIDPk, Timestamps, Base):
    """Giá vốn về tay (d2): giá gốc × tỷ giá + phí mua hộ + cước + thuế + hao hụt. Tự tính lại khi tỷ giá/cước đổi."""

    __tablename__ = "cost_sheets"
    __table_args__ = (
        Index("ix_cost_sheets_candidate_current", "candidate_id", "is_current"),
        Index("ix_cost_sheets_product_current", "product_id", "is_current"),
    )

    candidate_id: Mapped[uuid.UUID | None] = fk("candidates", ondelete="CASCADE", index=False)
    product_id: Mapped[uuid.UUID | None] = fk("products", ondelete="CASCADE", index=False)
    supplier_id: Mapped[uuid.UUID | None] = fk("suppliers")
    is_current: Mapped[bool] = flag(True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    auto_update: Mapped[bool] = flag(True)
    quantity_basis: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", comment="Tính cho lô bao nhiêu cái"
    )
    unit_price_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4), comment="VND cho 1 đơn vị ngoại tệ")
    fx_rate_at: Mapped[datetime | None]
    unit_price_vnd: Mapped[int] = money()
    domestic_shipping_vnd: Mapped[int] = money(comment="Cước nội địa bên bán (chia cho mỗi cái)")
    agent_fee_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    agent_fee_vnd: Mapped[int] = money()
    weight_grams: Mapped[int | None] = mapped_column(Integer)
    intl_shipping_vnd_per_kg: Mapped[int | None] = money_opt()
    intl_shipping_vnd: Mapped[int] = money()
    import_tax_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    vat_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    tax_vnd: Mapped[int] = money()
    packaging_vnd: Mapped[int] = money()
    other_fees_vnd: Mapped[int] = money()
    loss_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), comment="Hao hụt / lỗi dự phòng")
    loss_vnd: Mapped[int] = money()
    landed_cost_vnd: Mapped[int] = money(comment="Giá vốn về tay cho MỘT cái")
    moq: Mapped[int | None] = mapped_column(Integer)
    breakdown: Mapped[list[Any]] = json_list(comment='[{"label","amount_vnd","formula"}] để hiển thị')
    assumptions: Mapped[str | None] = mapped_column(Text)
    recalculated_at: Mapped[datetime | None]


class PriceProposal(UUIDPk, Timestamps, Base):
    """Đề xuất giá bán (d3) theo giá vốn, giá thị trường và biên lợi nhuận chị đặt. Chị duyệt."""

    __tablename__ = "price_proposals"
    __table_args__ = (
        Index("ix_price_proposals_candidate", "candidate_id", "created_at"),
        Index("ix_price_proposals_product", "product_id", "created_at"),
    )

    candidate_id: Mapped[uuid.UUID | None] = fk("candidates", ondelete="CASCADE", index=False)
    product_id: Mapped[uuid.UUID | None] = fk("products", ondelete="CASCADE", index=False)
    cost_sheet_id: Mapped[uuid.UUID | None] = fk("cost_sheets")
    status: Mapped[ProposalStatus] = mapped_column(enum_col(ProposalStatus), default=ProposalStatus.DRAFT)
    landed_cost_vnd: Mapped[int] = money()
    market_low_vnd: Mapped[int | None] = money_opt()
    market_median_vnd: Mapped[int | None] = money_opt()
    market_high_vnd: Mapped[int | None] = money_opt()
    target_margin_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    proposed_price_vnd: Mapped[int] = money()
    proposed_drop_price_vnd: Mapped[int | None] = money_opt(comment="Giá mở bán theo đợt nếu khác")
    margin_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    rationale: Mapped[str | None] = mapped_column(Text)
    approved_price_vnd: Mapped[int | None] = money_opt()
    decided_at: Mapped[datetime | None]
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)


class PurchaseOrder(UUIDPk, Timestamps, Base):
    """Đơn đặt mẫu / đặt lô (d5, g3). Đặt hàng và trả tiền NCC luôn chờ chị duyệt."""

    __tablename__ = "purchase_orders"

    code: Mapped[str] = mapped_column(String(30), unique=True)
    kind: Mapped[POKind] = mapped_column(enum_col(POKind))
    status: Mapped[POStatus] = mapped_column(enum_col(POStatus), default=POStatus.DRAFT, index=True)
    supplier_id: Mapped[uuid.UUID | None] = fk("suppliers")
    agent_supplier_id: Mapped[uuid.UUID | None] = fk("suppliers", comment="Đơn vị mua hộ (nếu qua trung gian)")
    drop_id: Mapped[uuid.UUID | None] = fk("drops")
    candidate_id: Mapped[uuid.UUID | None] = fk("candidates", comment="Đặt mẫu cho ứng viên")
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0")
    shipping_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0")
    fees_vnd: Mapped[int] = money()
    total_vnd: Mapped[int] = money()
    deposit_vnd: Mapped[int] = money()
    paid_vnd: Mapped[int] = money()
    message_draft: Mapped[str | None] = mapped_column(Text, comment="Nội dung đơn gửi bên mua hộ / NCC")
    message_language: Mapped[Language | None] = mapped_column(enum_col(Language))
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    approved_at: Mapped[datetime | None]
    sent_at: Mapped[datetime | None]
    expected_at: Mapped[date | None] = mapped_column(Date)
    received_at: Mapped[datetime | None]
    ai_generated: Mapped[bool] = flag()
    notes: Mapped[str | None] = mapped_column(Text)

    lines: Mapped[list[PurchaseOrderLine]] = relationship(
        back_populates="purchase_order",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderLine.position",
    )


class PurchaseOrderLine(UUIDPk, Timestamps, Base):
    __tablename__ = "purchase_order_lines"

    purchase_order_id: Mapped[uuid.UUID] = fk("purchase_orders", ondelete="CASCADE", nullable=False)
    position: Mapped[int] = count()
    candidate_id: Mapped[uuid.UUID | None] = fk("candidates")
    product_id: Mapped[uuid.UUID | None] = fk("products")
    variant_id: Mapped[uuid.UUID | None] = fk("product_variants")
    description: Mapped[str] = mapped_column(Text, comment="Tên + phân loại theo ngôn ngữ NCC")
    source_url: Mapped[str | None] = mapped_column(Text)
    variant_spec: Mapped[dict[str, Any]] = json_obj()
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    line_total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    unit_cost_vnd: Mapped[int | None] = money_opt(comment="Giá vốn về tay dự kiến mỗi cái")
    received_qty: Mapped[int] = count()
    defect_qty: Mapped[int] = count()

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines", lazy="raise")


class SupplierMessage(UUIDPk, Timestamps, Base):
    """Nhắn hỏi nhà cung cấp (d6): AI soạn tiếng Trung/Nhật, dịch câu trả lời, rút thông tin (giá, MOQ, thời gian)."""

    __tablename__ = "supplier_messages"
    __table_args__ = (Index("ix_supplier_messages_supplier", "supplier_id", "created_at"),)

    supplier_id: Mapped[uuid.UUID] = fk("suppliers", ondelete="CASCADE", nullable=False, index=False)
    purchase_order_id: Mapped[uuid.UUID | None] = fk("purchase_orders")
    candidate_id: Mapped[uuid.UUID | None] = fk("candidates")
    direction: Mapped[MessageDirection] = mapped_column(enum_col(MessageDirection))
    channel: Mapped[SupplierChannel] = mapped_column(enum_col(SupplierChannel), default=SupplierChannel.MANUAL)
    language: Mapped[Language] = mapped_column(enum_col(Language), default=Language.ZH)
    body_original: Mapped[str] = mapped_column(Text)
    body_vi: Mapped[str | None] = mapped_column(Text)
    status: Mapped[SupplierMessageStatus] = mapped_column(enum_col(SupplierMessageStatus))
    extracted: Mapped[dict[str, Any]] = json_obj(comment="price, moq, lead_days, shipping... rút từ câu trả lời")
    attachments: Mapped[list[Any]] = json_list()
    sent_at: Mapped[datetime | None]
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    ai_generated: Mapped[bool] = flag()
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)


class InboundShipment(UUIDPk, Timestamps, Base):
    """Lô hàng về (d7) theo các mốc: đã đặt → kho bên bán → thông quan → về nhà."""

    __tablename__ = "inbound_shipments"

    purchase_order_id: Mapped[uuid.UUID | None] = fk("purchase_orders", ondelete="CASCADE")
    code: Mapped[str | None] = mapped_column(String(60), comment="Mã lô / mã kiện bên mua hộ")
    carrier: Mapped[str | None] = mapped_column(String(80))
    tracking_code: Mapped[str | None] = mapped_column(String(120), index=True)
    status: Mapped[InboundStatus] = mapped_column(enum_col(InboundStatus), default=InboundStatus.ORDERED, index=True)
    milestones: Mapped[list[Any]] = json_list(comment='[{"status","at","note","source"}]')
    eta: Mapped[date | None] = mapped_column(Date)
    package_count: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    shipping_cost_vnd: Mapped[int | None] = money_opt()
    customs_cost_vnd: Mapped[int | None] = money_opt()
    received_at: Mapped[datetime | None]
    problem_note: Mapped[str | None] = mapped_column(Text)


class ProvenanceDocument(UUIDPk, CreatedAt, Base):
    """Chứng từ nguồn gốc (d4): hoá đơn, tờ khai, ảnh nhãn gốc theo từng lô — phục vụ hộ kinh doanh."""

    __tablename__ = "provenance_documents"

    kind: Mapped[DocumentKind] = mapped_column(enum_col(DocumentKind))
    purchase_order_id: Mapped[uuid.UUID | None] = fk("purchase_orders")
    inbound_shipment_id: Mapped[uuid.UUID | None] = fk("inbound_shipments")
    product_id: Mapped[uuid.UUID | None] = fk("products")
    supplier_id: Mapped[uuid.UUID | None] = fk("suppliers")
    storage_key: Mapped[str] = mapped_column(String(300), comment="private/...")
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = count()
    doc_number: Mapped[str | None] = mapped_column(String(100))
    doc_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    extracted: Mapped[dict[str, Any]] = json_obj(comment="AI đọc chứng từ")
    notes: Mapped[str | None] = mapped_column(Text)
    uploaded_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)
