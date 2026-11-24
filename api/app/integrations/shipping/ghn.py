"""Giao Hàng Nhanh (GHN) — báo phí, tạo vận đơn, in nhãn, theo dõi, huỷ, webhook trạng thái.

**Viết theo tài liệu API công khai của GHN (api.ghn.vn/home/docs), CHƯA thử với tài khoản thật.**

Cấu hình: `SHIPPING_DRIVER=ghn` (hoặc bật trong cài đặt «Hãng giao đang bật»), `GHN_TOKEN`, `GHN_SHOP_ID`.
Môi trường thử của GHN: đặt biến môi trường hệ thống `GHN_ENV=dev`.
Webhook: khai `<API_BASE_URL>/api/hooks/shipping/ghn` ở trang quản lý GHN. GHN không ký webhook, nên mỗi lần
nhận webhook mình **hỏi lại GHN** trạng thái vận đơn (nguồn tin cậy), không tin nội dung gửi tới.

GHN cần mã quận (DistrictID) và mã phường (WardCode): driver tự tra theo tên (danh mục master-data, khớp gần đúng)
nếu `Address.codes` chưa có `ghn_district_id` / `ghn_ward_code`.
"""

from __future__ import annotations

import json
import os
import unicodedata
from datetime import UTC, datetime
from typing import Any

import httpx
from rapidfuzz import fuzz, process

from app.core.config import settings
from app.core.enums import Carrier, ShippingStatus
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.integrations.shipping import (
    ShipmentCreated,
    ShippingDriver,
    ShippingQuote,
    ShippingRequest,
    TrackingEvent,
    TrackingInfo,
)

PROD = "https://online-gateway.ghn.vn/shiip/public-api"
DEV = "https://dev-online-gateway.ghn.vn/shiip/public-api"

# Trạng thái GHN → trạng thái chung
STATUS_MAP: dict[str, ShippingStatus] = {
    "ready_to_pick": ShippingStatus.CREATED,
    "picking": ShippingStatus.CREATED,
    "money_collect_picking": ShippingStatus.CREATED,
    "picked": ShippingStatus.PICKED_UP,
    "storing": ShippingStatus.IN_TRANSIT,
    "transporting": ShippingStatus.IN_TRANSIT,
    "sorting": ShippingStatus.IN_TRANSIT,
    "delivering": ShippingStatus.OUT_FOR_DELIVERY,
    "money_collect_delivering": ShippingStatus.OUT_FOR_DELIVERY,
    "delivered": ShippingStatus.DELIVERED,
    "delivery_fail": ShippingStatus.FAILED_DELIVERY,
    "waiting_to_return": ShippingStatus.FAILED_DELIVERY,
    "return": ShippingStatus.RETURNING,
    "return_transporting": ShippingStatus.RETURNING,
    "return_sorting": ShippingStatus.RETURNING,
    "returning": ShippingStatus.RETURNING,
    "return_fail": ShippingStatus.RETURNING,
    "returned": ShippingStatus.RETURNED,
    "cancel": ShippingStatus.CANCELLED,
    "exception": ShippingStatus.FAILED_DELIVERY,
    "damage": ShippingStatus.FAILED_DELIVERY,
    "lost": ShippingStatus.FAILED_DELIVERY,
}
DESCRIPTIONS = {
    "ready_to_pick": "Chờ lấy hàng", "picking": "Đang lấy hàng", "picked": "Đã lấy hàng", "storing": "Hàng đã về kho",
    "transporting": "Đang luân chuyển", "sorting": "Đang phân loại", "delivering": "Đang giao hàng",
    "delivered": "Giao hàng thành công", "delivery_fail": "Giao không thành công", "waiting_to_return": "Chờ trả hàng",
    "return": "Trả hàng", "returning": "Đang trả hàng", "returned": "Đã trả hàng", "cancel": "Đã huỷ",
    "exception": "Đơn gặp sự cố", "damage": "Hàng hư hỏng", "lost": "Hàng thất lạc",
}  # fmt: skip
SERVICES = {2: ("standard", "GHN · Hàng nhẹ", 2, 4), 5: ("heavy", "GHN · Hàng nặng", 3, 5)}


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    for w in ("tinh ", "thanh pho ", "tp. ", "tp ", "quan ", "huyen ", "thi xa ", "phuong ", "xa ", "thi tran "):
        s = s.replace(w, "")
    return " ".join(s.split())


class Driver(ShippingDriver):
    name = "ghn"

    def __init__(self) -> None:
        self.base = DEV if os.environ.get("GHN_ENV") == "dev" else PROD
        self._provinces: list[dict[str, Any]] | None = None
        self._districts: dict[int, list[dict[str, Any]]] = {}
        self._wards: dict[int, list[dict[str, Any]]] = {}

    # ---- HTTP ----

    def _headers(self) -> dict[str, str]:
        if not settings.ghn_token or not settings.ghn_shop_id:
            raise IntegrationNotConfigured("Chưa đặt GHN_TOKEN / GHN_SHOP_ID.")
        return {"Token": settings.ghn_token, "ShopId": str(settings.ghn_shop_id), "Content-Type": "application/json"}

    async def _call(self, path: str, body: dict[str, Any] | None = None, *, method: str = "POST") -> Any:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.request(method, f"{self.base}{path}", headers=self._headers(), json=body)
        except httpx.HTTPError as e:
            raise IntegrationError("Không kết nối được GHN.") from e
        try:
            data = r.json()
        except ValueError as e:
            raise IntegrationError(f"GHN trả dữ liệu lạ ({r.status_code}).") from e
        if r.status_code != 200 or data.get("code") != 200:
            raise IntegrationError(f"GHN báo lỗi: {data.get('message') or r.status_code}")
        return data.get("data")

    # ---- danh mục địa chỉ ----

    @staticmethod
    def _match(items: list[dict[str, Any]], name: str | None, key: str, names_key: str) -> dict[str, Any] | None:
        """Khớp gần đúng theo tên (kể cả tên khác trong NameExtension)."""
        if not name or not items:
            return None
        names: list[str] = []
        owners: list[dict[str, Any]] = []
        for it in items:
            for n in [it.get(key), *(it.get(names_key) or [])]:
                if n:
                    names.append(_norm(n))
                    owners.append(it)
        hit = process.extractOne(_norm(name), names, scorer=fuzz.WRatio, score_cutoff=80)
        return owners[hit[2]] if hit else None

    async def provinces(self) -> list[dict[str, Any]]:
        if self._provinces is None:
            self._provinces = await self._call("/master-data/province", method="GET") or []
        return self._provinces

    async def districts(self, province_id: int) -> list[dict[str, Any]]:
        if province_id not in self._districts:
            self._districts[province_id] = await self._call("/master-data/district", {"province_id": province_id}) or []
        return self._districts[province_id]

    async def wards(self, district_id: int) -> list[dict[str, Any]]:
        if district_id not in self._wards:
            self._wards[district_id] = (
                await self._call(f"/master-data/ward?district_id={district_id}", method="GET") or []
            )
        return self._wards[district_id]

    async def resolve(self, req: ShippingRequest) -> tuple[int, str]:
        codes = req.to.codes
        if codes.get("ghn_district_id") and codes.get("ghn_ward_code"):
            return int(codes["ghn_district_id"]), codes["ghn_ward_code"]
        prov = self._match(await self.provinces(), req.to.province, "ProvinceName", "NameExtension")
        if prov is None:
            raise IntegrationError(f"GHN không nhận ra tỉnh/thành «{req.to.province}».", code="address_unresolved")
        dist = self._match(await self.districts(prov["ProvinceID"]), req.to.district, "DistrictName", "NameExtension")
        if dist is None:
            raise IntegrationError(
                f"GHN cần quận/huyện hợp lệ (đang ghi «{req.to.district or ''}»).", code="address_unresolved"
            )
        ward = self._match(await self.wards(dist["DistrictID"]), req.to.ward, "WardName", "NameExtension")
        if ward is None:
            raise IntegrationError(
                f"GHN cần phường/xã hợp lệ (đang ghi «{req.to.ward or ''}»).", code="address_unresolved"
            )
        return int(dist["DistrictID"]), str(ward["WardCode"])

    async def address_suggestions(self, level: str, q: str, parent: str | None) -> list[dict[str, str | None]]:
        """Gợi ý cho ô địa chỉ ở trang đặt hàng (orders gọi nếu driver có hàm này)."""
        if level == "province":
            items, key, idk = await self.provinces(), "ProvinceName", "ProvinceID"
        elif level == "district" and parent:
            items, key, idk = await self.districts(int(parent)), "DistrictName", "DistrictID"
        elif level == "ward" and parent:
            items, key, idk = await self.wards(int(parent)), "WardName", "WardCode"
        else:
            return []
        qn = _norm(q)
        hits = [it for it in items if not qn or qn in _norm(it.get(key))]
        return [{"name": it[key], "code": str(it[idk])} for it in hits[:8]]

    # ---- interface ----

    async def quote(self, req: ShippingRequest) -> list[ShippingQuote]:
        district_id, ward_code = await self.resolve(req)
        out = []
        for type_id, (key, label, lo, hi) in SERVICES.items():
            if type_id == 5 and req.weight_grams < 20_000:
                continue  # hàng nặng chỉ dùng cho kiện lớn
            data = await self._call(
                "/v2/shipping-order/fee",
                {
                    "service_type_id": type_id, "to_district_id": district_id, "to_ward_code": ward_code,
                    "weight": req.weight_grams, "length": req.length_cm or 20, "width": req.width_cm or 15,
                    "height": req.height_cm or 10, "insurance_value": min(req.declared_value_vnd, 5_000_000),
                    "cod_value": req.cod_amount_vnd,
                },
            )  # fmt: skip
            out.append(
                ShippingQuote(
                    carrier=Carrier.GHN,
                    service=key,
                    service_name=label,
                    fee_vnd=int(data["total"]),
                    eta_days_min=lo,
                    eta_days_max=hi,
                )
            )
        return out

    async def create(self, req: ShippingRequest, service: str) -> ShipmentCreated:
        district_id, ward_code = await self.resolve(req)
        type_id = next((t for t, v in SERVICES.items() if v[0] == service), 2)
        address = ", ".join(x for x in (req.to.address_line, req.to.ward, req.to.district, req.to.province) if x)
        data = await self._call(
            "/v2/shipping-order/create",
            {
                "payment_type_id": 1,  # shop trả phí giao (phí đã thu của khách trong đơn)
                "required_note": "CHOXEMHANGKHONGTHU",
                "client_order_code": req.order_code,
                "to_name": req.to.name, "to_phone": req.to.phone, "to_address": address,
                "to_ward_code": ward_code, "to_district_id": district_id,
                "cod_amount": req.cod_amount_vnd, "insurance_value": min(req.declared_value_vnd, 5_000_000),
                "weight": req.weight_grams, "length": req.length_cm or 20, "width": req.width_cm or 15,
                "height": req.height_cm or 10, "service_type_id": type_id, "note": req.note or "",
                "items": [{"name": i.get("name", "Hàng"), "quantity": int(i.get("quantity", 1)), "weight": max(1, req.weight_grams // max(1, len(req.items)))} for i in req.items] or [{"name": "Hàng", "quantity": 1, "weight": req.weight_grams}],
            },
        )  # fmt: skip
        code = data["order_code"]
        token = await self._call("/v2/a5/gen-token", {"order_codes": [code]})
        label = (
            f"{self.base.replace('/shiip/public-api', '')}/a5/public-api/printA5?token={token['token']}"
            if token
            else None
        )
        eta = data.get("expected_delivery_time")
        return ShipmentCreated(
            carrier=Carrier.GHN, service=service, tracking_code=code, fee_vnd=int(data.get("total_fee") or 0),
            label_url=label, expected_delivery_at=datetime.fromisoformat(eta.replace("Z", "+00:00")) if isinstance(eta, str) else None,
            raw=data,
        )  # fmt: skip

    async def track(self, tracking_code: str) -> TrackingInfo:
        data = await self._call("/v2/shipping-order/detail", {"order_code": tracking_code})
        events: list[TrackingEvent] = []
        for log in data.get("log") or []:
            st = STATUS_MAP.get(log.get("status", ""), ShippingStatus.IN_TRANSIT)
            at = datetime.fromisoformat(str(log.get("updated_date")).replace("Z", "+00:00"))
            events.append(
                TrackingEvent(
                    tracking_code=tracking_code,
                    status=st,
                    description=DESCRIPTIONS.get(log.get("status", ""), log.get("status", "")),
                    occurred_at=at,
                )
            )
        current = STATUS_MAP.get(data.get("status", ""), ShippingStatus.CREATED)
        if not events:
            events.append(
                TrackingEvent(
                    tracking_code=tracking_code,
                    status=current,
                    description=DESCRIPTIONS.get(data.get("status", ""), ""),
                    occurred_at=datetime.now(UTC),
                )
            )
        return TrackingInfo(tracking_code=tracking_code, status=current, events=events)

    async def cancel(self, tracking_code: str) -> None:
        await self._call("/v2/switch-status/cancel", {"order_codes": [tracking_code]})

    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[TrackingEvent]:
        try:
            data = json.loads(body or b"{}")
        except json.JSONDecodeError as e:
            raise IntegrationError("Webhook GHN không phải JSON.") from e
        code = data.get("OrderCode")
        if not code:
            return []
        return (await self.track(code)).events  # không tin dữ liệu gửi tới: hỏi lại GHN
