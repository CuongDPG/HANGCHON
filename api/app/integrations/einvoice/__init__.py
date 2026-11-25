"""Hoá đơn điện tử (k5). Driver: `mock` (mặc định). Chưa chọn nhà cung cấp — interface này là chỗ cắm driver thật
(`app/integrations/einvoice/<ten>.py`, lớp `Driver(EInvoiceDriver)`).

Vòng đời: `issue` (phát hành, chống trùng theo `reference`) → `get_status` (tra trạng thái, gồm mã của cơ quan thuế
nếu có) → `download` (bản PDF để gửi khách / bản XML gốc để lưu trữ) → sai sót thì `adjust` (hoá đơn điều chỉnh) hoặc
`replace` (hoá đơn thay thế); `cancel` chỉ dùng khi nhà cung cấp / quy định còn cho huỷ (CHƯA CHẮC: quy định mới về
hoá đơn điện tử thu hẹp việc huỷ, ưu tiên điều chỉnh/thay thế — kiểm lại với nhà cung cấp khi tích hợp)."""

from __future__ import annotations

import abc
from datetime import datetime
from typing import Literal

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


InvoiceStatus = Literal["pending", "issued", "adjusted", "replaced", "cancelled", "error"]


class IssuedInvoice(BaseModel):
    external_id: str
    series: str
    number: str
    lookup_code: str
    issued_at: datetime
    pdf_url: str | None = None
    xml_url: str | None = None
    tax_authority_code: str | None = Field(default=None, description="Mã của cơ quan thuế (hoá đơn có mã), nếu có")
    original_external_id: str | None = Field(default=None, description="Hoá đơn gốc (khi đây là điều chỉnh/thay thế)")


class AdjustmentRequest(BaseModel):
    """Hoá đơn điều chỉnh hoặc thay thế cho một hoá đơn đã phát hành."""

    original_external_id: str
    reference: str = Field(description="Mã nội bộ của lần điều chỉnh / thay thế, chống phát hành trùng")
    reason: str
    lines: list[InvoiceLine] = Field(
        description="Điều chỉnh: các dòng chênh lệch (âm = giảm); thay thế: toàn bộ dòng mới"
    )
    total_vnd: int
    agreement_note: str | None = Field(default=None, description="Thoả thuận với người mua về sai sót, nếu cần")


class InvoiceState(BaseModel):
    external_id: str
    status: InvoiceStatus
    tax_authority_code: str | None = None
    message: str | None = Field(default=None, description="Lý do lỗi / thông báo của nhà cung cấp hoặc cơ quan thuế")
    checked_at: datetime


class EInvoiceDriver(abc.ABC):
    name: str

    @abc.abstractmethod
    async def issue(self, req: InvoiceRequest) -> IssuedInvoice: ...

    @abc.abstractmethod
    async def cancel(self, external_id: str, reason: str) -> None: ...

    @abc.abstractmethod
    async def adjust(self, req: AdjustmentRequest) -> IssuedInvoice: ...

    @abc.abstractmethod
    async def replace(self, req: AdjustmentRequest) -> IssuedInvoice: ...

    @abc.abstractmethod
    async def get_status(self, external_id: str) -> InvoiceState: ...

    @abc.abstractmethod
    async def download(self, external_id: str, fmt: Literal["pdf", "xml"] = "pdf") -> bytes: ...
