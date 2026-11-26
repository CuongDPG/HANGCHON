"""Cài đặt → Nguồn hàng: lưu khoá dịch vụ (mã hoá, chỉ trả dạng che), Cài đặt thắng biến môi trường, kiểm tra kết nối
(lọc khoá trong lời báo lỗi), chọn cách lấy hàng từng sàn mà driver `routed` tuân theo. HTTP đi qua respx, không gọi thật."""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlalchemy import text

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.enums import SourcePlatform
from app.integrations import get_driver, source_config
from app.integrations.base import driver_name
from app.integrations.sources import SourceQuery
from app.integrations.sources.onebound import BASE_URL
from app.integrations.sources.rakuten import SEARCH_URL, item_code

B = "/api/desk/control/sources"
OB_KEY = "ob-key-FAKE-1234567890-K7Qa"  # khoá giả
OB_SECRET = "ob-secret-FAKE-0987654321-S9Zx"
RK_KEY = "pk_FAKEaccesskey1234567890Wq"


async def _db_text() -> str:
    async with SessionLocal() as s:
        parts = []
        for table in ("app_settings", "audit_log"):
            parts += list((await s.execute(text(f"SELECT row_to_json(t)::text FROM {table} t"))).scalars())
    return "\n".join(parts)


def _p(data: dict, platform: str) -> dict:
    return next(x for x in data["platforms"] if x["platform"] == platform)


def _a(data: dict, account: str) -> dict:
    return next(x for x in data["accounts"] if x["account"] == account)


async def test_only_owner(helper_client: httpx.AsyncClient):
    assert (await helper_client.get(B)).status_code == 403
    assert (await helper_client.patch(f"{B}/platforms/taobao", json={"driver": "web"})).status_code == 403
    assert (await helper_client.patch(f"{B}/accounts/onebound", json={"values": {"api_key": "x"}})).status_code == 403
    assert (await helper_client.post(f"{B}/accounts/onebound/check", json={})).status_code == 403


async def test_overview_lists_platforms_accounts_and_guides(owner_client: httpx.AsyncClient):
    r = await owner_client.get(B)
    assert r.status_code == 200, r.text
    data = r.json()
    assert [p["platform"] for p in data["platforms"]] == [
        "1688", "taobao", "tmall", "pinduoduo", "alibaba", "rakuten", "amazon_jp",
    ]  # fmt: skip
    assert all(p["status"] == "mock" and p["driver_source"] == "env" for p in data["platforms"])
    assert [o["driver"] for o in _p(data, "taobao")["options"]] == ["mock", "web", "onebound"]
    assert [o["driver"] for o in _p(data, "alibaba")["options"]] == ["mock", "web"]
    for acc in data["accounts"]:
        assert acc["guide"]["steps"] and acc["guide"]["cost"] and not acc["ready"] and not acc["verified"]
        assert all(link["url"].startswith("https://") for link in acc["guide"]["links"])
    assert driver_name("sources") == "mock"


async def test_save_encrypts_masks_and_hides_from_settings(owner_client: httpx.AsyncClient):
    r = await owner_client.patch(
        f"{B}/accounts/onebound", json={"values": {"api_key": OB_KEY, "api_secret": OB_SECRET}}
    )
    assert r.status_code == 200, r.text
    assert OB_KEY not in r.text and OB_SECRET not in r.text
    f = {x["key"]: x for x in r.json()["fields"]}
    assert f["api_secret"]["masked"] == "••••" + OB_SECRET[-4:] and f["api_secret"]["source"] == "settings"
    assert r.json()["ready"]
    raw = await _db_text()
    assert OB_KEY not in raw and OB_SECRET not in raw  # chỉ lưu dạng mã hoá, lưu vết không ghi giá trị
    assert "control.source_account_saved" in raw
    settings_list = (await owner_client.get("/api/desk/control/settings")).json()
    assert not any(s["key"].startswith("source_account.") for s in settings_list)
    bad = await owner_client.patch("/api/desk/control/settings/source_account.onebound", json={"value": {}})
    assert bad.status_code == 400
    # ô bí mật để trống = giữ giá trị cũ; clear = xoá
    r = await owner_client.patch(f"{B}/accounts/onebound", json={"values": {"api_secret": ""}, "clear": ["api_key"]})
    f = {x["key"]: x for x in r.json()["fields"]}
    assert f["api_secret"]["is_set"] and not f["api_key"]["is_set"]
    assert (await owner_client.patch(f"{B}/accounts/onebound", json={"values": {"x": "1"}})).status_code == 400
    assert (await owner_client.patch(f"{B}/accounts/khong-co", json={})).status_code == 404


@respx.mock
async def test_settings_override_env(owner_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "onebound_api_key", "env-key-AAAA")
    monkeypatch.setattr(settings, "onebound_api_secret", "env-secret-BBBB")
    f = {x["key"]: x for x in _a((await owner_client.get(B)).json(), "onebound")["fields"]}
    assert f["api_key"]["source"] == "env" and f["api_key"]["masked"].endswith("AAAA")
    await owner_client.patch(f"{B}/accounts/onebound", json={"values": {"api_key": OB_KEY}})
    assert source_config.value("onebound", "api_key") == OB_KEY  # Cài đặt thắng env
    assert source_config.value("onebound", "api_secret") == "env-secret-BBBB"  # ô chưa lưu vẫn theo env
    route = respx.get(f"{BASE_URL}/taobao/item_search/").mock(
        return_value=httpx.Response(200, json={"error_code": "0000", "items": {"item": []}})
    )
    await get_driver("sources", "onebound").search(SourceQuery(keywords=["杯"], platforms=[SourcePlatform.TAOBAO]))
    assert route.calls.last.request.url.params["key"] == OB_KEY


@respx.mock
async def test_check_ok_and_error_is_scrubbed(owner_client: httpx.AsyncClient):
    await owner_client.patch(f"{B}/accounts/onebound", json={"values": {"api_key": OB_KEY, "api_secret": OB_SECRET}})
    route = respx.get(f"{BASE_URL}/taobao/item_get/").mock(
        return_value=httpx.Response(200, json={"error_code": "0000", "item": {"title": "保温杯"}})
    )
    r = await owner_client.post(f"{B}/accounts/onebound/check", json={})
    assert r.status_code == 200 and r.json()["ok"] and "保温杯" in r.json()["message"]
    assert route.calls.last.request.url.params["secret"] == OB_SECRET
    assert _a((await owner_client.get(B)).json(), "onebound")["check"]["ok"]
    # dịch vụ lặp lại khoá trong câu báo lỗi → phải lọc
    route.mock(return_value=httpx.Response(200, json={"error_code": "4005", "reason": f"bad secret {OB_SECRET}"}))
    r = await owner_client.post(f"{B}/accounts/onebound/check", json={})
    assert not r.json()["ok"] and OB_SECRET not in r.text and "***" in r.json()["message"]
    # khoá đang nhập (chưa lưu) được dùng để thử
    route.mock(return_value=httpx.Response(200, json={"error_code": "0000", "item": {}}))
    r = await owner_client.post(f"{B}/accounts/onebound/check", json={"values": {"api_secret": "typed-secret-XYZW"}})
    assert r.json()["ok"] and route.calls.last.request.url.params["secret"] == "typed-secret-XYZW"
    assert OB_SECRET not in await _db_text()


async def test_check_without_keys(owner_client: httpx.AsyncClient):
    r = await owner_client.post(f"{B}/accounts/rakuten/check", json={})
    assert r.status_code == 200 and not r.json()["ok"] and "Application ID" in r.json()["message"]


@respx.mock
async def test_route_per_platform(owner_client: httpx.AsyncClient):
    r = await owner_client.patch(f"{B}/platforms/taobao", json={"driver": "onebound"})
    assert r.status_code == 200, r.text
    tb = _p(r.json(), "taobao")
    assert tb["driver"] == "onebound" and tb["status"] == "not_connected" and tb["driver_source"] == "settings"
    assert driver_name("sources") == "routed"
    await owner_client.patch(f"{B}/accounts/onebound", json={"values": {"api_key": OB_KEY, "api_secret": OB_SECRET}})
    data = (await owner_client.get(B)).json()
    assert _p(data, "taobao")["status"] == "connected" and _a(data, "onebound")["used_by"] == ["taobao"]
    r = await owner_client.patch(f"{B}/platforms/rakuten", json={"driver": "web"})
    assert _p(r.json(), "rakuten")["status"] == "web" and _p(r.json(), "rakuten")["warning"]  # AI đang giả lập
    assert r.json()["general_driver"] == "web"

    respx.get(f"{BASE_URL}/taobao/item_search/").mock(
        return_value=httpx.Response(
            200, json={"error_code": "0000", "items": {"item": [{"num_iid": "9", "title": "杯", "price": "5"}]}}
        )
    )
    src = get_driver("sources")
    assert src.name == "routed"
    items = await src.search(
        SourceQuery(keywords=["杯"], platforms=[SourcePlatform.TAOBAO, SourcePlatform.ALIBABA_1688])
    )
    by = {i.platform for i in items}
    assert SourcePlatform.TAOBAO in by and SourcePlatform.ALIBABA_1688 in by  # 1688 vẫn giả lập (env mock)
    assert next(i for i in items if i.platform == SourcePlatform.TAOBAO).external_id == "9"

    integ = next(i for i in (await owner_client.get("/api/desk/control/integrations")).json() if i["kind"] == "sources")
    assert integ["partly_mock"] and "onebound" in integ["drivers"]

    assert (await owner_client.patch(f"{B}/platforms/alibaba", json={"driver": "onebound"})).status_code == 400
    assert (await owner_client.patch(f"{B}/platforms/shopee_vn", json={"driver": "web"})).status_code == 404
    await owner_client.patch(f"{B}/platforms/taobao", json={"driver": None})
    await owner_client.patch(f"{B}/platforms/rakuten", json={"driver": None})
    assert driver_name("sources") == "mock"  # bỏ chọn hết → theo SOURCES_DRIVER
    assert "control.source_route_saved" in await _db_text()


def test_env_route_falls_back(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "sources_driver", "onebound")
    assert source_config.env_route(SourcePlatform.TAOBAO) == "onebound"
    assert source_config.env_route(SourcePlatform.RAKUTEN) == "web"  # OneBound không lấy được Rakuten
    monkeypatch.setattr(settings, "sources_driver", "mock")
    assert source_config.env_route(SourcePlatform.RAKUTEN) == "mock"


@respx.mock
async def test_rakuten_driver_maps_search_and_product(owner_client: httpx.AsyncClient):
    await owner_client.patch(
        f"{B}/accounts/rakuten", json={"values": {"application_id": "uuid-app-1", "access_key": RK_KEY}}
    )
    item = {
        "itemName": "真空断熱タンブラー 450ml",
        "itemPrice": 1980,
        "itemCode": "shop-a:tumbler-450",
        "itemUrl": "https://item.rakuten.co.jp/shop-a/tumbler-450/",
        "itemCaption": "ステンレス製",
        "mediumImageUrls": ["https://thumbnail.image.rakuten.co.jp/a.jpg?_ex=128x128"],
        "shopName": "ショップA",
        "reviewAverage": 4.5,
        "reviewCount": 120,
    }
    route = respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json={"Items": [item], "count": 1}))
    d = get_driver("sources", "rakuten")
    items = await d.search(SourceQuery(keywords=["タンブラー"], platforms=[SourcePlatform.RAKUTEN], price_max=3000))
    assert len(items) == 1 and items[0].price_amount == 1980 and items[0].currency == "JPY"
    assert items[0].image_url == "https://thumbnail.image.rakuten.co.jp/a.jpg" and items[0].review_count == 120
    req = route.calls.last.request
    assert req.url.params["applicationId"] == "uuid-app-1" and req.url.params["maxPrice"] == "3000"
    assert req.headers["accessKey"] == RK_KEY and req.headers["Referer"].startswith("http")
    assert item_code("https://item.rakuten.co.jp/shop-a/tumbler-450/") == "shop-a:tumbler-450"
    p = await d.fetch_product("https://item.rakuten.co.jp/shop-a/tumbler-450/")
    assert p.description == "ステンレス製" and route.calls.last.request.url.params["itemCode"] == "shop-a:tumbler-450"

    route.mock(return_value=httpx.Response(403, json={"error": "forbidden", "error_description": f"bad {RK_KEY}"}))
    r = await owner_client.post(f"{B}/accounts/rakuten/check", json={})
    assert not r.json()["ok"] and RK_KEY not in r.text and "403" in r.json()["message"]
