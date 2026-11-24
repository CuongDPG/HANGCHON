"""Thanh toán giả: `simulate_transfer` giả lập khách chuyển khoản; webhook mock ký HMAC bằng HOOKS_MOCK_SECRET.

Webhook body: `{"transfers": [IncomingTransfer...]}`, header `X-Mock-Signature: sha256=<hex>`."""

from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import quote

from app.core.config import settings
from app.core.security import hmac_sha256, verify_hmac_sha256
from app.core.timeutil import now_utc
from app.integrations._mockutil import short_id
from app.integrations.base import IntegrationError
from app.integrations.payments import IncomingTransfer, PaymentRequest, PaymentsDriver, transfer_content_for


class Driver(PaymentsDriver):
    name = "mock"

    def __init__(self) -> None:
        self.transfers: list[IncomingTransfer] = []

    async def create_request(self, order_code: str, amount_vnd: int) -> PaymentRequest:
        content = transfer_content_for(order_code)
        payload = f"MOCKQR|{settings.bank_code}|{settings.bank_account_no}|{amount_vnd}|{content}"
        return PaymentRequest(
            order_code=order_code,
            amount_vnd=amount_vnd,
            transfer_content=content,
            bank_code=settings.bank_code,
            account_no=settings.bank_account_no,
            account_name=settings.bank_account_name,
            qr_payload=payload,
            qr_image_url=f"https://placehold.co/400x400/png?text={quote('QR ' + content)}",
        )

    def simulate_transfer(
        self, amount_vnd: int, content: str, *, payer_name: str = "NGUYEN VAN A", received_at: datetime | None = None
    ) -> IncomingTransfer:
        t = IncomingTransfer(
            external_id=f"MOCKTX{short_id(content, amount_vnd, len(self.transfers), now_utc().timestamp()).upper()}",
            amount_vnd=amount_vnd,
            content=content,
            received_at=received_at or now_utc(),
            payer_name=payer_name,
            payer_account="9999999999",
            bank_code=settings.bank_code,
        )
        self.transfers.append(t)
        return t

    @staticmethod
    def sign(body: bytes) -> str:
        return "sha256=" + hmac_sha256(settings.hooks_mock_secret, body)

    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[IncomingTransfer]:
        sig = {k.lower(): v for k, v in headers.items()}.get("x-mock-signature", "")
        if not verify_hmac_sha256(settings.hooks_mock_secret, body, sig):
            raise IntegrationError("Chữ ký webhook không hợp lệ.", code="invalid_signature")
        data = json.loads(body or b"{}")
        return [IncomingTransfer.model_validate(t) for t in data.get("transfers", [])]

    async def list_transactions(self, since: datetime | None = None) -> list[IncomingTransfer]:
        return [t for t in self.transfers if since is None or t.received_at > since]
