"""Hoá đơn điện tử giả: số tăng dần, cùng `reference` thì trả lại hoá đơn đã phát hành (không trùng)."""

from __future__ import annotations

from app.core.timeutil import now_utc
from app.integrations._mockutil import short_id
from app.integrations.base import IntegrationError
from app.integrations.einvoice import EInvoiceDriver, InvoiceRequest, IssuedInvoice


class Driver(EInvoiceDriver):
    name = "mock"

    def __init__(self) -> None:
        self.issued: dict[str, IssuedInvoice] = {}
        self.cancelled: set[str] = set()

    async def issue(self, req: InvoiceRequest) -> IssuedInvoice:
        if req.total_vnd != sum(line.quantity * line.unit_price_vnd for line in req.lines):
            raise IntegrationError("Tổng tiền không khớp các dòng hàng.", code="invoice_total_mismatch")
        if req.reference in self.issued:
            return self.issued[req.reference]
        n = len(self.issued) + 1
        inv = IssuedInvoice(
            external_id=f"EINV{short_id(req.reference)}",
            series="1C26TMK",
            number=f"{n:08d}",
            lookup_code=short_id("lookup", req.reference, length=12).upper(),
            issued_at=now_utc(),
            pdf_url=f"https://mock.hangchon.local/einvoice/{n:08d}.pdf",
        )
        self.issued[req.reference] = inv
        return inv

    async def cancel(self, external_id: str, reason: str) -> None:
        if not any(i.external_id == external_id for i in self.issued.values()):
            raise IntegrationError("Không thấy hoá đơn.")
        self.cancelled.add(external_id)
