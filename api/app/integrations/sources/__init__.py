"""Nguồn hàng: tìm theo từ khoá (đã dịch), lấy hồ sơ từ link, tìm bằng ảnh, đọc đánh giá, xu hướng, giá thị trường VN.

Driver: `mock` (mặc định), `web` (AI + web search/fetch), `onebound` (1688/Taobao, cần ONEBOUND_API_KEY)."""

from __future__ import annotations

import abc
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.enums import Language, SourcePlatform


class SourceQuery(BaseModel):
    keywords: list[str] = Field(description="Từ khoá đã dịch đúng ngôn ngữ của nguồn")
    platforms: list[SourcePlatform] = Field(default_factory=list)
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    currency: str | None = None
    limit: int = 20


class SourceItem(BaseModel):
    platform: SourcePlatform
    external_id: str
    url: str
    title: str
    language: Language = Language.ZH
    price_amount: Decimal
    currency: str
    image_url: str | None = None
    seller_name: str | None = None
    seller_url: str | None = None
    rating: float | None = None
    review_count: int | None = None
    sales_count: int | None = None


class SourceReview(BaseModel):
    external_id: str
    rating: int
    body: str
    language: Language
    author: str | None = None
    created_on: date | None = None
    photos: list[str] = Field(default_factory=list)
    variant: str | None = None


class SourceProduct(SourceItem):
    description: str | None = None
    images: list[str] = Field(default_factory=list)
    specs: dict[str, str] = Field(default_factory=dict)
    variants: list[dict[str, str]] = Field(default_factory=list)
    moq: int | None = None
    weight_grams: int | None = None
    reviews: list[SourceReview] = Field(default_factory=list)


class TrendItem(BaseModel):
    platform: SourcePlatform
    title: str
    url: str
    image_url: str | None = None
    language: Language
    metrics: dict[str, float] = Field(default_factory=dict, description="mentions, growth_pct, rank...")
    snippet: str | None = None


class MarketListing(BaseModel):
    """Giá cùng món trên sàn Việt Nam (b5)."""

    platform: SourcePlatform
    title: str
    url: str
    shop_name: str | None = None
    price_vnd: int
    original_price_vnd: int | None = None
    sold_count: int | None = None
    rating: float | None = None


class SourcesDriver(abc.ABC):
    name: str

    @abc.abstractmethod
    async def search(self, query: SourceQuery) -> list[SourceItem]: ...

    @abc.abstractmethod
    async def fetch_product(self, url: str) -> SourceProduct: ...

    @abc.abstractmethod
    async def search_by_image(
        self, image: bytes | str, *, platforms: list[SourcePlatform] | None = None, limit: int = 20
    ) -> list[SourceItem]:
        """`image` là bytes ảnh hoặc URL ảnh."""

    @abc.abstractmethod
    async def fetch_reviews(self, url: str, *, limit: int = 200) -> list[SourceReview]: ...

    @abc.abstractmethod
    async def trends(self, platforms: list[SourcePlatform] | None = None, *, limit: int = 10) -> list[TrendItem]: ...

    @abc.abstractmethod
    async def market_prices(self, query: str, *, limit: int = 10) -> list[MarketListing]: ...
