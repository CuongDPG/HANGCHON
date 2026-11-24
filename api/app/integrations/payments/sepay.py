"""SePay (https://sepay.vn) — nhận biến động số dư chuyển khoản qua webhook, đối soát qua API, tạo chuỗi VietQR.

**Viết theo tài liệu công khai của SePay, CHƯA thử với tài khoản thật.**

Cấu hình (`api/.env`):
- `PAYMENTS_DRIVER=sepay`
- `SEPAY_WEBHOOK_SECRET` = «API Key» chị đặt ở mục Webhooks của SePay (chọn kiểu chứng thực «API Key»);
  SePay gửi header `Authorization: Apikey <khoá>`.
- `SEPAY_API_KEY` = API Token (my.sepay.vn → Cấu hình công ty → API Access) để đối soát `list_transactions`.
- `BANK_CODE` (mã BIN NAPAS 6 số, vd 970436, hoặc tên viết tắt: VCB, MB, TCB, ACB...), `BANK_ACCOUNT_NO`,
  `BANK_ACCOUNT_NAME`, `PAYMENT_CODE_PREFIX` (khớp «Cấu hình mã thanh toán» trên SePay, mặc định HC).
- URL webhook khai trên SePay: `<API_BASE_URL>/api/hooks/payments/sepay`.

Dữ liệu webhook (SePay → mình), JSON:
    {"id": 92704, "gateway": "Vietcombank", "transactionDate": "2023-03-25 14:02:37",
     "accountNumber": "0123499999", "code": null, "content": "HC 48213", "transferType": "in",
     "transferAmount": 2277000, "accumulated": 19077000, "subAccount": null,
     "referenceCode": "MBVCB.3278907687", "description": ""}
`transactionDate` là giờ Việt Nam. Chỉ lấy `transferType == "in"`. Mình trả `{"success": true}` (HTTP 200).
"""

from __future__ import annotations

import hmac
import json
from datetime import datetime
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.timeutil import VN_TZ
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.integrations.payments import IncomingTransfer, PaymentRequest, PaymentsDriver, transfer_content_for

API_BASE = "https://my.sepay.vn/userapi"
QR_IMAGE_BASE = "https://qr.sepay.vn/img"

# Mã BIN NAPAS của một số ngân hàng (danh sách VietQR). Ghi BANK_CODE bằng BIN 6 số là chắc nhất.
BANK_BINS = {
    "VCB": "970436", "VIETCOMBANK": "970436", "ICB": "970415", "VTB": "970415", "VIETINBANK": "970415",
    "BIDV": "970418", "VBA": "970405", "AGRIBANK": "970405", "MB": "970422", "MBBANK": "970422",
    "TCB": "970407", "TECHCOMBANK": "970407", "ACB": "970416", "VPB": "970432", "VPBANK": "970432",
    "TPB": "970423", "TPBANK": "970423", "STB": "970403", "SACOMBANK": "970403", "VIB": "970441",
    "SHB": "970443", "HDB": "970437", "HDBANK": "970437", "OCB": "970448", "MSB": "970426",
    "SEAB": "970440", "SEABANK": "970440", "EIB": "970431", "EXIMBANK": "970431", "LPB": "970449",
}  # fmt: skip


def bank_bin(code: str) -> str:
    c = (code or "").strip().upper()
    if c.isdigit() and len(c) == 6:
        return c
    if c in BANK_BINS:
        return BANK_BINS[c]
    raise IntegrationNotConfigured(f"Không biết mã BIN của ngân hàng «{code}». Ghi BANK_CODE bằng mã BIN 6 số.")


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def crc16_ccitt(data: str) -> str:
    """CRC-16/CCITT-FALSE (đa thức 0x1021, khởi tạo 0xFFFF) theo chuẩn EMVCo cho trường 63."""
    crc = 0xFFFF
    for b in data.encode("utf-8"):
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def vietqr_payload(bin_code: str, account_no: str, amount_vnd: int, content: str) -> str:
    """Chuỗi VietQR (EMVCo, NAPAS 247, chuyển nhanh tới tài khoản) có sẵn số tiền + nội dung."""
    beneficiary = _tlv("00", bin_code) + _tlv("01", account_no)
    merchant = _tlv("00", "A000000727") + _tlv("01", beneficiary) + _tlv("02", "QRIBFTTA")
    body = (
        _tlv("00", "01")
        + _tlv("01", "12")  # QR động (có số tiền)
        + _tlv("38", merchant)
        + _tlv("53", "704")  # VND
        + _tlv("54", str(int(amount_vnd)))
        + _tlv("58", "VN")
        + _tlv("62", _tlv("08", content[:50]))
        + "6304"
    )
    return body + crc16_ccitt(body)


class Driver(PaymentsDriver):
    name = "sepay"

    async def create_request(self, order_code: str, amount_vnd: int) -> PaymentRequest:
        content = transfer_content_for(order_code)
        bin_code = bank_bin(settings.bank_code)
        qs = urlencode(
            {
                "acc": settings.bank_account_no,
                "bank": bin_code,
                "amount": int(amount_vnd),
                "des": content,
                "template": "compact",
            }
        )
        return PaymentRequest(
            order_code=order_code,
            amount_vnd=amount_vnd,
            transfer_content=content,
            bank_code=bin_code,
            account_no=settings.bank_account_no,
            account_name=settings.bank_account_name,
            qr_payload=vietqr_payload(bin_code, settings.bank_account_no, amount_vnd, content),
            qr_image_url=f"{QR_IMAGE_BASE}?{qs}",
        )

    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[IncomingTransfer]:
        secret = settings.sepay_webhook_secret
        if not secret:
            raise IntegrationNotConfigured("Chưa đặt SEPAY_WEBHOOK_SECRET (API Key của webhook SePay).")
        auth = {k.lower(): v for k, v in headers.items()}.get("authorization", "")
        given = auth[len("Apikey ") :].strip() if auth.lower().startswith("apikey ") else ""
        if not given or not hmac.compare_digest(given, secret):
            raise IntegrationError("Khoá webhook SePay không đúng.", code="invalid_signature")
        try:
            data = json.loads(body or b"{}")
        except json.JSONDecodeError as e:
            raise IntegrationError("Webhook SePay không phải JSON.") from e
        items = data if isinstance(data, list) else [data]
        return [t for t in (self._from_webhook(d) for d in items) if t is not None]

    @staticmethod
    def _parse_time(value: str | None) -> datetime:
        if not value:
            return datetime.now(VN_TZ)
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=VN_TZ)

    def _from_webhook(self, d: dict) -> IncomingTransfer | None:
        if str(d.get("transferType", "in")).lower() != "in":
            return None
        amount = int(d.get("transferAmount") or 0)
        if amount <= 0 or d.get("id") is None:
            return None
        content = d.get("content") or d.get("description") or ""
        if d.get("code") and str(d["code"]) not in content:
            content = f"{content} {d['code']}".strip()
        return IncomingTransfer(
            external_id=str(d["id"]),
            amount_vnd=amount,
            content=content,
            received_at=self._parse_time(d.get("transactionDate")),
            payer_name=None,
            payer_account=None,
            bank_code=d.get("gateway"),
            raw=d,
        )

    async def list_transactions(self, since: datetime | None = None) -> list[IncomingTransfer]:
        token = settings.sepay_api_key
        if not token:
            raise IntegrationNotConfigured("Chưa đặt SEPAY_API_KEY để đối soát giao dịch.")
        params: dict[str, str | int] = {"account_number": settings.bank_account_no, "limit": 200}
        if since:
            params["transaction_date_min"] = since.astimezone(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(
                    f"{API_BASE}/transactions/list", params=params, headers={"Authorization": f"Bearer {token}"}
                )
        except httpx.HTTPError as e:
            raise IntegrationError("Không kết nối được SePay.") from e
        if r.status_code != 200:
            raise IntegrationError(f"SePay báo lỗi {r.status_code}.")
        out: list[IncomingTransfer] = []
        for t in r.json().get("transactions") or []:
            amount = int(float(t.get("amount_in") or 0))
            if amount <= 0:
                continue
            out.append(
                IncomingTransfer(
                    external_id=str(t["id"]),
                    amount_vnd=amount,
                    content=t.get("transaction_content") or "",
                    received_at=self._parse_time(t.get("transaction_date")),
                    bank_code=t.get("bank_brand_name"),
                    raw=t,
                )
            )
        return out
