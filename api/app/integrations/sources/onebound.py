"""Driver `onebound`: 1688 / Taobao qua API bên thứ ba OneBound (api-gw.onebound.cn).

Bật ở *Cài đặt → Nguồn hàng* (thẻ OneBound + chọn «Qua OneBound» cho 1688/Taobao/Tmall) hoặc `SOURCES_DRIVER=onebound`.
Khoá: `source_config.value("onebound", "api_key" | "api_secret")` — Cài đặt thắng `ONEBOUND_API_KEY` /
`ONEBOUND_API_SECRET`.

**CHƯA THỬ VỚI KHOÁ THẬT.** Viết theo tài liệu công khai của OneBound: mỗi API là
`GET https://api-gw.onebound.cn/<api_type>/<api_name>/?key=..&secret=..&<tham số>` với `api_type` = `taobao` | `1688`,
`api_name` = `item_search` (q, page, start_price, end_price) · `item_get` (num_iid) · `item_review` (num_iid, page) ·
`item_search_img` (imgid = URL ảnh) · `upload_img` (POST imgcode = base64). Kết quả có `error_code` ("0000" = ổn) và
`reason`. Tên trường có thể khác giữa các bản API — kiểm lại khi có khoá.

OneBound không có radar xu hướng và giá sàn Việt Nam: hai việc này chuyển sang driver `web`.
"""

from __future__ import annotations

import base64
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

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

BASE_URL = "https://api-gw.onebound.cn"
CHECK_ITEM_ID = "520813250866"  # món ví dụ trong tài liệu OneBound
API_TYPE = {
    SourcePlatform.TAOBAO: "taobao",
    SourcePlatform.TMALL: "taobao",
    SourcePlatform.ALIBABA_1688: "1688",
}


def _dec(v: Any) -> Decimal:
    try:
        return Decimal(str(v).split("-")[0].strip() or "0")
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _int(v: Any) -> int | None:
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else None


def _grams(kg: Any) -> int | None:
    """`item_weight` của OneBound tính bằng kg (vd "0.5")."""
    try:
        v = float(str(kg).strip())
    except (TypeError, ValueError):
        return None
    return int(v * 1000) if v > 0 else None


def _https(u: str | None) -> str | None:
    if not u:
        return None
    return "https:" + u if u.startswith("//") else u


def item_ref(url: str) -> tuple[SourcePlatform, str]:
    """Rút (nền tảng, mã sản phẩm) từ link Taobao/Tmall/1688."""
    p = urlparse(url)
    host = p.netloc.lower()
    if "1688.com" in host:
        m = re.search(r"/offer/(\d+)", p.path)
        if m:
            return SourcePlatform.ALIBABA_1688, m.group(1)
    if "taobao.com" in host or "tmall.com" in host:
        ids = parse_qs(p.query).get("id")
        if ids and ids[0].isdigit():
            return (SourcePlatform.TMALL if "tmall" in host else SourcePlatform.TAOBAO), ids[0]
    raise IntegrationError("OneBound chỉ đọc được link Taobao, Tmall, 1688 (có mã sản phẩm trong link).")


class Driver(SourcesDriver):
    name = "onebound"

    def __init__(self, client: httpx.AsyncClient | None = None, creds: dict[str, str] | None = None) -> None:
        self._client = client
        self._override = creds or {}  # «Kiểm tra kết nối» với khoá đang nhập, chưa lưu

    def _creds(self) -> tuple[str, str]:
        key = self._override.get("api_key") or source_config.value("onebound", "api_key")
        secret = self._override.get("api_secret") or source_config.value("onebound", "api_secret")
        if not key or not secret:
            raise IntegrationNotConfigured(
                "Chưa có API key / API secret của OneBound: chị nhập ở Cài đặt → Nguồn hàng."
            )
        return key, secret

    async def check(self) -> str:
        """Gọi thử một lần `item_get` (món mẫu trong tài liệu OneBound, có bộ nhớ đệm phía họ). Tốn 1 lần gọi."""
        data = await self._call("taobao", "item_get", num_iid=CHECK_ITEM_ID)
        title = str((data.get("item") or {}).get("title") or "").strip()
        return "Đã nối OneBound" + (f": đọc thử được «{title[:60]}»." if title else ".")

    async def _call(self, api_type: str, api_name: str, *, method: str = "GET", **params: Any) -> dict[str, Any]:
        key, secret = self._creds()
        url = f"{BASE_URL}/{api_type}/{api_name}/"
        query = {"key": key, "secret": secret, "lang": "zh-CN", **{k: v for k, v in params.items() if v is not None}}
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            if method == "POST":
                resp = await client.post(url, params={"key": key, "secret": secret}, data=query)
            else:
                resp = await client.get(url, params=query)
        except httpx.HTTPError as e:
            raise IntegrationError("Không kết nối được OneBound, chị thử lại sau.") from e
        finally:
            if self._client is None:
                await client.aclose()
        if resp.status_code >= 400:
            raise IntegrationError(f"OneBound báo lỗi HTTP {resp.status_code}.")
        try:
            data = resp.json()
        except ValueError as e:
            raise IntegrationError("OneBound trả dữ liệu không đọc được.") from e
        code = str(data.get("error_code", "0000"))
        if code not in ("0000", "0", ""):
            raise IntegrationError(f"OneBound: {data.get('reason') or data.get('error') or code}")
        return data

    def _items(self, data: dict[str, Any], platform: SourcePlatform) -> list[SourceItem]:
        raw = (data.get("items") or {}).get("item") or []
        out = []
        for it in raw:
            iid = str(it.get("num_iid") or "")
            if not iid:
                continue
            url = _https(it.get("detail_url")) or (
                f"https://detail.1688.com/offer/{iid}.html"
                if platform == SourcePlatform.ALIBABA_1688
                else f"https://item.taobao.com/item.htm?id={iid}"
            )
            out.append(
                SourceItem(
                    platform=platform,
                    external_id=iid,
                    url=url,
                    title=str(it.get("title") or ""),
                    language=Language.ZH,
                    price_amount=_dec(it.get("promotion_price") or it.get("price")),
                    currency="CNY",
                    image_url=_https(it.get("pic_url")),
                    seller_name=it.get("seller_nick") or it.get("nick"),
                    sales_count=_int(it.get("sales")),
                )
            )
        return out

    async def search(self, query: SourceQuery) -> list[SourceItem]:
        platforms = [
            p for p in (query.platforms or [SourcePlatform.ALIBABA_1688, SourcePlatform.TAOBAO]) if p in API_TYPE
        ]
        out: list[SourceItem] = []
        for p in platforms:
            data = await self._call(
                API_TYPE[p],
                "item_search",
                q=" ".join(query.keywords),
                page=1,
                start_price=str(query.price_min) if query.price_min is not None else None,
                end_price=str(query.price_max) if query.price_max is not None else None,
            )
            out += self._items(data, p)
        return out[: query.limit]

    async def fetch_product(self, url: str) -> SourceProduct:
        platform, iid = item_ref(url)
        data = await self._call(API_TYPE[platform], "item_get", num_iid=iid)
        it = data.get("item") or {}
        specs = {str(p.get("name")): str(p.get("value")) for p in it.get("props") or [] if p.get("name")}
        skus = ((it.get("skus") or {}).get("sku")) or []
        variants = [{"name": str(s.get("properties_name") or s.get("properties") or "")} for s in skus[:20]]
        reviews = await self.fetch_reviews(url, limit=30)
        return SourceProduct(
            platform=platform,
            external_id=iid,
            url=url,
            title=str(it.get("title") or ""),
            language=Language.ZH,
            price_amount=_dec(it.get("price")),
            currency="CNY",
            image_url=_https(it.get("pic_url")),
            seller_name=it.get("nick") or (it.get("seller_info") or {}).get("nick"),
            sales_count=_int(it.get("total_sold") or it.get("sales")),
            description=it.get("desc_short") or None,
            images=[u for u in (_https(i.get("url")) for i in it.get("item_imgs") or []) if u],
            specs=specs,
            variants=variants,
            moq=_int(it.get("min_num")),
            weight_grams=_grams(it.get("item_weight")),
            reviews=reviews,
        )

    async def search_by_image(
        self, image: bytes | str, *, platforms: list[SourcePlatform] | None = None, limit: int = 20
    ) -> list[SourceItem]:
        platforms = [p for p in (platforms or [SourcePlatform.ALIBABA_1688, SourcePlatform.TAOBAO]) if p in API_TYPE]
        out: list[SourceItem] = []
        for p in platforms:
            imgid = image
            if isinstance(image, bytes):
                up = await self._call(
                    API_TYPE[p], "upload_img", method="POST", imgcode=base64.b64encode(image).decode()
                )
                imgid = (up.get("items") or {}).get("url") or up.get("url")
                if not imgid:
                    raise IntegrationError("OneBound không nhận ảnh tải lên.")
            data = await self._call(API_TYPE[p], "item_search_img", imgid=imgid)
            out += self._items(data, p)
        return out[:limit]

    async def fetch_reviews(self, url: str, *, limit: int = 200) -> list[SourceReview]:
        platform, iid = item_ref(url)
        try:
            data = await self._call(API_TYPE[platform], "item_review", num_iid=iid, page=1)
        except IntegrationError:
            return []  # nhiều gói API không có item_review: hồ sơ vẫn chạy, chỉ thiếu đánh giá
        out = []
        for i, r in enumerate(((data.get("items") or {}).get("item") or [])[:limit]):
            try:
                day = date.fromisoformat(str(r.get("rate_date", ""))[:10])
            except ValueError:
                day = None
            out.append(
                SourceReview(
                    external_id=str(r.get("rate_id") or f"{iid}-{i}"),
                    rating=int(r.get("rate_star") or 5),
                    body=str(r.get("rate_content") or ""),
                    language=Language.ZH,
                    author=r.get("display_user_nick"),
                    created_on=day,
                    photos=[u for u in (_https(p) for p in r.get("pics") or []) if u],
                    variant=r.get("auction_sku"),
                )
            )
        return out

    async def trends(self, platforms: list[SourcePlatform] | None = None, *, limit: int = 10) -> list[TrendItem]:
        return await get_driver("sources", "web").trends(platforms, limit=limit)

    async def market_prices(self, query: str, *, limit: int = 10) -> list[MarketListing]:
        return await get_driver("sources", "web").market_prices(query, limit=limit)
