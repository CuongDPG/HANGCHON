"""Thanh toán chuyển khoản VietQR: tạo yêu cầu (mã QR + nội dung chuyển khoản), nhận khoản chuyển tới.

Driver: `mock` (mặc định, có `simulate_transfer`), `sepay` (webhook SePay)."""

from __future__ import annotations

import abc
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.config import settings


class PaymentRequest(BaseModel):
    order_code: str
    amount_vnd: int
    transfer_content: str = Field(description="Nội dung chuyển khoản khách phải ghi, dùng để khớp đơn")
    bank_code: str
    account_no: str
    account_name: str
    qr_payload: str
    qr_image_url: str | None = None


class IncomingTransfer(BaseModel):
    external_id: str = Field(description="Mã giao dịch phía ngân hàng/cổng, duy nhất")
    amount_vnd: int
    content: str
    received_at: datetime
    payer_name: str | None = None
    payer_account: str | None = None
    bank_code: str | None = None
    raw: dict = Field(default_factory=dict)


def transfer_content_for(order_code: str) -> str:
    """Nội dung chuyển khoản chuẩn: '<tiền tố> <mã đơn>' — không dấu, không ký tự đặc biệt để ngân hàng giữ nguyên."""
    return f"{settings.payment_code_prefix} {order_code}".upper()


class PaymentsDriver(abc.ABC):
    name: str

    @abc.abstractmethod
    async def create_request(self, order_code: str, amount_vnd: int) -> PaymentRequest: ...

    @abc.abstractmethod
    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[IncomingTransfer]:
        """Xác thực chữ ký rồi trả các khoản chuyển tới; sai chữ ký thì raise IntegrationError."""

    @abc.abstractmethod
    async def list_transactions(self, since: datetime | None = None) -> list[IncomingTransfer]:
        """Đối soát: các khoản chuyển tới từ `since` (dùng khi webhook lỡ)."""
