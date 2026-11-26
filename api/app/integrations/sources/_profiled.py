"""Bọc driver nguồn hàng bằng hồ sơ nguồn (`source_profiles`) — áp cho mọi đường lấy hàng (mock, web, onebound,
rakuten, routed) ở một chỗ:

- link đưa vào (`fetch_product`, `fetch_reviews`) → link ngắn chuẩn (vd `https://www.amazon.co.jp/dp/<ASIN>`);
- kết quả ra (tìm, tìm bằng ảnh, hồ sơ): link chuẩn, mã món theo hồ sơ (khử trùng theo mã), nhận ra sàn của link lạ,
  ảnh đổi sang cỡ lớn + chỉ giữ ảnh ở máy chủ ảnh của sàn + tối đa `max_images`.

Dùng: `wrap(get_driver("sources"))` trong `sources()` của sourcing / assessment.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import SourcePlatform
from app.integrations import source_profiles as sp
from app.integrations.sources import (
    MarketListing,
    SourceItem,
    SourceProduct,
    SourceQuery,
    SourceReview,
    SourcesDriver,
    TrendItem,
)


def _mock_route(driver: SourcesDriver, item: SourceItem) -> bool:
    """Dữ liệu giả lập (ảnh giữ chỗ placehold.co…): không lọc theo máy chủ ảnh của sàn."""
    if driver.name == "mock":
        return True
    if driver.name != "routed":
        return False
    from app.integrations import source_config

    return source_config.route(item.platform) == "mock"


def normalize(item: SourceItem, *, images: bool = True) -> SourceItem:
    p = sp.detect(item.url)
    pid, _ = sp.extract_id(item.url, p)
    update: dict[str, Any] = {"url": sp.canonical(item.url, p)}
    if pid:
        update["external_id"] = pid[:120]
    if item.platform in (SourcePlatform.WEB, SourcePlatform.OTHER) and p.platform != sp.GENERIC:
        update["platform"] = SourcePlatform(p.platform)
    if not images:
        return item.model_copy(update=update)
    if item.image_url:
        imgs = sp.clean_images([item.image_url], p)
        update["image_url"] = imgs[0] if imgs else None
    if isinstance(item, SourceProduct):
        imgs = sp.clean_images([*item.images, *([item.image_url] if item.image_url else [])], p)
        update["images"] = imgs
        update["image_url"] = imgs[0] if imgs else None
    return item.model_copy(update=update)


class Profiled(SourcesDriver):
    def __init__(self, inner: SourcesDriver) -> None:
        self.inner = inner
        self.name = inner.name

    def __getattr__(self, attr: str) -> Any:  # tiện ích riêng của driver (vd mock) vẫn gọi được
        return getattr(self.inner, attr)

    def _norm(self, item: SourceItem) -> SourceItem:
        return normalize(item, images=not _mock_route(self.inner, item))

    async def search(self, query: SourceQuery) -> list[SourceItem]:
        return [self._norm(i) for i in await self.inner.search(query)]

    async def fetch_product(self, url: str) -> SourceProduct:
        p = await self.inner.fetch_product(sp.canonical(url))
        out = self._norm(p)
        assert isinstance(out, SourceProduct)
        return out

    async def search_by_image(
        self, image: bytes | str, *, platforms: list[SourcePlatform] | None = None, limit: int = 20
    ) -> list[SourceItem]:
        return [self._norm(i) for i in await self.inner.search_by_image(image, platforms=platforms, limit=limit)]

    async def fetch_reviews(self, url: str, *, limit: int = 200) -> list[SourceReview]:
        return await self.inner.fetch_reviews(sp.canonical(url), limit=limit)

    async def trends(self, platforms: list[SourcePlatform] | None = None, *, limit: int = 10) -> list[TrendItem]:
        return await self.inner.trends(platforms, limit=limit)

    async def market_prices(self, query: str, *, limit: int = 10) -> list[MarketListing]:
        return await self.inner.market_prices(query, limit=limit)


def wrap(driver: SourcesDriver) -> SourcesDriver:
    """Một lớp bọc cho mỗi driver (giữ nguyên đối tượng để test monkeypatch được)."""
    if isinstance(driver, Profiled):
        return driver
    w = getattr(driver, "_profiled", None)
    if w is None:
        w = Profiled(driver)
        driver._profiled = w  # type: ignore[attr-defined]
    return w
