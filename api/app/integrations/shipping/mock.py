"""Vận chuyển giả, **không giữ trạng thái**: mã vận đơn mang mốc thời gian tạo, trạng thái suy ra từ thời gian đã trôi
(mỗi MOCK_SHIPPING_STEP_SECONDS lên một nấc) nên API và worker thấy giống nhau.

Chuỗi trạng thái: created → picked_up → in_transit → out_for_delivery → delivered.
Mã chứa «F» ở vị trí dịch vụ (service="fail") đi nhánh giao thất bại: ... → failed_delivery → returning → returned."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.enums import Carrier, ShippingStatus
from app.core.security import verify_hmac_sha256
from app.core.timeutil import now_utc
from app.integrations._mockutil import short_id
from app.integrations.base import IntegrationError
from app.integrations.shipping import (
    ShipmentCreated,
    ShippingDriver,
    ShippingQuote,
    ShippingRequest,
    TrackingEvent,
    TrackingInfo,
)

_HAPPY = [
    (ShippingStatus.CREATED, "Đã tạo vận đơn, chờ lấy hàng"),
    (ShippingStatus.PICKED_UP, "Đã lấy hàng"),
    (ShippingStatus.IN_TRANSIT, "Đang trung chuyển"),
    (ShippingStatus.OUT_FOR_DELIVERY, "Đang giao hàng"),
    (ShippingStatus.DELIVERED, "Giao hàng thành công"),
]
_FAIL = [
    *_HAPPY[:4],
    (ShippingStatus.FAILED_DELIVERY, "Giao không thành công: không liên lạc được người nhận"),
    (ShippingStatus.RETURNING, "Đang hoàn hàng về người gửi"),
    (ShippingStatus.RETURNED, "Đã hoàn hàng"),
]
_SERVICES = {
    "standard": ("Giao tiêu chuẩn", 1.0, 2, 4),
    "express": ("Giao nhanh", 1.6, 1, 2),
    "fail": ("Giao thử nhánh lỗi", 1.0, 2, 4),
}


def _b36(n: int) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = chars[r] + s
    return s or "0"


class Driver(ShippingDriver):
    name = "mock"

    def __init__(self) -> None:
        self.cancelled: set[str] = set()
        self.time_offset = timedelta(0)  # test có thể tua nhanh: driver.time_offset += timedelta(hours=5)

    def advance(self, steps: int = 1) -> None:
        self.time_offset += timedelta(seconds=settings.mock_shipping_step_seconds * steps)

    async def quote(self, req: ShippingRequest) -> list[ShippingQuote]:
        base = 18_000 + max(0, (req.weight_grams - 500) // 500) * 5_000
        far = 0 if req.to.province.strip().lower() in settings.shipping_from_province.lower() else 12_000
        return [
            ShippingQuote(
                carrier=Carrier.MOCK,
                service=key,
                service_name=name,
                fee_vnd=int((base + far) * mult) // 1000 * 1000,
                eta_days_min=lo,
                eta_days_max=hi,
            )
            for key, (name, mult, lo, hi) in _SERVICES.items()
            if key != "fail"
        ]

    async def create(self, req: ShippingRequest, service: str) -> ShipmentCreated:
        if service not in _SERVICES:
            raise IntegrationError(f"Dịch vụ giao hàng không tồn tại: {service}")
        created = now_utc() + self.time_offset
        flag = "F" if service == "fail" else "S"
        code = f"MK{flag}{_b36(int(created.timestamp()))}{short_id(req.order_code, created, length=4).upper()}"
        quotes = {q.service: q for q in await self.quote(req)}
        fee = quotes.get(service, next(iter(quotes.values()))).fee_vnd
        return ShipmentCreated(
            carrier=Carrier.MOCK,
            service=service,
            tracking_code=code,
            fee_vnd=fee,
            label_url=f"https://placehold.co/400x600/png?text=NHAN+{code}",
            expected_delivery_at=created + timedelta(days=_SERVICES[service][3]),
        )

    def _created_at(self, code: str) -> datetime:
        try:
            return datetime.fromtimestamp(int(code[3:-4], 36), tz=UTC)
        except ValueError as e:
            raise IntegrationError(f"Mã vận đơn không hợp lệ: {code}") from e

    async def track(self, tracking_code: str) -> TrackingInfo:
        created = self._created_at(tracking_code)
        chain = _FAIL if tracking_code[2] == "F" else _HAPPY
        step = settings.mock_shipping_step_seconds
        elapsed = (now_utc() + self.time_offset - created).total_seconds()
        reached = min(len(chain), int(elapsed // step) + 1)
        events = [
            TrackingEvent(
                tracking_code=tracking_code,
                status=s,
                description=d,
                occurred_at=created + timedelta(seconds=step * i),
                location="Kho giả lập",
            )
            for i, (s, d) in enumerate(chain[:reached])
        ]
        if tracking_code in self.cancelled:  # huỷ khi còn ở nấc «created» → dừng ở đó
            events = events[:1]
            events.append(
                TrackingEvent(
                    tracking_code=tracking_code,
                    status=ShippingStatus.CANCELLED,
                    description="Đã huỷ vận đơn",
                    occurred_at=now_utc(),
                )
            )
        return TrackingInfo(tracking_code=tracking_code, status=events[-1].status, events=events)

    async def cancel(self, tracking_code: str) -> None:
        info = await self.track(tracking_code)
        if info.status != ShippingStatus.CREATED:
            raise IntegrationError("Hãng đã lấy hàng, không huỷ được vận đơn.", code="cannot_cancel")
        self.cancelled.add(tracking_code)

    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[TrackingEvent]:
        sig = {k.lower(): v for k, v in headers.items()}.get("x-mock-signature", "")
        if not verify_hmac_sha256(settings.hooks_mock_secret, body, sig):
            raise IntegrationError("Chữ ký webhook không hợp lệ.", code="invalid_signature")
        return [TrackingEvent.model_validate(e) for e in json.loads(body or b"{}").get("events", [])]
