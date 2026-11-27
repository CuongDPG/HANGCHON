"""Sàn giả: lưu sản phẩm/đơn trong bộ nhớ; `simulate_order` giả lập khách đặt trên sàn."""

from __future__ import annotations

from datetime import datetime

from app.core.enums import Channel
from app.core.timeutil import now_utc
from app.integrations._mockutil import short_id
from app.integrations.base import IntegrationError
from app.integrations.marketplaces import (
    ORDER_STATUSES,
    MarketplaceOrder,
    MarketplaceOrderLine,
    MarketplaceProduct,
    MarketplacesDriver,
)


class Driver(MarketplacesDriver):
    name = "mock"
    supports_deactivate = True

    def __init__(self) -> None:
        self.products: dict[str, tuple[Channel, MarketplaceProduct]] = {}
        self.orders: list[MarketplaceOrder] = []
        self.status_updates: list[
            tuple[Channel, str, str, str | None]
        ] = []  # (sàn, mã đơn sàn, trạng thái, mã vận đơn)
        self.deactivated: set[str] = set()
        self.fail: set[str] = set()  # test: mã món trên sàn mà lệnh ngừng/mở bán sẽ lỗi

    async def upsert_product(self, marketplace: Channel, product: MarketplaceProduct) -> str:
        ext = product.external_id or f"{marketplace.value}_{short_id(product.sku, marketplace)}"
        self.products[ext] = (marketplace, product.model_copy(update={"external_id": ext}))
        return ext

    async def update_stock(self, marketplace: Channel, external_id: str, stock: int) -> None:
        if external_id not in self.products:
            raise IntegrationError("Sản phẩm chưa có trên sàn.")
        ch, p = self.products[external_id]
        self.products[external_id] = (ch, p.model_copy(update={"stock": stock}))

    async def deactivate_product(self, marketplace: Channel, external_id: str) -> None:
        # sàn giả giữ món trong bộ nhớ từng tiến trình: món đồng bộ ở tiến trình khác vẫn nhận lệnh (ghi lại)
        if external_id in self.fail:
            raise IntegrationError("Sàn giả lập báo lỗi khi ngừng bán.")
        self.deactivated.add(external_id)

    async def activate_product(self, marketplace: Channel, external_id: str) -> None:
        if external_id in self.fail:
            raise IntegrationError("Sàn giả lập báo lỗi khi mở bán lại.")
        self.deactivated.discard(external_id)

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
        if status not in ORDER_STATUSES:
            raise IntegrationError(f"Trạng thái «{status}» không hỗ trợ.")
        # sàn giả giữ đơn trong bộ nhớ của từng tiến trình: đơn kéo về ở tiến trình khác vẫn nhận cập nhật (ghi lại)
        self.status_updates.append((marketplace, external_id, status, tracking_code))
        for i, o in enumerate(self.orders):
            if o.external_id == external_id:
                self.orders[i] = o.model_copy(update={"status": status})
