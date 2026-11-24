"""Shopee Open Platform v2 — **khung driver**, viết theo tài liệu công khai (open.shopee.com), CHƯA thử thật.

Đã có: ký yêu cầu, kéo đơn (get_order_list + get_order_detail), cập nhật tồn, sửa tên/giá sản phẩm đã có.
Chưa làm: tạo sản phẩm mới (cần mã ngành hàng, ảnh tải lên media_space, cài đặt vận chuyển), giao hàng qua
logistics/ship_order, làm mới access token (OAuth). Khoá: `SHOPEE_PARTNER_ID`, `SHOPEE_PARTNER_KEY` (config chung);
`SHOPEE_SHOP_ID`, `SHOPEE_ACCESS_TOKEN` đọc từ biến môi trường hệ thống (người tích hợp nên chuyển vào Settings).
Bật: `MARKETPLACES_DRIVER=shopee` (orders dùng driver thật theo từng sàn khi driver khác `mock`).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.config import settings
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

    def _creds(self) -> tuple[str, str, str, str]:
        pid, key = settings.shopee_partner_id, settings.shopee_partner_key
        shop, token = os.environ.get("SHOPEE_SHOP_ID", ""), os.environ.get("SHOPEE_ACCESS_TOKEN", "")
        if not (pid and key and shop and token):
            raise IntegrationNotConfigured("Chưa đủ khoá Shopee (partner id/key, shop id, access token).")
        return str(pid), key, shop, token

    async def _call(
        self, method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        pid, key, shop, token = self._creds()
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
        self._check(marketplace)
        raise IntegrationNotConfigured("Giao đơn Shopee qua logistics/ship_order chưa làm (khung driver).")
