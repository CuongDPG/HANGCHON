"""Giao Hàng Tiết Kiệm (GHTK) — báo phí, tạo vận đơn, theo dõi, huỷ, webhook trạng thái.

**Viết theo tài liệu API công khai của GHTK (docs.giaohangtietkiem.vn), CHƯA thử với tài khoản thật.**

Cấu hình: `GHTK_TOKEN` (trong api/.env). Địa chỉ lấy hàng đọc từ biến môi trường hệ thống (chưa có trong
config chung — người tích hợp nên chuyển vào `Settings`): `GHTK_PICK_NAME`, `GHTK_PICK_TEL`, `GHTK_PICK_ADDRESS`,
`GHTK_PICK_DISTRICT`, `GHTK_PICK_WARD`; tỉnh lấy hàng = `SHIPPING_FROM_PROVINCE`. Môi trường thử: `GHTK_ENV=dev`.
Webhook: khai `<API_BASE_URL>/api/hooks/shipping/ghtk`. Mình hỏi lại GHTK trạng thái mỗi lần nhận webhook.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs

import httpx

from app.core.config import settings
from app.core.enums import Carrier, ShippingStatus
from app.core.timeutil import VN_TZ
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.integrations.shipping import (
    ShipmentCreated,
    ShippingDriver,
    ShippingQuote,
    ShippingRequest,
    TrackingEvent,
    TrackingInfo,
)

PROD = "https://services.giaohangtietkiem.vn"
DEV = "https://services-staging.ghtklab.com"

STATUS_MAP: dict[int, ShippingStatus] = {
    -1: ShippingStatus.CANCELLED,
    1: ShippingStatus.CREATED,
    2: ShippingStatus.CREATED,
    12: ShippingStatus.CREATED,
    8: ShippingStatus.CREATED,
    3: ShippingStatus.PICKED_UP,
    4: ShippingStatus.OUT_FOR_DELIVERY,
    10: ShippingStatus.OUT_FOR_DELIVERY,
    5: ShippingStatus.DELIVERED,
    6: ShippingStatus.DELIVERED,
    7: ShippingStatus.FAILED_DELIVERY,
    9: ShippingStatus.FAILED_DELIVERY,
    20: ShippingStatus.RETURNING,
    11: ShippingStatus.RETURNED,
    21: ShippingStatus.RETURNED,
    13: ShippingStatus.FAILED_DELIVERY,
}
SERVICES = {"road": ("GHTK · Đường bộ", 2, 5), "fly": ("GHTK · Bay", 1, 3)}


class Driver(ShippingDriver):
    name = "ghtk"

    def __init__(self) -> None:
        self.base = DEV if os.environ.get("GHTK_ENV") == "dev" else PROD

    def _headers(self) -> dict[str, str]:
        if not settings.ghtk_token:
            raise IntegrationNotConfigured("Chưa đặt GHTK_TOKEN.")
        return {"Token": settings.ghtk_token, "Content-Type": "application/json"}

    @staticmethod
    def _pick() -> dict[str, str]:
        pick = {
            "pick_name": os.environ.get("GHTK_PICK_NAME", ""),
            "pick_tel": os.environ.get("GHTK_PICK_TEL", ""),
            "pick_address": os.environ.get("GHTK_PICK_ADDRESS", ""),
            "pick_province": settings.shipping_from_province,
            "pick_district": os.environ.get("GHTK_PICK_DISTRICT", ""),
            "pick_ward": os.environ.get("GHTK_PICK_WARD", ""),
        }
        if not (pick["pick_name"] and pick["pick_tel"] and pick["pick_address"]):
            raise IntegrationNotConfigured("Chưa khai địa chỉ lấy hàng GHTK (GHTK_PICK_NAME/TEL/ADDRESS).")
        return pick

    async def _call(
        self, method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.request(
                    method, f"{self.base}{path}", headers=self._headers(), params=params, json=body
                )
        except httpx.HTTPError as e:
            raise IntegrationError("Không kết nối được GHTK.") from e
        try:
            data = r.json()
        except ValueError as e:
            raise IntegrationError(f"GHTK trả dữ liệu lạ ({r.status_code}).") from e
        if not data.get("success"):
            raise IntegrationError(f"GHTK báo lỗi: {data.get('message') or r.status_code}")
        return data

    async def quote(self, req: ShippingRequest) -> list[ShippingQuote]:
        pick = self._pick()
        out = []
        for transport, (label, lo, hi) in SERVICES.items():
            data = await self._call(
                "GET", "/services/shipment/fee",
                params={
                    "pick_province": pick["pick_province"], "pick_district": pick["pick_district"],
                    "province": req.to.province, "district": req.to.district or "", "ward": req.to.ward or "",
                    "address": req.to.address_line, "weight": req.weight_grams, "value": req.declared_value_vnd,
                    "transport": transport, "deliver_option": "none",
                },
            )  # fmt: skip
            fee = data.get("fee") or {}
            if fee.get("delivery") is False:
                continue  # tuyến này GHTK không giao
            out.append(
                ShippingQuote(
                    carrier=Carrier.GHTK,
                    service=transport,
                    service_name=label,
                    fee_vnd=int(fee.get("fee", 0)) + int(fee.get("insurance_fee", 0)),
                    eta_days_min=lo,
                    eta_days_max=hi,
                )
            )
        return out

    async def create(self, req: ShippingRequest, service: str) -> ShipmentCreated:
        per_item = max(0.1, req.weight_grams / 1000 / max(1, len(req.items) or 1))
        body = {
            "products": [{"name": i.get("name", "Hàng"), "weight": round(per_item, 2), "quantity": int(i.get("quantity", 1))} for i in req.items]
            or [{"name": "Hàng", "weight": round(req.weight_grams / 1000, 2), "quantity": 1}],
            "order": {
                "id": req.order_code, **self._pick(), "tel": req.to.phone, "name": req.to.name,
                "address": req.to.address_line, "province": req.to.province, "district": req.to.district or "",
                "ward": req.to.ward or "", "hamlet": "Khác", "is_freeship": "1", "pick_money": req.cod_amount_vnd,
                "value": req.declared_value_vnd, "transport": service if service in SERVICES else "road",
                "note": req.note or "",
            },
        }  # fmt: skip
        data = (await self._call("POST", "/services/shipment/order", body=body)).get("order") or {}
        label = data.get("label")
        if not label:
            raise IntegrationError("GHTK không trả mã vận đơn.")
        eta = data.get("estimated_deliver_time")
        expected = None
        if isinstance(eta, str):
            try:
                expected = datetime.strptime(eta[:10], "%Y-%m-%d").replace(tzinfo=VN_TZ)
            except ValueError:
                expected = None
        return ShipmentCreated(
            carrier=Carrier.GHTK, service=service, tracking_code=label, fee_vnd=int(data.get("fee") or 0),
            label_url=f"{self.base}/services/label/{label}", expected_delivery_at=expected or datetime.now(UTC) + timedelta(days=SERVICES.get(service, SERVICES["road"])[2]),
            raw=data,
        )  # fmt: skip

    async def track(self, tracking_code: str) -> TrackingInfo:
        o = (await self._call("GET", f"/services/shipment/v2/{tracking_code}")).get("order") or {}
        st = STATUS_MAP.get(int(o.get("status", 1)), ShippingStatus.IN_TRANSIT)
        modified = o.get("modified") or o.get("created")
        try:
            at = (
                datetime.strptime(modified, "%Y-%m-%d %H:%M:%S").replace(tzinfo=VN_TZ)
                if modified
                else datetime.now(UTC)
            )
        except ValueError:
            at = datetime.now(UTC)
        ev = TrackingEvent(
            tracking_code=tracking_code, status=st, description=o.get("status_text") or st.value, occurred_at=at
        )
        return TrackingInfo(tracking_code=tracking_code, status=st, events=[ev])

    async def cancel(self, tracking_code: str) -> None:
        await self._call("POST", f"/services/shipment/cancel/{tracking_code}")

    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[TrackingEvent]:
        try:
            data = json.loads(body or b"{}")
        except json.JSONDecodeError:
            data = {k: v[0] for k, v in parse_qs((body or b"").decode()).items()}  # GHTK có thể gửi dạng form
        label = data.get("label_id") or data.get("label")
        if not label:
            return []
        return (await self.track(str(label))).events  # không tin dữ liệu gửi tới: hỏi lại GHTK
