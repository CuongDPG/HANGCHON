"""Shopee Open Platform v2 — **khung driver**, viết theo tài liệu công khai (open.shopee.com), CHƯA thử thật.

Đã có: ký yêu cầu, kéo đơn (get_order_list + get_order_detail), cập nhật tồn, sửa tên/giá sản phẩm đã có,
báo đã gửi hàng (logistics/get_shipping_parameter + ship_order, kèm mã vận đơn). Chưa làm: tạo sản phẩm mới (cần mã
ngành hàng, ảnh tải lên media_space, cài đặt vận chuyển), làm mới access token (OAuth). Khoá: `SHOPEE_PARTNER_ID`, `SHOPEE_PARTNER_KEY` (config chung);
`SHOPEE_SHOP_ID`, `SHOPEE_ACCESS_TOKEN` đọc từ biến môi trường hệ thống (người tích hợp nên chuyển vào Settings).
Bật: `MARKETPLACES_DRIVER=shopee` (orders dùng driver thật theo từng sàn khi driver khác `mock`).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.enums import Channel
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.integrations.marketplaces import (
    MarketplaceOrder,
    MarketplaceOrderLine,
    MarketplaceProduct,
    MarketplacesDriver,
)

BASE = "https://partner.shopeemobile.com"


def sign(partner_key: str, partner_id: str, path: str, ts: int, access_token: str = "", shop_id: str = "") -> str:
    base = f"{partner_id}{path}{ts}{access_token}{shop_id}"
    return hmac.new(partner_key.encode(), base.encode(), hashlib.sha256).hexdigest()


class Driver(MarketplacesDriver):
    name = "shopee"

    async def _creds(self) -> tuple[str, str, str, str]:
        """Cài đặt → Mạng xã hội (thẻ Shopee, token tự làm mới) > biến môi trường."""
        from app.integrations import channel_config as cc
        from app.integrations.channel_oauth import shopee_access_token

        pid, key, shop = (
            cc.value("shopee", "partner_id"),
            cc.value("shopee", "partner_key"),
            cc.value("shopee", "shop_id"),
        )
        if not (pid and key and shop):
            raise IntegrationNotConfigured("Chưa đủ khoá Shopee (partner id/key, shop id, access token).")
        return str(pid), key, shop, await shopee_access_token()

    async def _call(
        self, method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        pid, key, shop, token = await self._creds()
        ts = int(time.time())
        q = {
            "partner_id": pid,
            "timestamp": ts,
            "access_token": token,
            "shop_id": shop,
            "sign": sign(key, pid, path, ts, token, shop),
            **(params or {}),
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.request(method, f"{BASE}{path}", params=q, json=body)
        except httpx.HTTPError as e:
            raise IntegrationError("Không kết nối được Shopee.") from e
        data = r.json() if r.content else {}
        if r.status_code != 200 or data.get("error"):
            raise IntegrationError(f"Shopee báo lỗi: {data.get('message') or data.get('error') or r.status_code}")
        return data.get("response") or {}

    @staticmethod
    def _check(mk: Channel) -> None:
        if mk != Channel.SHOPEE:
            raise IntegrationNotConfigured("Driver Shopee chỉ dùng cho Shopee.")

    async def upsert_product(self, marketplace: Channel, product: MarketplaceProduct) -> str:
        self._check(marketplace)
        if not product.external_id:
            raise IntegrationNotConfigured(
                "Tạo món mới trên Shopee cần ngành hàng và ảnh tải lên Shopee. Chị tạo món trên Shopee với SKU "
                f"«{product.sku}», lần đồng bộ sau sẽ cập nhật giá và tồn."
            )
        item_id = int(product.external_id)
        await self._call(
            "POST",
            "/api/v2/product/update_item",
            body={"item_id": item_id, "item_name": product.name[:120], "description": product.description[:3000]},
        )
        await self._call(
            "POST",
            "/api/v2/product/update_price",
            body={"item_id": item_id, "price_list": [{"model_id": 0, "original_price": product.price_vnd}]},
        )
        await self.update_stock(marketplace, product.external_id, product.stock)
        return product.external_id

    async def update_stock(self, marketplace: Channel, external_id: str, stock: int) -> None:
        self._check(marketplace)
        await self._call(
            "POST",
            "/api/v2/product/update_stock",
            body={
                "item_id": int(external_id),
                "stock_list": [{"model_id": 0, "seller_stock": [{"stock": max(0, stock)}]}],
            },
        )

    async def fetch_orders(self, marketplace: Channel, since: datetime | None = None) -> list[MarketplaceOrder]:
        self._check(marketplace)
        now = datetime.now(UTC)
        start = max(since or now - timedelta(days=3), now - timedelta(days=14))  # Shopee giới hạn 15 ngày mỗi lần
        sns: list[str] = []
        cursor = ""
        while True:
            res = await self._call("GET", "/api/v2/order/get_order_list", params={
                "time_range_field": "create_time", "time_from": int(start.timestamp()), "time_to": int(now.timestamp()),
                "page_size": 50, "cursor": cursor,
            })  # fmt: skip
            sns += [o["order_sn"] for o in res.get("order_list") or []]
            if not res.get("more"):
                break
            cursor = res.get("next_cursor") or ""
        out: list[MarketplaceOrder] = []
        for i in range(0, len(sns), 50):
            res = await self._call("GET", "/api/v2/order/get_order_detail", params={
                "order_sn_list": ",".join(sns[i : i + 50]),
                "response_optional_fields": "buyer_username,recipient_address,item_list,total_amount,estimated_shipping_fee",
            })  # fmt: skip
            for o in res.get("order_list") or []:
                addr = o.get("recipient_address") or {}
                out.append(
                    MarketplaceOrder(
                        marketplace=Channel.SHOPEE,
                        external_id=o["order_sn"],
                        status=o.get("order_status", ""),
                        buyer_name=addr.get("name") or o.get("buyer_username") or "Khách Shopee",
                        buyer_phone=addr.get("phone"),
                        address_line=addr.get("full_address"),
                        province=addr.get("state"),
                        lines=[
                            MarketplaceOrderLine(
                                sku=it.get("model_sku") or it.get("item_sku") or str(it.get("item_id")),
                                name=it.get("item_name", ""),
                                quantity=int(it.get("model_quantity_purchased", 1)),
                                unit_price_vnd=int(
                                    float(it.get("model_discounted_price") or it.get("model_original_price") or 0)
                                ),
                            )
                            for it in o.get("item_list") or []
                        ],
                        total_vnd=int(float(o.get("total_amount") or 0)),
                        shipping_fee_vnd=int(float(o.get("estimated_shipping_fee") or 0)),
                        placed_at=datetime.fromtimestamp(int(o.get("create_time", now.timestamp())), tz=UTC),
                        raw=o,
                    )
                )
        return out

    async def update_order_status(
        self, marketplace: Channel, external_id: str, status: str, tracking_code: str | None = None
    ) -> None:
        """Theo tài liệu v2.logistics.get_shipping_parameter + v2.logistics.ship_order (open.shopee.com), CHƯA thử thật.

        «shipped»: hỏi `get_shipping_parameter` xem đơn cần cách giao nào (`info_needed`), rồi `ship_order` kèm mã vận
        đơn của hãng mình tự gọi: ưu tiên `non_integrated` (kênh giao ngoài Shopee), không thì `pickup` (địa chỉ lấy hàng
        + khung giờ Shopee gợi ý), cuối cùng `dropoff`. «delivered»: Shopee chỉ mở API cập nhật giao xong
        (`v2.logistics.update_tracking_status`) cho người bán Brazil, nên ở Việt Nam bỏ qua — Shopee tự chốt theo mã
        vận đơn / người mua xác nhận."""
        self._check(marketplace)
        if status == "delivered":
            return
        if status != "shipped":
            raise IntegrationError(f"Trạng thái «{status}» không hỗ trợ.")
        param = await self._call("GET", "/api/v2/logistics/get_shipping_parameter", params={"order_sn": external_id})
        await self._call(
            "POST", "/api/v2/logistics/ship_order", body=ship_order_body(external_id, param, tracking_code)
        )


def ship_order_body(order_sn: str, param: dict[str, Any], tracking_code: str | None) -> dict[str, Any]:
    """Dựng body `ship_order` từ kết quả `get_shipping_parameter`: chọn một cách giao có trong `info_needed`, điền các ô
    mà `info_needed` đòi (theo tài liệu: khoá có mặt thì vẫn phải gửi object, kể cả rỗng)."""
    need = param.get("info_needed") or {}
    tracking = tracking_code or ""
    body: dict[str, Any] = {"order_sn": order_sn}
    if "non_integrated" in need:
        body["non_integrated"] = {"tracking_number": tracking} if tracking else {}
    elif "pickup" in need and ((param.get("pickup") or {}).get("address_list")):
        addrs = ((param.get("pickup") or {}).get("address_list")) or []
        addr = next((a for a in addrs if "pickup_address" in (a.get("address_flag") or [])), addrs[0])
        pick: dict[str, Any] = {"address_id": addr["address_id"]}
        slots = addr.get("time_slot_list") or []
        slot = next((t for t in slots if "recommended" in (t.get("flags") or [])), slots[0] if slots else None)
        if slot and slot.get("pickup_time_id"):
            pick["pickup_time_id"] = slot["pickup_time_id"]
        if tracking and "tracking_number" in (need.get("pickup") or []):
            pick["tracking_number"] = tracking
        body["pickup"] = pick
    elif "dropoff" in need:
        drop: dict[str, Any] = {}
        branches = ((param.get("dropoff") or {}).get("branch_list")) or []
        if "branch_id" in (need.get("dropoff") or []) and branches:
            drop["branch_id"] = branches[0]["branch_id"]
        if tracking and {"tracking_no", "tracking_number"} & set(need.get("dropoff") or []):
            drop["tracking_number"] = tracking
        body["dropoff"] = drop
    else:
        raise IntegrationError("Shopee không cho giao đơn này lúc này (kiểm trạng thái đơn trên Shopee).")
    return body
