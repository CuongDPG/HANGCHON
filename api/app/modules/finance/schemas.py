"""Schema đọc cơ bản của finance (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.modules.finance.models import (
    BackupKind,
    BackupStatus,
    BackupTrigger,
    ExpenseCategory,
    InvoiceStatus,
    LedgerDirection,
    LedgerKind,
    LedgerSource,
    ReportStatus,
)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LedgerEntryOut(ORM):
    """Sổ doanh thu, chi phí (k1). Một dòng = một nghiệp vụ; xuất bảng kê theo kỳ phục vụ khai thuế hộ kinh doanh."""

    id: uuid.UUID
    entry_date: date
    kind: LedgerKind
    direction: LedgerDirection
    amount_vnd: int
    description: str
    category: str | None
    document_no: str | None
    source: LedgerSource
    source_key: str | None
    order_id: uuid.UUID | None
    payment_id: uuid.UUID | None
    expense_id: uuid.UUID | None
    invoice_id: uuid.UUID | None
    purchase_order_id: uuid.UUID | None
    period: str
    notes: str | None
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ExpenseOut(ORM):
    id: uuid.UUID
    incurred_on: date
    category: ExpenseCategory
    amount_vnd: int
    original_amount: Decimal | None
    currency: str | None
    fx_rate: Decimal | None
    description: str
    vendor: str | None
    purchase_order_id: uuid.UUID | None
    receipt_storage_key: str | None
    payment_method: str | None
    is_deductible: bool
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class InvoiceOut(ORM):
    """Hoá đơn điện tử (k5)."""

    id: uuid.UUID
    order_id: uuid.UUID | None
    reference: str
    provider: str
    status: InvoiceStatus
    series: str | None
    number: str | None
    lookup_code: str | None
    external_id: str | None
    buyer_name: str
    buyer_tax_code: str | None
    buyer_address: str | None
    buyer_email: str | None
    lines: list[Any]
    total_vnd: int
    issued_at: datetime | None
    pdf_storage_key: str | None
    xml_storage_key: str | None
    replaces_id: uuid.UUID | None
    error: str | None
    raw: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class WeeklyReportOut(ORM):
    """Báo cáo tuần (i5): doanh thu, biên lợi nhuận từng món, khách quay lại, bài hiệu quả."""

    id: uuid.UUID
    week_start: date
    week_end: date
    status: ReportStatus
    revenue_vnd: int
    cogs_vnd: int
    gross_profit_vnd: int
    expenses_vnd: int
    order_count: int
    customer_count: int
    returning_customer_count: int
    ai_cost_vnd: int
    product_margins: list[Any]
    top_posts: list[Any]
    metrics: dict[str, Any]
    summary: str | None
    highlights: list[Any]
    generated_at: datetime | None
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class BackupOut(ORM):
    """Sao lưu hằng ngày (k4)."""

    id: uuid.UUID
    kind: BackupKind
    status: BackupStatus
    trigger: BackupTrigger
    storage_key: str | None
    size_bytes: int | None
    checksum: str | None
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    triggered_by_id: uuid.UUID | None
    created_at: datetime
