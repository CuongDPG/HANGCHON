"""Nguồn hàng giả: sinh ứng viên, hồ sơ, đánh giá, xu hướng, giá VN xác định theo đầu vào."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlparse

from app.core.enums import Language, SourcePlatform
from app.integrations._mockutil import placeholder_image, rng, short_id
from app.integrations.sources import (
    MarketListing,
    SourceItem,
    SourceProduct,
    SourceQuery,
    SourceReview,
    SourcesDriver,
    TrendItem,
)

_CURRENCY = {
    SourcePlatform.ALIBABA_1688: ("CNY", Language.ZH),
    SourcePlatform.TAOBAO: ("CNY", Language.ZH),
    SourcePlatform.TMALL: ("CNY", Language.ZH),
    SourcePlatform.RAKUTEN: ("JPY", Language.JA),
    SourcePlatform.AMAZON_JP: ("JPY", Language.JA),
}
_NOUNS_ZH = ["保温杯", "收纳盒", "硅胶刷", "沥水架", "折叠衣架", "密封罐", "厨房剪刀", "防滑垫"]
_NOUNS_JA = ["保温ボトル", "収納ケース", "シリコンブラシ", "水切りラック", "折りたたみハンガー", "保存容器"]
_NOUNS_VI = ["Bình giữ nhiệt", "Hộp đựng đồ", "Cọ silicon", "Giá úp bát", "Móc phơi gấp", "Hũ kín hơi", "Kéo bếp"]
_PRAISE = ["Chắc tay, dùng thích", "Đóng gói cẩn thận", "Đúng như mô tả", "Rửa dễ", "Giá hợp lý"]
_COMPLAIN = ["Nắp hơi lỏng", "Có mùi nhựa lúc đầu", "Màu nhạt hơn ảnh", "Giao chậm", "Hơi nhỏ"]


# Giá bán lẻ thường gặp ở Việt Nam theo loại hàng (giả lập, VND): giá VN cùng thang với giá vốn về tay của hàng
# nhập, để biên dự kiến hợp lý. Khớp cụm cụ thể trước cụm chung; không khớp thì lấy giá ngẫu nhiên theo từ khoá.
_VN_RETAIL: list[tuple[str, int]] = [
    ("nhật", 800_000), ("lan can", 1_200_000), ("thuỷ tinh", 230_000), ("in hình", 95_000), ("nhựa", 150_000),
    ("mini", 170_000), ("trẻ em", 190_000), ("ống hút", 150_000), ("văn phòng", 150_000), ("cốc", 150_000),
    ("bình giữ nhiệt", 300_000), ("hộp cơm tròn", 220_000), ("hộp cơm", 320_000), ("kẹp phơi", 110_000),
    ("móc phơi", 160_000), ("cây phơi", 480_000), ("dây phơi", 120_000), ("giày", 130_000), ("giá phơi", 330_000),
    ("áo choàng", 290_000), ("khăn tắm", 250_000), ("khăn mặt", 170_000), ("pin sạc", 240_000), ("đèn", 230_000),
    ("móc dán", 110_000), ("kệ", 210_000), ("thảm", 160_000),
]  # fmt: skip


def _market_base(query: str) -> int | None:
    q = query.lower().replace("thủy", "thuỷ")
    return next((price for key, price in _VN_RETAIL if key in q), None)


def _platform_of(url: str) -> SourcePlatform:
    host = urlparse(url).netloc.lower()
    for key, p in (
        ("1688", SourcePlatform.ALIBABA_1688),
        ("taobao", SourcePlatform.TAOBAO),
        ("tmall", SourcePlatform.TMALL),
        ("rakuten", SourcePlatform.RAKUTEN),
        ("amazon.co.jp", SourcePlatform.AMAZON_JP),
        ("shopee", SourcePlatform.SHOPEE_VN),
        ("tiktok", SourcePlatform.TIKTOK_SHOP_VN),
    ):
        if key in host or f"/{key}/" in url:
            return p
    return SourcePlatform.WEB


def _item(platform: SourcePlatform, seed: str, n: int) -> SourceItem:
    r = rng(platform, seed, n)
    currency, lang = _CURRENCY.get(platform, ("CNY", Language.ZH))
    noun = r.choice(_NOUNS_JA if lang == Language.JA else _NOUNS_ZH)
    price = Decimal(r.randint(800, 6000) if currency == "JPY" else r.randint(8, 89)) + Decimal("0.00")
    ext = short_id(platform, seed, n)
    return SourceItem(
        platform=platform,
        external_id=ext,
        url=f"https://mock.hangchon.local/{platform.value}/item/{ext}",
        title=f"{noun} {seed[:12]} #{n + 1}",
        language=lang,
        price_amount=price,
        currency=currency,
        image_url=placeholder_image(ext),
        seller_name=f"Cửa hàng mẫu {short_id(platform, seed, n % 3, length=4)}",
        seller_url=f"https://mock.hangchon.local/{platform.value}/shop/{short_id(seed, n % 3, length=6)}",
        rating=round(r.uniform(4.0, 5.0), 1),
        review_count=r.randint(20, 3000),
        sales_count=r.randint(100, 50000),
    )


class Driver(SourcesDriver):
    name = "mock"

    async def search(self, query: SourceQuery) -> list[SourceItem]:
        platforms = query.platforms or [SourcePlatform.ALIBABA_1688, SourcePlatform.TAOBAO, SourcePlatform.RAKUTEN]
        seed = " ".join(query.keywords) or "hang"
        items = [_item(p, seed, i) for p in platforms for i in range(max(1, query.limit // len(platforms)))]
        if query.price_max is not None:
            items = [i for i in items if i.price_amount <= query.price_max]
        if query.price_min is not None:
            items = [i for i in items if i.price_amount >= query.price_min]
        return items[: query.limit]

    async def fetch_product(self, url: str) -> SourceProduct:
        platform = _platform_of(url)
        base = _item(platform, url, 0)
        r = rng("product", url)
        return SourceProduct(
            **base.model_dump(exclude={"url"}),
            url=url,
            description="Mô tả gốc (giả lập) của sản phẩm.",
            images=[placeholder_image(url, i) for i in range(4)],
            specs={
                "Chất liệu": r.choice(["Inox 304", "Silicon", "Nhựa PP", "Tre"]),
                "Dung tích": f"{r.randint(3, 10)}00ml",
            },
            variants=[{"Màu": c} for c in r.sample(["Trắng", "Xám", "Xanh chàm", "Be"], 2)],
            moq=r.choice([1, 2, 10, 50]),
            weight_grams=r.randint(80, 900),
            reviews=await self.fetch_reviews(url, limit=10),
        )

    async def search_by_image(
        self, image: bytes | str, *, platforms: list[SourcePlatform] | None = None, limit: int = 20
    ) -> list[SourceItem]:
        seed = image if isinstance(image, str) else short_id(image[:256], len(image))
        platforms = platforms or [SourcePlatform.ALIBABA_1688, SourcePlatform.TAOBAO]
        return [_item(p, f"img-{seed}", i) for p in platforms for i in range(3)][:limit]

    async def fetch_reviews(self, url: str, *, limit: int = 200) -> list[SourceReview]:
        r = rng("reviews", url)
        lang = _CURRENCY.get(_platform_of(url), ("CNY", Language.ZH))[1]
        out = []
        for i in range(min(limit, 30)):
            rating = r.choices([5, 4, 3, 2, 1], weights=[55, 25, 10, 6, 4])[0]
            body = r.choice(_PRAISE if rating >= 4 else _COMPLAIN)
            out.append(
                SourceReview(
                    external_id=short_id(url, i),
                    rating=rating,
                    body=f"[{lang.value}] {body}",
                    language=lang,
                    author=f"Người mua {i + 1}",
                    created_on=date(2026, 11, 1) - timedelta(days=i * 3),
                    photos=[placeholder_image(url, 100 + i)] if i % 5 == 0 else [],
                )
            )
        return out

    async def trends(self, platforms: list[SourcePlatform] | None = None, *, limit: int = 10) -> list[TrendItem]:
        platforms = platforms or [SourcePlatform.XIAOHONGSHU, SourcePlatform.COSME, SourcePlatform.TIKTOK_SHOP_VN]
        out = []
        for i in range(limit):
            p = platforms[i % len(platforms)]
            r = rng("trend", p, i)
            out.append(
                TrendItem(
                    platform=p,
                    title=r.choice(_NOUNS_VI) + " kiểu mới",
                    url=f"https://mock.hangchon.local/{p.value}/trend/{short_id(p, i)}",
                    image_url=placeholder_image(f"trend{p}{i}"),
                    language=Language.JA if p == SourcePlatform.COSME else Language.ZH,
                    metrics={"mentions": r.randint(200, 9000), "growth_pct": round(r.uniform(10, 300), 1)},
                    snippet="Nhiều bài review tuần này (giả lập).",
                )
            )
        return out

    async def market_prices(self, query: str, *, limit: int = 10) -> list[MarketListing]:
        r = rng("market", query)
        base = _market_base(query) or r.randint(8, 40) * 10_000
        out = []
        for i in range(min(limit, 6)):
            p = SourcePlatform.SHOPEE_VN if i % 2 == 0 else SourcePlatform.TIKTOK_SHOP_VN
            price = (round(base * r.uniform(0.85, 1.35) / 10_000) * 10_000 - 1_000) if base >= 50_000 else base
            out.append(
                MarketListing(
                    platform=p,
                    title=f"{query} (shop {i + 1})",
                    url=f"https://mock.hangchon.local/{p.value}/{short_id(query, i)}",
                    shop_name=f"Shop mẫu {i + 1}",
                    price_vnd=max(price, 10_000),
                    original_price_vnd=price + 30_000,
                    sold_count=r.randint(0, 5000),
                    rating=round(r.uniform(4.2, 5.0), 1),
                )
            )
        return out
