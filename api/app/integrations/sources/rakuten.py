"""Driver `rakuten`: Rakuten Ichiba qua Rakuten Web Service (Ichiba Item Search API, miễn phí).

Bật ở *Cài đặt → Nguồn hàng* (thẻ Rakuten Web Service + chọn «Qua Rakuten API» ở thẻ Rakuten).
Khoá: `source_config.value("rakuten", "application_id" | "access_key" | "referer")`, Cài đặt thắng
`RAKUTEN_APPLICATION_ID` / `RAKUTEN_ACCESS_KEY`.

**CHƯA THỬ VỚI KHOÁ THẬT.** Ngày 26/11/2026 trang tài liệu chính thức (webservice.rakuten.co.jp/documentation)
trả lỗi 503, nên điểm cuối và tham số dưới đây lấy từ các bài viết kỹ thuật về đợt chuyển API năm 2026 (xem
docs/source-accounts.md): `GET https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601` với
`applicationId` (UUID) + `accessKey` (`pk_…`, gửi cả ở header `accessKey` lẫn tham số), `keyword`, `itemCode`,
`hits` (≤ 30), `page`, `minPrice`, `maxPrice` (yên), `sort=standard`, `imageFlag=1`, `format=json`,
`formatVersion=2` (mỗi món là object phẳng trong `Items`). Rakuten kiểm tên miền gọi: gửi `Referer` + `Origin`
bằng địa chỉ đã khai khi tạo ứng dụng. Lỗi: `{"error", "error_description"}` (400 thiếu/sai tham số, 403 sai khoá
hoặc tên miền, 429 gọi quá nhanh).

Tìm bằng ảnh, đánh giá, xu hướng, giá sàn Việt Nam: chuyển sang driver `web`.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

import httpx

from app.ai.errors import AIError
from app.core.config import settings
from app.core.enums import Language, SourcePlatform
from app.integrations import source_config
from app.integrations.base import IntegrationError, IntegrationNotConfigured, get_driver
from app.integrations.sources import (
    MarketListing,
    SourceItem,
    SourceProduct,
    SourceQuery,
    SourceReview,
    SourcesDriver,
    TrendItem,
)

SEARCH_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"
CHECK_KEYWORD = "タンブラー"  # bình giữ nhiệt — chỉ để tìm thử 1 món


def item_code(url: str) -> str:
    """`https://item.rakuten.co.jp/<shop>/<item>/` → `<shop>:<item>` (mã món của Ichiba)."""
    p = urlparse(url)
    if p.netloc.lower() == "item.rakuten.co.jp":
        parts = [x for x in p.path.split("/") if x]
        if len(parts) >= 2:
            return f"{parts[0]}:{parts[1]}"
    raise IntegrationError("Rakuten API chỉ đọc được link món dạng item.rakuten.co.jp/<cửa hàng>/<món>/.")


def _img(v: Any) -> str | None:
    u = v.get("imageUrl") if isinstance(v, dict) else v
    if not u:
        return None
    return re.sub(r"\?_ex=\d+x\d+$", "", str(u))  # bỏ cỡ thu nhỏ 128x128 → ảnh gốc


def _flat(data: dict[str, Any]) -> list[dict[str, Any]]:
    """formatVersion=2 trả object phẳng; formatVersion=1 bọc trong {"Item": …}."""
    return [x.get("Item", x) if isinstance(x, dict) else {} for x in data.get("Items") or []]


class Driver(SourcesDriver):
    name = "rakuten"

    def __init__(self, client: httpx.AsyncClient | None = None, creds: dict[str, str] | None = None) -> None:
        self._client = client
        self._override = creds or {}

    def _val(self, key: str) -> str | None:
        return self._override.get(key) or source_config.value("rakuten", key)

    async def _call(self, **params: Any) -> dict[str, Any]:
        app_id, access_key = self._val("application_id"), self._val("access_key")
        if not app_id or not access_key:
            raise IntegrationNotConfigured(
                "Chưa có Application ID / Access key của Rakuten: chị nhập ở Cài đặt → Nguồn hàng."
            )
        referer = (self._val("referer") or settings.web_base_url).rstrip("/") + "/"
        query = {
            "applicationId": app_id,
            "accessKey": access_key,
            "format": "json",
            "formatVersion": 2,
            "imageFlag": 1,
            **{k: v for k, v in params.items() if v is not None},
        }
        headers = {"accessKey": access_key, "Referer": referer, "Origin": referer.rstrip("/")}
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            resp = await client.get(SEARCH_URL, params=query, headers=headers)
        except httpx.HTTPError as e:
            raise IntegrationError("Không kết nối được Rakuten, chị thử lại sau.") from e
        finally:
            if self._client is None:
                await client.aclose()
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
            why = (data.get("error_description") or data.get("error")) if isinstance(data, dict) else None
            hint = {
                403: " Kiểm tra lại Access key và tên miền đã khai cho ứng dụng.",
                429: " Gọi quá nhanh, chị thử lại sau ít phút.",
            }.get(resp.status_code, "")
            raise IntegrationError(f"Rakuten báo lỗi {resp.status_code}: {why or 'không rõ lý do'}.{hint}")
        return data if isinstance(data, dict) else {}

    def _item(self, it: dict[str, Any]) -> SourceItem:
        images = [u for u in (_img(x) for x in it.get("mediumImageUrls") or []) if u]
        return SourceItem(
            platform=SourcePlatform.RAKUTEN,
            external_id=str(it.get("itemCode") or ""),
            url=str(it.get("itemUrl") or ""),
            title=str(it.get("itemName") or ""),
            language=Language.JA,
            price_amount=Decimal(str(it.get("itemPrice") or 0)),
            currency="JPY",
            image_url=images[0] if images else None,
            seller_name=it.get("shopName"),
            seller_url=it.get("shopUrl"),
            rating=float(it["reviewAverage"]) if it.get("reviewAverage") else None,
            review_count=int(it["reviewCount"]) if it.get("reviewCount") is not None else None,
        )

    async def check(self) -> str:
        data = await self._call(keyword=CHECK_KEYWORD, hits=1)
        items = _flat(data)
        name = str(items[0].get("itemName") or "")[:60] if items else ""
        return "Đã nối Rakuten" + (f": tìm thử được «{name}»." if name else ".")

    async def search(self, query: SourceQuery) -> list[SourceItem]:
        if query.platforms and SourcePlatform.RAKUTEN not in query.platforms:
            return []
        data = await self._call(
            keyword=" ".join(query.keywords)[:128],
            hits=max(1, min(30, query.limit)),
            page=1,
            sort="standard",
            minPrice=int(query.price_min) if query.price_min is not None else None,
            maxPrice=int(query.price_max) if query.price_max is not None else None,
        )
        return [self._item(it) for it in _flat(data) if it.get("itemCode")][: query.limit]

    async def fetch_product(self, url: str) -> SourceProduct:
        data = await self._call(itemCode=item_code(url), hits=1)
        items = _flat(data)
        if not items:
            raise IntegrationError("Rakuten không tìm thấy món này (có thể đã ngừng bán).")
        it = items[0]
        base = self._item(it)
        return SourceProduct(
            **base.model_dump(),
            description=it.get("itemCaption") or None,
            images=[u for u in (_img(x) for x in it.get("mediumImageUrls") or []) if u],
            reviews=await self.fetch_reviews(url, limit=30),
        )

    async def search_by_image(
        self, image: bytes | str, *, platforms: list[SourcePlatform] | None = None, limit: int = 20
    ) -> list[SourceItem]:
        return await get_driver("sources", "web").search_by_image(image, platforms=platforms, limit=limit)

    async def fetch_reviews(self, url: str, *, limit: int = 200) -> list[SourceReview]:
        try:
            return await get_driver("sources", "web").fetch_reviews(url, limit=limit)
        except (IntegrationError, AIError):
            return []  # đánh giá đọc qua web, lỗi thì hồ sơ vẫn chạy

    async def trends(self, platforms: list[SourcePlatform] | None = None, *, limit: int = 10) -> list[TrendItem]:
        return await get_driver("sources", "web").trends(platforms, limit=limit)

    async def market_prices(self, query: str, *, limit: int = 10) -> list[MarketListing]:
        return await get_driver("sources", "web").market_prices(query, limit=limit)
