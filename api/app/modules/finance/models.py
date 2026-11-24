"""finance — nền tảng tài chính (i5, k1, k4, k5): sổ doanh thu/chi phí hộ kinh doanh, chi phí, hoá đơn điện tử,
báo cáo tuần, sao lưu."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Date, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, Timestamps, UUIDPk, count, enum_col, fk, flag, json_list, json_obj, money
from app.core.enums import StrEnum


class LedgerKind(StrEnum):
    REVENUE = "revenue"  # doanh thu bán hàng (ghi khi đơn được xác nhận/giao — xem docs/data-model.md)
    REFUND = "refund"  # giảm trừ doanh thu
    COST_OF_GOODS = "cost_of_goods"
    SHIPPING = "shipping"
    PAYMENT_FEE = "payment_fee"
    MARKETPLACE_FEE = "marketplace_fee"
    EXPENSE = "expense"
    ADJUSTMENT = "adjustment"


class LedgerDirection(StrEnum):
    IN = "in"
    OUT = "out"


class LedgerSource(StrEnum):
    AUTO = "auto"  # ghi tự động từ đơn/chi phí (k1)
    MANUAL = "manual"


class ExpenseCategory(StrEnum):
    GOODS = "goods"  # mua hàng
    SAMPLES = "samples"
    SHIPPING = "shipping"
    PACKAGING = "packaging"
    ADS = "ads"
    AI = "ai"  # tiền AI (k2)
    SOFTWARE = "software"
    FEES = "fees"
    TAX = "tax"
    OTHER = "other"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    ISSUING = "issuing"
    ISSUED = "issued"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REPLACED = "replaced"


class ReportStatus(StrEnum):
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class BackupKind(StrEnum):
    DATABASE = "database"
    STORAGE = "storage"
    FULL = "full"


class BackupStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BackupTrigger(StrEnum):
    SCHEDULE = "schedule"
    MANUAL = "manual"


class LedgerEntry(UUIDPk, Timestamps, Base):
    """Sổ doanh thu, chi phí (k1). Một dòng = một nghiệp vụ; xuất bảng kê theo kỳ phục vụ khai thuế hộ kinh doanh."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        Index("ix_ledger_entries_date_kind", "entry_date", "kind"),
        UniqueConstraint("source_key", name="uq_ledger_entries_source_key"),
    )

    entry_date: Mapped[date] = mapped_column(Date, comment="Ngày nghiệp vụ (giờ VN)")
    kind: Mapped[LedgerKind] = mapped_column(enum_col(LedgerKind))
    direction: Mapped[LedgerDirection] = mapped_column(enum_col(LedgerDirection))
    amount_vnd: Mapped[int] = money(comment="Luôn dương; chiều tiền theo direction")
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(60))
    document_no: Mapped[str | None] = mapped_column(String(60), comment="Số chứng từ (mã đơn, số hoá đơn...)")
    source: Mapped[LedgerSource] = mapped_column(enum_col(LedgerSource), default=LedgerSource.AUTO)
    source_key: Mapped[str | None] = mapped_column(String(120), comment="Chống ghi trùng: vd order:<id>:revenue")
    order_id: Mapped[uuid.UUID | None] = fk("orders")
    payment_id: Mapped[uuid.UUID | None] = fk("payments")
    expense_id: Mapped[uuid.UUID | None] = fk("expenses")
    invoice_id: Mapped[uuid.UUID | None] = fk("invoices")
    purchase_order_id: Mapped[uuid.UUID | None] = fk("purchase_orders")
    period: Mapped[str] = mapped_column(String(7), index=True, comment="YYYY-MM")
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)


class Expense(UUIDPk, Timestamps, Base):
    __tablename__ = "expenses"
    __table_args__ = (Index("ix_expenses_date_category", "incurred_on", "category"),)

    incurred_on: Mapped[date] = mapped_column(Date)
    category: Mapped[ExpenseCategory] = mapped_column(enum_col(ExpenseCategory))
    amount_vnd: Mapped[int] = money()
    original_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    description: Mapped[str] = mapped_column(Text)
    vendor: Mapped[str | None] = mapped_column(String(200))
    purchase_order_id: Mapped[uuid.UUID | None] = fk("purchase_orders")
    receipt_storage_key: Mapped[str | None] = mapped_column(String(300))
    payment_method: Mapped[str | None] = mapped_column(String(30))
    is_deductible: Mapped[bool] = flag(True)
    created_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)
    source_key: Mapped[str | None] = mapped_column(
        String(120), unique=True, comment="Chi phí sinh từ sự kiện expense.recorded của module khác (chống ghi trùng)"
    )


class Invoice(UUIDPk, Timestamps, Base):
    """Hoá đơn điện tử (k5)."""

    __tablename__ = "invoices"

    order_id: Mapped[uuid.UUID | None] = fk("orders")
    reference: Mapped[str] = mapped_column(String(60), unique=True, comment="Chống phát hành trùng")
    provider: Mapped[str] = mapped_column(String(30), default="mock")
    status: Mapped[InvoiceStatus] = mapped_column(enum_col(InvoiceStatus), default=InvoiceStatus.DRAFT)
    series: Mapped[str | None] = mapped_column(String(20))
    number: Mapped[str | None] = mapped_column(String(20))
    lookup_code: Mapped[str | None] = mapped_column(String(40))
    external_id: Mapped[str | None] = mapped_column(String(120))
    buyer_name: Mapped[str] = mapped_column(String(200))
    buyer_tax_code: Mapped[str | None] = mapped_column(String(20))
    buyer_address: Mapped[str | None] = mapped_column(Text)
    buyer_email: Mapped[str | None] = mapped_column(String(254))
    lines: Mapped[list[Any]] = json_list()
    total_vnd: Mapped[int] = money()
    issued_at: Mapped[datetime | None]
    pdf_storage_key: Mapped[str | None] = mapped_column(String(300))
    xml_storage_key: Mapped[str | None] = mapped_column(String(300))
    replaces_id: Mapped[uuid.UUID | None] = fk("invoices")
    error: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict[str, Any]] = json_obj()


class WeeklyReport(UUIDPk, Timestamps, Base):
    """Báo cáo tuần (i5): doanh thu, biên lợi nhuận từng món, khách quay lại, bài hiệu quả."""

    __tablename__ = "weekly_reports"

    week_start: Mapped[date] = mapped_column(Date, unique=True, comment="Thứ Hai")
    week_end: Mapped[date] = mapped_column(Date)
    status: Mapped[ReportStatus] = mapped_column(enum_col(ReportStatus), default=ReportStatus.GENERATING)
    revenue_vnd: Mapped[int] = money()
    cogs_vnd: Mapped[int] = money()
    gross_profit_vnd: Mapped[int] = money()
    expenses_vnd: Mapped[int] = money()
    order_count: Mapped[int] = count()
    customer_count: Mapped[int] = count()
    returning_customer_count: Mapped[int] = count()
    ai_cost_vnd: Mapped[int] = money()
    product_margins: Mapped[list[Any]] = json_list(comment='[{"product_id","name","qty","revenue_vnd","margin_pct"}]')
    top_posts: Mapped[list[Any]] = json_list()
    metrics: Mapped[dict[str, Any]] = json_obj()
    summary: Mapped[str | None] = mapped_column(Text)
    highlights: Mapped[list[Any]] = json_list()
    generated_at: Mapped[datetime | None]
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)


class Backup(UUIDPk, CreatedAt, Base):
    """Sao lưu hằng ngày (k4)."""

    __tablename__ = "backups"

    kind: Mapped[BackupKind] = mapped_column(enum_col(BackupKind))
    status: Mapped[BackupStatus] = mapped_column(enum_col(BackupStatus), default=BackupStatus.RUNNING)
    trigger: Mapped[BackupTrigger] = mapped_column(enum_col(BackupTrigger), default=BackupTrigger.SCHEDULE)
    storage_key: Mapped[str | None] = mapped_column(String(300), comment="private/backups/...")
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    error: Mapped[str | None] = mapped_column(Text)
    triggered_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)
