"""Sàn giả: lưu sản phẩm/đơn trong bộ nhớ; `simulate_order` giả lập khách đặt trên sàn."""

from __future__ import annotations

from datetime import datetime

from app.core.enums import Channel
from app.core.timeutil import now_utc
from app.integrations._mockutil import short_id
from app.integrations.base import IntegrationError
from app.integrations.marketplaces import (
    MarketplaceOrder,
    MarketplaceOrderLine,
    MarketplaceProduct,
    MarketplacesDriver,
)


class Driver(MarketplacesDriver):
    name = "mock"

    def __init__(self) -> None:
        self.products: dict[str, tuple[Channel, MarketplaceProduct]] = {}
        self.orders: list[MarketplaceOrder] = []

    async def upsert_product(self, marketplace: Channel, product: MarketplaceProduct) -> str:
        ext = product.external_id or f"{marketplace.value}_{short_id(product.sku, marketplace)}"
        self.products[ext] = (marketplace, product.model_copy(update={"external_id": ext}))
        return ext

    async def update_stock(self, marketplace: Channel, external_id: str, stock: int) -> None:
        if external_id not in self.products:
            raise IntegrationError("Sản phẩm chưa có trên sàn.")
        ch, p = self.products[external_id]
        self.products[external_id] = (ch, p.model_copy(update={"stock": stock}))

    def simulate_order(self, marketplace: Channel, sku: str, quantity: int = 1, unit_price_vnd: int = 150_000):
        o = MarketplaceOrder(
            marketplace=marketplace,
            external_id=f"{marketplace.value.upper()}{short_id(sku, len(self.orders), now_utc().timestamp())}",
            status="awaiting_shipment",
            buyer_name="Khách sàn (giả lập)",
            buyer_phone="0900000000",
            address_line="1 Đường Mẫu",
            province="Hà Nội",
            lines=[MarketplaceOrderLine(sku=sku, name=sku, quantity=quantity, unit_price_vnd=unit_price_vnd)],
            total_vnd=quantity * unit_price_vnd,
            placed_at=now_utc(),
        )
        self.orders.append(o)
        return o

    async def fetch_orders(self, marketplace: Channel, since: datetime | None = None) -> list[MarketplaceOrder]:
        return [o for o in self.orders if o.marketplace == marketplace and (since is None or o.placed_at > since)]

    async def update_order_status(
        self, marketplace: Channel, external_id: str, status: str, tracking_code: str | None = None
    ) -> None:
        for i, o in enumerate(self.orders):
            if o.external_id == external_id:
                self.orders[i] = o.model_copy(update={"status": status})
                return
        raise IntegrationError("Không thấy đơn trên sàn.")
