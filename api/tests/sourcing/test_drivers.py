"""Driver thật của tích hợp sources: `web` (AI + web search/fetch, chạy bằng AI giả) và `onebound` (HTTP giả lập)."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.config import settings
from app.core.enums import SourcePlatform
from app.integrations import IntegrationError, IntegrationNotConfigured, get_driver
from app.integrations.sources import SourceQuery
from app.integrations.sources.onebound import BASE_URL, item_ref
from app.integrations.sources.onebound import Driver as OneBound


async def test_web_driver_with_fake_ai():
    d = get_driver("sources", "web")
    items = await d.search(SourceQuery(keywords=["折叠晾衣架"], platforms=[SourcePlatform.TAOBAO], limit=6))
    assert items and all(i.platform == SourcePlatform.TAOBAO and i.url.startswith("http") for i in items)
    p = await d.fetch_product("https://item.taobao.com/item.htm?id=123456")
    assert p.url.endswith("123456") and p.specs and p.reviews
    assert await d.fetch_reviews("https://item.taobao.com/item.htm?id=123456")
    assert await d.trends(limit=4)
    m = await d.market_prices("giá phơi gấp gọn", limit=4)
    assert m and all(x.price_vnd > 0 for x in m)
    assert await d.search_by_image(b"\x89PNG....", limit=3)


async def test_web_driver_unreadable_page(fake_ai):
    fake_ai["sources.web_fetch_product"] = lambda inp: {
        "platform": "web", "url": inp.url, "title": "?", "price_amount": 0, "currency": "USD",
        "readable": False, "note": "Trang yêu cầu đăng nhập.",
    }  # fmt: skip
    with pytest.raises(IntegrationError, match="đăng nhập"):
        await get_driver("sources", "web").fetch_product("https://example.com/p/1")


async def test_web_driver_used_by_link_import(owner_client, monkeypatch):
    monkeypatch.setattr(settings, "sources_driver", "web")
    r = await owner_client.post(
        "/api/desk/sourcing/import-link", json={"url": "https://detail.1688.com/offer/6112233.html"}
    )
    assert r.json()["status"] == "succeeded", r.json()


def test_item_ref():
    assert item_ref("https://item.taobao.com/item.htm?spm=a&id=681234567890") == (SourcePlatform.TAOBAO, "681234567890")
    assert item_ref("https://detail.tmall.com/item.htm?id=55") == (SourcePlatform.TMALL, "55")
    assert item_ref("https://detail.1688.com/offer/6112233.html") == (SourcePlatform.ALIBABA_1688, "6112233")
    with pytest.raises(IntegrationError):
        item_ref("https://www.rakuten.co.jp/shop/item/1")


async def test_onebound_requires_keys(monkeypatch):
    monkeypatch.setattr(settings, "onebound_api_key", None)
    with pytest.raises(IntegrationNotConfigured):
        await OneBound().search(SourceQuery(keywords=["晾衣架"]))


@respx.mock
async def test_onebound_maps_search_and_product(monkeypatch):
    monkeypatch.setattr(settings, "onebound_api_key", "k")
    monkeypatch.setenv("ONEBOUND_API_SECRET", "s")
    respx.get(f"{BASE_URL}/taobao/item_search/").mock(
        return_value=httpx.Response(
            200,
            json={
                "error_code": "0000",
                "items": {
                    "item": [
                        {
                            "num_iid": "681",
                            "title": "不锈钢折叠晾衣架",
                            "price": "31.00",
                            "promotion_price": "29.90",
                            "pic_url": "//img.alicdn.com/a.jpg",
                            "sales": "2140人付款",
                            "seller_nick": "佛山工厂店",
                            "detail_url": "//item.taobao.com/item.htm?id=681",
                        }
                    ]
                },
            },
        )
    )
    route_get = respx.get(f"{BASE_URL}/taobao/item_get/").mock(
        return_value=httpx.Response(
            200,
            json={
                "error_code": "0000",
                "item": {
                    "num_iid": "681",
                    "title": "不锈钢折叠晾衣架",
                    "price": "31.00",
                    "pic_url": "//img/a.jpg",
                    "item_imgs": [{"url": "//img/1.jpg"}, {"url": "//img/2.jpg"}],
                    "props": [{"name": "材质", "value": "304不锈钢"}],
                    "item_weight": "2.1",
                    "min_num": "2",
                    "nick": "佛山工厂店",
                },
            },
        )
    )
    respx.get(f"{BASE_URL}/taobao/item_review/").mock(
        return_value=httpx.Response(
            200,
            json={
                "error_code": "0000",
                "items": {"item": [{"rate_content": "很结实", "rate_star": 5, "rate_date": "2026-11-01"}]},
            },
        )
    )
    d = OneBound(client=httpx.AsyncClient())
    items = await d.search(SourceQuery(keywords=["晾衣架"], platforms=[SourcePlatform.TAOBAO]))
    assert len(items) == 1
    it = items[0]
    assert it.external_id == "681" and str(it.price_amount) == "29.90" and it.currency == "CNY"
    assert it.image_url == "https://img.alicdn.com/a.jpg" and it.sales_count == 2140
    p = await d.fetch_product("https://item.taobao.com/item.htm?id=681")
    assert p.specs == {"材质": "304不锈钢"} and p.weight_grams == 2100 and p.moq == 2 and len(p.images) == 2
    assert p.reviews and p.reviews[0].body == "很结实"
    assert route_get.calls.last.request.url.params["num_iid"] == "681"
    assert route_get.calls.last.request.url.params["key"] == "k"


@respx.mock
async def test_onebound_error_code(monkeypatch):
    monkeypatch.setattr(settings, "onebound_api_key", "k")
    monkeypatch.setenv("ONEBOUND_API_SECRET", "s")
    respx.get(f"{BASE_URL}/1688/item_search/").mock(
        return_value=httpx.Response(200, json={"error_code": "4005", "reason": "key không hợp lệ"})
    )
    with pytest.raises(IntegrationError, match="key không hợp lệ"):
        await OneBound(client=httpx.AsyncClient()).search(
            SourceQuery(keywords=["x"], platforms=[SourcePlatform.ALIBABA_1688])
        )
