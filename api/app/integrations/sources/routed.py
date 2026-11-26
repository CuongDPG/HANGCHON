"""Driver `routed`: mỗi sàn đi đường chị chọn ở *Cài đặt → Nguồn hàng* (`source_config.route`).

Tự bật khi chị đã chọn cách lấy hàng cho ít nhất một sàn (`integrations.base.driver_name`); không có thì hệ thống
dùng thẳng `SOURCES_DRIVER` như trước. Việc không gắn với sàn (xu hướng, giá sàn Việt Nam, link trang lạ) đi
`source_config.general()`.
"""

from __future__ import annotations

from app.core.enums import SourcePlatform
from app.integrations import source_config
from app.integrations.base import get_driver
from app.integrations.sources import (
    MarketListing,
    SourceItem,
    SourceProduct,
    SourceQuery,
    SourceReview,
    SourcesDriver,
    TrendItem,
)
from app.integrations.sources.web import platform_of

DEFAULT_SEARCH = [SourcePlatform.ALIBABA_1688, SourcePlatform.TAOBAO, SourcePlatform.RAKUTEN]


def _driver(name: str) -> SourcesDriver:
    return get_driver("sources", name)


def _group(platforms: list[SourcePlatform]) -> dict[str, list[SourcePlatform]]:
    out: dict[str, list[SourcePlatform]] = {}
    for p in platforms:
        out.setdefault(source_config.route(p), []).append(p)
    return out


def _for_url(url: str) -> SourcesDriver:
    p = platform_of(url)
    return _driver(source_config.route(p) if p in source_config.PLATFORMS else source_config.general())


class Driver(SourcesDriver):
    name = "routed"

    async def search(self, query: SourceQuery) -> list[SourceItem]:
        out: list[SourceItem] = []
        for name, ps in _group(query.platforms or DEFAULT_SEARCH).items():
            out += await _driver(name).search(query.model_copy(update={"platforms": ps}))
        return out[: query.limit]

    async def fetch_product(self, url: str) -> SourceProduct:
        return await _for_url(url).fetch_product(url)

    async def search_by_image(
        self, image: bytes | str, *, platforms: list[SourcePlatform] | None = None, limit: int = 20
    ) -> list[SourceItem]:
        out: list[SourceItem] = []
        for name, ps in _group(platforms or DEFAULT_SEARCH[:2]).items():
            out += await _driver(name).search_by_image(image, platforms=ps, limit=limit)
        return out[:limit]

    async def fetch_reviews(self, url: str, *, limit: int = 200) -> list[SourceReview]:
        return await _for_url(url).fetch_reviews(url, limit=limit)

    async def trends(self, platforms: list[SourcePlatform] | None = None, *, limit: int = 10) -> list[TrendItem]:
        return await _driver(source_config.general()).trends(platforms, limit=limit)

    async def market_prices(self, query: str, *, limit: int = 10) -> list[MarketListing]:
        return await _driver(source_config.general()).market_prices(query, limit=limit)
