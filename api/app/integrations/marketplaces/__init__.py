"""Sàn TMĐT (g9): đồng bộ sản phẩm, tồn kho, kéo đơn.

Driver: `mock` (mặc định), `tiktok_shop`, `shopee`."""

from __future__ import annotations

import abc
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import Channel

ORDER_STATUSES = ("shipped", "delivered")


class MarketplaceProduct(BaseModel):
    sku: str
    name: str
    description: str
    price_vnd: int
    stock: int
    image_urls: list[str] = Field(default_factory=list)
    weight_grams: int | None = None
    category_hint: str | None = None
    external_id: str | None = None  # có thì cập nhật, không thì tạo mới


class MarketplaceOrderLine(BaseModel):
    sku: str
    name: str
    quantity: int
    unit_price_vnd: int


class MarketplaceOrder(BaseModel):
    marketplace: Channel
    external_id: str
    status: str
    buyer_name: str
    buyer_phone: str | None = None
    address_line: str | None = None
    province: str | None = None
    lines: list[MarketplaceOrderLine]
    total_vnd: int
    shipping_fee_vnd: int = 0
    placed_at: datetime
    raw: dict = Field(default_factory=dict)


def driver_for(mk: Channel) -> MarketplacesDriver:
    """Công tắc của sàn ở Cài đặt → Mạng xã hội; chưa đặt thì theo MARKETPLACES_DRIVER (mock = sàn giả, khác = driver
    thật của đúng sàn đó: tiktok_shop / shopee)."""
    from app.core.config import settings
    from app.integrations import channel_config, get_driver

    chosen = channel_config.mode(mk.value)
    if chosen == "real":
        return get_driver("marketplaces", mk.value)
    if chosen == "mock" or settings.marketplaces_driver == "mock":
        return get_driver("marketplaces", "mock")
    return get_driver("marketplaces", mk.value)


class MarketplacesDriver(abc.ABC):
    name: str
    # Ngừng bán / mở bán lại một món trên sàn qua API. False = nơi gọi tự đặt tồn về 0 thay thế (và nói rõ với chị).
    supports_deactivate: bool = False

    @abc.abstractmethod
    async def upsert_product(self, marketplace: Channel, product: MarketplaceProduct) -> str:
        """Trả về external_id trên sàn."""

    @abc.abstractmethod
    async def update_stock(self, marketplace: Channel, external_id: str, stock: int) -> None: ...

    @abc.abstractmethod
    async def fetch_orders(self, marketplace: Channel, since: datetime | None = None) -> list[MarketplaceOrder]: ...

    @abc.abstractmethod
    async def update_order_status(
        self, marketplace: Channel, external_id: str, status: str, tracking_code: str | None = None
    ) -> None:
        """Báo trạng thái giao của đơn lên sàn. `status` ∈ ORDER_STATUSES: «shipped» (kèm mã vận đơn của hãng giao
        mình tự gọi) · «delivered». Gọi lặp cùng mốc phải an toàn ở phía mình (orders tự giữ mốc đã báo)."""

    async def deactivate_product(self, marketplace: Channel, external_id: str) -> None:
        """Ngừng bán (ẩn khỏi gian hàng, giữ nguyên món trên sàn để mở bán lại). Chỉ gọi khi `supports_deactivate`."""
        from app.integrations.base import IntegrationNotConfigured

        raise IntegrationNotConfigured("Sàn này chưa có lệnh ngừng bán qua API.")

    async def activate_product(self, marketplace: Channel, external_id: str) -> None:
        """Mở bán lại món đã ngừng bằng `deactivate_product`."""
        from app.integrations.base import IntegrationNotConfigured

        raise IntegrationNotConfigured("Sàn này chưa có lệnh mở bán lại qua API.")
