"""Cài đặt → Mạng xã hội: lưu khoá kênh (mã hoá, chỉ trả dạng che), kiểm tra kết nối, «Kết nối» OAuth, tự làm mới
token, công tắc giả lập ↔ thật mà driver tuân theo. Không gọi nền tảng thật: mọi HTTP đi qua httpx.MockTransport."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select, text

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.enums import Channel
from app.core.secrets import decrypt
from app.integrations import channel_config as cc
from app.integrations import channel_oauth
from app.modules.control.models import AppSetting, AuditLog

BASE = "/api/desk/control/channels"
PAGE_TOKEN = "EAAFAKEPAGETOKENFAKEFAKEFAKE-test-W9xQ"  # khoá giả


@pytest.fixture
def platform() -> Iterator[Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]]:
    """Gắn nền tảng giả cho channel_oauth; trả danh sách request đã gọi."""
    calls: list[httpx.Request] = []

    def install(handler: Callable[[httpx.Request], httpx.Response]) -> list[httpx.Request]:
        def wrap(req: httpx.Request) -> httpx.Response:
            calls.append(req)
            return handler(req)

        channel_oauth.set_transport(httpx.MockTransport(wrap))
        return calls

    yield install
    channel_oauth.set_transport(None)


async def _raw_db_text() -> str:
    async with SessionLocal() as s:
        parts = []
        for table in ("app_settings", "audit_log"):
            parts += list((await s.execute(text(f"SELECT row_to_json(t)::text FROM {table} t"))).scalars())
    return "\n".join(parts)


def _card(items: list[dict], channel: str) -> dict:
    return next(c for c in items if c["channel"] == channel)


async def test_only_owner(helper_client: httpx.AsyncClient):
    assert (await helper_client.get(BASE)).status_code == 403
    assert (await helper_client.patch(f"{BASE}/facebook", json={"mode": "real"})).status_code == 403


async def test_list_has_every_channel_with_guide(owner_client: httpx.AsyncClient):
    r = await owner_client.get(BASE)
    assert r.status_code == 200, r.text
    items = r.json()
    assert [c["channel"] for c in items] == [
        "facebook", "instagram", "threads", "tiktok", "zalo_oa", "zalo_group", "shopee", "tiktok_shop",
    ]  # fmt: skip
    fb = _card(items, "facebook")
    assert fb["status"] == "mock" and fb["mode_source"] == "env" and not fb["ready"]
    assert fb["guide"]["steps"] and all(link["url"].startswith("https://") for link in fb["guide"]["links"])
    tiktok = _card(items, "tiktok")
    assert tiktok["oauth"]["supported"] and tiktok["oauth"]["redirect_uri"].endswith("/api/hooks/oauth/tiktok")
    assert _card(items, "zalo_group")["status"] == "manual"


async def test_save_encrypts_secret_and_masks_on_read(owner_client: httpx.AsyncClient):
    r = await owner_client.patch(f"{BASE}/facebook", json={"values": {"page_id": "1234567", "page_token": PAGE_TOKEN}})
    assert r.status_code == 200, r.text
    assert PAGE_TOKEN not in r.text
    f = {x["key"]: x for x in r.json()["fields"]}
    assert f["page_id"]["value"] == "1234567" and f["page_id"]["source"] == "settings"
    assert f["page_token"]["value"] is None and f["page_token"]["masked"] == "••••W9xQ" and f["page_token"]["is_set"]
    assert r.json()["ready"] and r.json()["status"] == "mock"  # có khoá nhưng chưa bật chạy thật

    # không lộ qua danh sách cài đặt chung, không sửa được qua PATCH /settings
    settings_list = (await owner_client.get("/api/desk/control/settings")).json()
    assert not any(s["key"].startswith("channel_account.") for s in settings_list)
    bad = await owner_client.patch("/api/desk/control/settings", json={"values": {"channel_account.facebook": {}}})
    assert bad.status_code == 400

    # CSDL chỉ có bản mã hoá; lưu vết ghi tên ô, không ghi giá trị
    assert PAGE_TOKEN not in await _raw_db_text()
    async with SessionLocal() as s:
        row = await s.get(AppSetting, "channel_account.facebook")
        audits = list(
            (await s.execute(select(AuditLog).where(AuditLog.action == "control.channel_account_saved"))).scalars()
        )
    assert decrypt(row.value["secrets"]["page_token"]) == PAGE_TOKEN
    assert len(audits) == 1 and set(audits[0].data["changed"]) == {"page_id", "page_token"}

    # ô bí mật để trống = giữ; clear = xoá về biến môi trường
    r = await owner_client.patch(f"{BASE}/facebook", json={"values": {"page_token": ""}})
    assert {x["key"]: x for x in r.json()["fields"]}["page_token"]["is_set"]
    r = await owner_client.patch(f"{BASE}/facebook", json={"clear": ["page_token"]})
    assert not {x["key"]: x for x in r.json()["fields"]}["page_token"]["is_set"]


async def test_validation(owner_client: httpx.AsyncClient):
    assert (await owner_client.patch(f"{BASE}/nope", json={"mode": "real"})).status_code == 404
    assert (await owner_client.patch(f"{BASE}/facebook", json={"values": {"khong_co": "x"}})).status_code == 400
    r = await owner_client.patch(f"{BASE}/tiktok", json={"values": {"access_token": "dan-tay"}})
    assert r.status_code == 400 and "Kết nối" in r.json()["detail"]
    assert (await owner_client.patch(f"{BASE}/zalo_group", json={"mode": "real"})).status_code == 400
    assert (await owner_client.patch(f"{BASE}/facebook", json={"mode": "bat"})).status_code == 422


async def test_db_switch_overrides_env_for_driver_selection(owner_client: httpx.AsyncClient, monkeypatch):
    from app.integrations.social import driver_name_for
    from app.modules.orders.marketplace import driver_for as marketplace_driver

    monkeypatch.setattr(settings, "social_channel_drivers", "facebook=meta")
    monkeypatch.setattr(settings, "marketplaces_driver", "mock")
    assert driver_name_for(Channel.FACEBOOK) == "meta" and driver_name_for(Channel.TIKTOK) == "mock"

    await owner_client.patch(f"{BASE}/facebook", json={"mode": "mock"})
    await owner_client.patch(f"{BASE}/tiktok", json={"mode": "real"})
    await owner_client.patch(f"{BASE}/shopee", json={"mode": "real"})
    assert driver_name_for(Channel.FACEBOOK) == "mock"  # chị tắt: thắng env
    assert driver_name_for(Channel.TIKTOK) == "tiktok_draft"
    assert marketplace_driver(Channel.SHOPEE).name == "shopee"
    assert marketplace_driver(Channel.TIKTOK_SHOP).name == "mock"

    # màn Tích hợp phản ánh công tắc
    social = next(i for i in (await owner_client.get("/api/desk/control/integrations")).json() if i["kind"] == "social")
    assert set(social["drivers"]) == {"mock", "tiktok_draft"} and social["partly_mock"]

    # tiến trình khác (worker) thấy sau khi đọc lại bản chụp
    cc.reset()
    assert driver_name_for(Channel.FACEBOOK) == "meta"
    await cc.ensure_fresh()
    assert driver_name_for(Channel.FACEBOOK) == "mock"


async def test_driver_reads_settings_over_env(owner_client: httpx.AsyncClient, monkeypatch):
    from app.integrations.social._meta_publish import MetaPublisher

    monkeypatch.setattr(settings, "meta_page_id", "env-page")
    monkeypatch.setattr(settings, "meta_page_token", "env-token")
    assert MetaPublisher()._page() == ("env-page", "env-token")
    await owner_client.patch(f"{BASE}/facebook", json={"values": {"page_id": "db-page", "page_token": PAGE_TOKEN}})
    assert MetaPublisher()._page() == ("db-page", PAGE_TOKEN)
    await owner_client.patch(f"{BASE}/instagram", json={"values": {"ig_user_id": "1789"}})
    assert MetaPublisher()._ig() == ("1789", PAGE_TOKEN)  # Instagram dùng chung mã Trang


async def test_check_facebook_ok_and_error(owner_client: httpx.AsyncClient, platform):
    await owner_client.patch(f"{BASE}/facebook", json={"values": {"page_id": "1234567", "page_token": PAGE_TOKEN}})

    def ok(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/1234567") and req.url.params["fields"] == "id,name"
        return httpx.Response(200, json={"id": "1234567", "name": "Hàng Chọn"})

    calls = platform(ok)
    r = await owner_client.post(f"{BASE}/facebook/check", json={})
    assert r.status_code == 200
    assert (
        r.json()["ok"]
        and r.json()["message"] == "Đã nối Trang «Hàng Chọn»."
        and r.json()["account_name"] == "Hàng Chọn"
    )
    assert calls[0].url.params["access_token"] == PAGE_TOKEN
    card = _card((await owner_client.get(BASE)).json(), "facebook")
    assert card["account_name"] == "Hàng Chọn" and card["check"]["ok"]

    def bad(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": f"Invalid OAuth access token {PAGE_TOKEN}", "code": 190}})

    platform(bad)
    r = await owner_client.post(f"{BASE}/facebook/check", json={})
    body = r.json()
    assert not body["ok"] and "Facebook báo lỗi" in body["message"] and PAGE_TOKEN not in r.text


async def test_check_reports_missing_fields_and_uses_unsaved_input(owner_client: httpx.AsyncClient, platform):
    r = await owner_client.post(f"{BASE}/threads/check", json={})
    assert not r.json()["ok"] and "Còn thiếu" in r.json()["message"]

    platform(lambda req: httpx.Response(200, json={"id": "42", "username": "hangchon"}))
    r = await owner_client.post(
        f"{BASE}/threads/check", json={"values": {"user_id": "42", "access_token": "THtoken-1234"}}
    )
    assert r.json()["ok"] and r.json()["account_name"] == "@hangchon"


async def test_tiktok_connect_callback_and_refresh(
    owner_client: httpx.AsyncClient, client: httpx.AsyncClient, platform
):
    r = await owner_client.post(f"{BASE}/tiktok/connect")
    assert r.status_code == 400  # chưa có client key

    await owner_client.patch(
        f"{BASE}/tiktok", json={"values": {"client_key": "ck-test", "client_secret": "cs-test-secret"}}
    )
    r = await owner_client.post(f"{BASE}/tiktok/connect")
    assert r.status_code == 200, r.text
    url = urlparse(r.json()["url"])
    q = parse_qs(url.query)
    assert url.netloc == "www.tiktok.com" and q["client_key"] == ["ck-test"] and q["response_type"] == ["code"]
    assert (
        q["redirect_uri"] == [f"{settings.web_base_url}/api/hooks/oauth/tiktok"] and "user.info.basic" in q["scope"][0]
    )
    state = q["state"][0]

    def tiktok(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v2/oauth/token/":
            form = parse_qs(req.content.decode())
            if form["grant_type"] == ["authorization_code"]:
                assert form["code"] == ["the-code"] and form["client_secret"] == ["cs-test-secret"]
                return httpx.Response(200, json={"access_token": "act.first", "refresh_token": "rft.first",
                                                 "expires_in": 7200, "refresh_expires_in": 15552000, "open_id": "oid"})  # fmt: skip
            assert form["refresh_token"] == ["rft.first"]
            return httpx.Response(
                200, json={"access_token": "act.second", "refresh_token": "rft.second", "expires_in": 7200}
            )
        assert req.url.path == "/v2/user/info/"
        return httpx.Response(200, json={"data": {"user": {"display_name": "Mai chọn hàng"}}, "error": {"code": "ok"}})

    calls = platform(tiktok)
    # state sai → về Cài đặt kèm lỗi, không đổi mã
    bad = await client.get("/api/hooks/oauth/tiktok", params={"code": "the-code", "state": "sai"})
    assert bad.status_code == 303 and "ket_qua=loi" in bad.headers["location"] and not calls

    ok = await client.get("/api/hooks/oauth/tiktok", params={"code": "the-code", "state": state})
    assert ok.status_code == 303 and ok.headers["location"].endswith("/desk/cai-dat/mang-xa-hoi?kenh=tiktok&ket_qua=ok")
    # state chỉ dùng một lần
    again = await client.get("/api/hooks/oauth/tiktok", params={"code": "the-code", "state": state})
    assert "ket_qua=loi" in again.headers["location"]

    card = _card((await owner_client.get(BASE)).json(), "tiktok")
    assert card["oauth"]["connected"] and card["account_name"] == "Mai chọn hàng" and "act.first" not in str(card)
    assert "act.first" not in await _raw_db_text()

    # token sắp hết hạn → driver lấy token mới, refresh token mới được lưu (TikTok đổi mỗi lần)
    await cc.store_tokens("tiktok", {}, {"expires_at": time.time() + 60})
    assert await channel_oauth.tiktok_access_token() == "act.second"
    assert cc.value("tiktok", "refresh_token") == "rft.second"
    cc.reset()
    await cc.refresh()
    assert cc.value("tiktok", "access_token") == "act.second"  # tiến trình khác cũng thấy


async def test_shopee_connect_signs_and_stores_shop(
    owner_client: httpx.AsyncClient, client: httpx.AsyncClient, platform
):
    await owner_client.patch(f"{BASE}/shopee", json={"values": {"partner_id": "10090", "partner_key": "pk-test-key"}})
    r = await owner_client.post(f"{BASE}/shopee/connect")
    url = urlparse(r.json()["url"])
    q = parse_qs(url.query)
    assert url.path == "/api/v2/shop/auth_partner" and q["partner_id"] == ["10090"] and len(q["sign"][0]) == 64
    back = urlparse(q["redirect"][0])
    state = parse_qs(back.query)["state"][0]

    def shopee(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v2/auth/token/get":
            assert b'"shop_id":555' in req.content.replace(b" ", b"")
            return httpx.Response(
                200, json={"access_token": "sp-at", "refresh_token": "sp-rt", "expire_in": 14400, "error": ""}
            )
        assert req.url.path == "/api/v2/shop/get_shop_info" and req.url.params["shop_id"] == "555"
        return httpx.Response(200, json={"shop_name": "Hàng Chọn shop", "error": ""})

    platform(shopee)
    res = await client.get(back.path, params={"state": state, "code": "c0de", "shop_id": "555"})
    assert "ket_qua=ok" in res.headers["location"]
    card = _card((await owner_client.get(BASE)).json(), "shopee")
    fields = {f["key"]: f for f in card["fields"]}
    assert fields["shop_id"]["value"] == "555" and card["account_name"] == "Hàng Chọn shop"


async def test_zalo_refresh_persists_new_tokens_in_settings(owner_client: httpx.AsyncClient, platform):
    from app.integrations._zalo_token import ZaloTokenStore

    await owner_client.patch(
        f"{BASE}/zalo_oa",
        json={"values": {"oa_id": "oa1", "app_id": "app1", "app_secret": "zsecret-1", "access_token": "zat-old1",
                         "refresh_token": "zrt-old1"}},
    )  # fmt: skip

    def zalo(req: httpx.Request) -> httpx.Response:
        assert req.headers["secret_key"] == "zsecret-1" and b"zrt-old1" in req.content
        return httpx.Response(
            200, json={"access_token": "zat-new1", "refresh_token": "zrt-new1", "expires_in": "90000"}
        )

    platform(zalo)
    r = await owner_client.post(f"{BASE}/zalo_oa/check", json={})
    assert r.json()["ok"], r.text
    assert cc.value("zalo_oa", "access_token") == "zat-new1" and cc.value("zalo_oa", "refresh_token") == "zrt-new1"
    assert await ZaloTokenStore().access_token() == "zat-new1"  # driver/ZNS dùng token mới, không gọi lại Zalo
