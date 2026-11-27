"""TikTok Shop Partner API (bản 202309) — **khung driver**, viết theo tài liệu công khai
(partner.tiktokshop.com/docv2), CHƯA thử thật.

Đã có: ký yêu cầu, kéo đơn (orders/search), cập nhật tồn theo SKU, báo đã gửi hàng (người bán tự giao, kèm mã vận
đơn — xem `update_order_status`), ngừng bán / mở bán lại (`POST /product/202309/products/deactivate` và `/activate`,
body `product_ids` — theo tài liệu bên thứ ba, CHƯA đối chiếu Partner Center). Chưa làm: tạo sản phẩm mới (ngành hàng, ảnh, thuộc tính bắt buộc), làm mới access
token. Khoá: `TIKTOK_SHOP_APP_KEY`, `TIKTOK_SHOP_APP_SECRET`
(config chung); `TIKTOK_SHOP_ACCESS_TOKEN`, `TIKTOK_SHOP_CIPHER` đọc từ biến môi trường hệ thống.
`external_id` của món = `<product_id>:<sku_id>` trên TikTok Shop.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
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

BASE = "https://open-api.tiktokglobalshop.com"


def sign(app_secret: str, path: str, params: dict[str, Any], body: str = "") -> str:
    """Ghép path + các cặp key+value (bỏ sign, access_token; xếp theo key) + body, bọc app_secret hai đầu, HMAC-SHA256."""
    joined = "".join(f"{k}{params[k]}" for k in sorted(params) if k not in ("sign", "access_token"))
    base = f"{app_secret}{path}{joined}{body}{app_secret}"
    return hmac.new(app_secret.encode(), base.encode(), hashlib.sha256).hexdigest()


class Driver(MarketplacesDriver):
    name = "tiktok_shop"
    supports_deactivate = True

    async def _creds(self) -> tuple[str, str, str, str]:
        """Cài đặt → Mạng xã hội (thẻ TikTok Shop, token tự làm mới) > biến môi trường."""
        from app.integrations import channel_config as cc
        from app.integrations.channel_oauth import tts_access_token

        key, secret = cc.value("tiktok_shop", "app_key"), cc.value("tiktok_shop", "app_secret")
        cipher = cc.value("tiktok_shop", "shop_cipher")
        if not (key and secret and cipher):
            raise IntegrationNotConfigured("Chưa đủ khoá TikTok Shop (app key/secret, access token, shop cipher).")
        return key, secret, await tts_access_token(), cipher

    async def _call(
        self, method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        key, secret, token, cipher = await self._creds()
        q: dict[str, Any] = {"app_key": key, "timestamp": int(time.time()), "shop_cipher": cipher, **(params or {})}
        raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False) if body is not None else ""
        q["sign"] = sign(secret, path, q, raw)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.request(
                    method, f"{BASE}{path}", params=q, content=raw or None,
                    headers={"x-tts-access-token": token, "content-type": "application/json"},
                )  # fmt: skip
        except httpx.HTTPError as e:
            raise IntegrationError("Không kết nối được TikTok Shop.") from e
        data = r.json() if r.content else {}
        if r.status_code != 200 or data.get("code") not in (0, None):
            raise IntegrationError(f"TikTok Shop báo lỗi: {data.get('message') or r.status_code}")
        return data.get("data") or {}

    @staticmethod
    def _check(mk: Channel) -> None:
        if mk != Channel.TIKTOK_SHOP:
            raise IntegrationNotConfigured("Driver TikTok Shop chỉ dùng cho TikTok Shop.")

    async def upsert_product(self, marketplace: Channel, product: MarketplaceProduct) -> str:
        self._check(marketplace)
        if not product.external_id or ":" not in product.external_id:
            raise IntegrationNotConfigured(
                "Tạo món mới trên TikTok Shop cần ngành hàng, ảnh và thuộc tính bắt buộc. Chị tạo món với SKU "
                f"«{product.sku}» trên TikTok Shop rồi ghi mã «product_id:sku_id» để đồng bộ giá và tồn."
            )
        await self.update_stock(marketplace, product.external_id, product.stock)
        return product.external_id

    async def update_stock(self, marketplace: Channel, external_id: str, stock: int) -> None:
        self._check(marketplace)
        product_id, sku_id = external_id.split(":", 1)
        await self._call(
            "POST",
            f"/product/202309/products/{product_id}/inventory/update",
            body={"skus": [{"id": sku_id, "inventory": [{"quantity": max(0, stock)}]}]},
        )

    async def deactivate_product(self, marketplace: Channel, external_id: str) -> None:
        """«Deactivate Products» 202309 (cả món, mọi SKU). Đường dẫn và body theo tài liệu bên thứ ba, CHƯA đối chiếu
        tài liệu chính thức và CHƯA thử thật — kiểm trước khi bật."""
        self._check(marketplace)
        await self._call(
            "POST", "/product/202309/products/deactivate", body={"product_ids": [external_id.split(":", 1)[0]]}
        )

    async def activate_product(self, marketplace: Channel, external_id: str) -> None:
        """«Activate Product» 202309 — cùng ghi chú như `deactivate_product`."""
        self._check(marketplace)
        await self._call(
            "POST", "/product/202309/products/activate", body={"product_ids": [external_id.split(":", 1)[0]]}
        )

    async def fetch_orders(self, marketplace: Channel, since: datetime | None = None) -> list[MarketplaceOrder]:
        self._check(marketplace)
        start = since or datetime.now(UTC) - timedelta(days=3)
        out: list[MarketplaceOrder] = []
        token = ""
        while True:
            params: dict[str, Any] = {"page_size": 50}
            if token:
                params["page_token"] = token
            data = await self._call(
                "POST", "/order/202309/orders/search", params=params, body={"create_time_ge": int(start.timestamp())}
            )
            for o in data.get("orders") or []:
                addr = o.get("recipient_address") or {}
                pay = o.get("payment") or {}
                districts = addr.get("district_info") or []
                out.append(
                    MarketplaceOrder(
                        marketplace=Channel.TIKTOK_SHOP,
                        external_id=str(o["id"]),
                        status=o.get("status", ""),
                        buyer_name=addr.get("name") or "Khách TikTok Shop",
                        buyer_phone=addr.get("phone_number"),
                        address_line=addr.get("full_address"),
                        province=next(
                            (d.get("address_name") for d in districts if d.get("address_level") == "L1"), None
                        ),
                        lines=[
                            MarketplaceOrderLine(
                                sku=li.get("seller_sku") or str(li.get("sku_id")),
                                name=li.get("product_name", ""),
                                quantity=int(li.get("quantity", 1)),
                                unit_price_vnd=int(float(li.get("sale_price") or 0)),
                            )
                            for li in o.get("line_items") or []
                        ],
                        total_vnd=int(float(pay.get("total_amount") or 0)),
                        shipping_fee_vnd=int(float(pay.get("shipping_fee") or 0)),
                        placed_at=datetime.fromtimestamp(int(o.get("create_time", time.time())), tz=UTC),
                        raw=o,
                    )
                )
            token = data.get("next_page_token") or ""
            if not token:
                break
        return out

    async def update_order_status(
        self, marketplace: Channel, external_id: str, status: str, tracking_code: str | None = None
    ) -> None:
        """Người bán tự giao (hãng mình gọi): «Mark Package As Shipped» bản 202309 —
        `POST /fulfillment/202309/orders/{order_id}/packages` với `tracking_number` + `shipping_provider_id`
        (mã hãng giao trên TikTok Shop, lấy từ «Get Shipping Providers»; đặt ở `TIKTOK_SHOP_SHIPPING_PROVIDER_ID`).
        CHƯA thử thật; tên tài liệu đã đối chiếu trên Partner Center, đường dẫn và các ô body chưa đối chiếu được toàn
        văn — kiểm lại trên tài liệu trước khi bật. «delivered»: bỏ qua, TikTok Shop tự cập nhật theo mã vận đơn."""
        self._check(marketplace)
        if status == "delivered":
            return
        if status != "shipped":
            raise IntegrationError(f"Trạng thái «{status}» không hỗ trợ.")
        if not tracking_code:
            raise IntegrationError("Thiếu mã vận đơn để báo TikTok Shop.")
        provider = os.environ.get("TIKTOK_SHOP_SHIPPING_PROVIDER_ID", "").strip()
        if not provider:
            raise IntegrationNotConfigured("Chưa đặt TIKTOK_SHOP_SHIPPING_PROVIDER_ID (mã hãng giao trên TikTok Shop).")
        await self._call(
            "POST",
            f"/fulfillment/202309/orders/{external_id}/packages",
            body={"tracking_number": tracking_code, "shipping_provider_id": provider},
        )
