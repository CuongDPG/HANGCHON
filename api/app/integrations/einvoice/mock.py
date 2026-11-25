"""Hoá đơn điện tử giả: số tăng dần, cùng `reference` thì trả lại hoá đơn đã phát hành (không trùng)."""

from __future__ import annotations

from typing import Literal

from app.core.timeutil import now_utc
from app.integrations._mockutil import short_id
from app.integrations.base import IntegrationError
from app.integrations.einvoice import (
    AdjustmentRequest,
    EInvoiceDriver,
    InvoiceLine,
    InvoiceRequest,
    InvoiceState,
    InvoiceStatus,
    IssuedInvoice,
)


def _check_total(lines: list[InvoiceLine], total_vnd: int) -> None:
    if total_vnd != sum(line.quantity * line.unit_price_vnd for line in lines):
        raise IntegrationError("Tổng tiền không khớp các dòng hàng.", code="invoice_total_mismatch")


class Driver(EInvoiceDriver):
    name = "mock"

    def __init__(self) -> None:
        self.issued: dict[str, IssuedInvoice] = {}
        self.cancelled: set[str] = set()
        self.superseded: dict[str, InvoiceStatus] = {}  # hoá đơn gốc → adjusted | replaced

    def _new(self, reference: str, original: str | None = None) -> IssuedInvoice:
        n = len(self.issued) + 1
        inv = IssuedInvoice(
            external_id=f"EINV{short_id(reference)}",
            series="1C26TMK",
            number=f"{n:08d}",
            lookup_code=short_id("lookup", reference, length=12).upper(),
            issued_at=now_utc(),
            pdf_url=f"https://mock.hangchon.local/einvoice/{n:08d}.pdf",
            xml_url=f"https://mock.hangchon.local/einvoice/{n:08d}.xml",
            original_external_id=original,
        )
        self.issued[reference] = inv
        return inv

    def _find(self, external_id: str) -> IssuedInvoice:
        for inv in self.issued.values():
            if inv.external_id == external_id:
                return inv
        raise IntegrationError("Không thấy hoá đơn.")

    async def issue(self, req: InvoiceRequest) -> IssuedInvoice:
        _check_total(req.lines, req.total_vnd)
        return self.issued.get(req.reference) or self._new(req.reference)

    async def cancel(self, external_id: str, reason: str) -> None:
        self._find(external_id)
        self.cancelled.add(external_id)

    async def _supersede(self, req: AdjustmentRequest, kind: InvoiceStatus) -> IssuedInvoice:
        self._find(req.original_external_id)
        if req.original_external_id in self.cancelled:
            raise IntegrationError("Hoá đơn gốc đã huỷ.")
        if kind == "replaced":
            _check_total(req.lines, req.total_vnd)
        if req.reference in self.issued:
            return self.issued[req.reference]
        self.superseded[req.original_external_id] = kind
        return self._new(req.reference, original=req.original_external_id)

    async def adjust(self, req: AdjustmentRequest) -> IssuedInvoice:
        return await self._supersede(req, "adjusted")

    async def replace(self, req: AdjustmentRequest) -> IssuedInvoice:
        return await self._supersede(req, "replaced")

    async def get_status(self, external_id: str) -> InvoiceState:
        inv = self._find(external_id)
        status: InvoiceStatus = (
            "cancelled" if external_id in self.cancelled else self.superseded.get(external_id, "issued")
        )
        return InvoiceState(
            external_id=inv.external_id,
            status=status,
            tax_authority_code=f"M1-26-{inv.lookup_code[:5]}",
            checked_at=now_utc(),
        )

    async def download(self, external_id: str, fmt: Literal["pdf", "xml"] = "pdf") -> bytes:
        inv = self._find(external_id)
        if fmt == "xml":
            return f'<?xml version="1.0" encoding="UTF-8"?><HDon><SHDon>{inv.number}</SHDon></HDon>'.encode()
        return b"%PDF-1.4\n% hoa don gia " + inv.number.encode() + b"\n%%EOF\n"
