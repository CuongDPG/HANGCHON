"""Hoá đơn điện tử (k5). Driver: `mock` (mặc định). Nhà cung cấp thật bổ sung khi cần."""

from __future__ import annotations

import abc
from datetime import datetime

from pydantic import BaseModel, Field


class InvoiceLine(BaseModel):
    name: str
    unit: str = "cái"
    quantity: int
    unit_price_vnd: int
    vat_rate_pct: float | None = None  # hộ kinh doanh thường không tách VAT


class InvoiceRequest(BaseModel):
    reference: str = Field(description="Mã đơn hàng hoặc mã nội bộ, dùng chống phát hành trùng")
    buyer_name: str
    buyer_tax_code: str | None = None
    buyer_address: str | None = None
    buyer_email: str | None = None
    lines: list[InvoiceLine]
    total_vnd: int
    payment_method: str = "TM/CK"


class IssuedInvoice(BaseModel):
    external_id: str
    series: str
    number: str
    lookup_code: str
    issued_at: datetime
    pdf_url: str | None = None
    xml_url: str | None = None


class EInvoiceDriver(abc.ABC):
    name: str

    @abc.abstractmethod
    async def issue(self, req: InvoiceRequest) -> IssuedInvoice: ...

    @abc.abstractmethod
    async def cancel(self, external_id: str, reason: str) -> None: ...
