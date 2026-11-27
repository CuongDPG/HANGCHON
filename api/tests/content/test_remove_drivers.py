"""Gỡ bài / ngừng bán trên sàn ở driver thật (CHƯA thử với tài khoản thật): kiểm hình dạng yêu cầu bằng HTTP giả."""

from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import settings
from app.core.enums import Channel
from app.integrations.base import IntegrationError
from app.integrations.marketplaces import shopee, tiktok_shop
from app.integrations.social import _ratelimit as rl
from app.integrations.social.meta import Driver as MetaDriver
from app.integrations.social.zalo_oa import Driver as ZaloDriver


@pytest.fixture(autouse=True)
def _meta(monkeypatch):
    monkeypatch.setattr("app.integrations.social._meta_publish.limiter", rl.RateLimiter())
    for k, v in {"meta_page_id": "P1", "meta_page_token": "TOK", "meta_ig_user_id": "IG1", "threads_user_id": "U1",
                 "threads_access_token": "TT"}.items():  # fmt: skip
        monkeypatch.setattr(settings, k, v)


def _driver(calls: list[httpx.Request]) -> MetaDriver:
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(200, json={"success": True})

    return MetaDriver(transport=httpx.MockTransport(handler))


async def test_facebook_hide_restore_and_delete() -> None:
    calls: list[httpx.Request] = []
    d = _driver(calls)
    assert d.remove_modes(Channel.FACEBOOK) == {"hide", "delete"}
    assert (await d.remove_post(Channel.FACEBOOK, "P1_9")).mode == "hidden"
    await d.restore_post(Channel.FACEBOOK, "P1_9")
    assert (await d.remove_post(Channel.FACEBOOK, "P1_9", mode="delete")).mode == "deleted"
    hide, restore, delete = calls
    assert hide.method == "POST" and hide.url.path == f"/{settings.meta_graph_version}/P1_9"
    assert parse_qs(hide.content.decode()) == {"is_hidden": ["true"], "access_token": ["TOK"]}
    assert parse_qs(restore.content.decode())["is_hidden"] == ["false"]
    assert delete.method == "DELETE" and delete.url.params["access_token"] == "TOK"


async def test_instagram_threads_only_delete_and_never_escalate() -> None:
    calls: list[httpx.Request] = []
    d = _driver(calls)
    assert (await d.remove_post(Channel.INSTAGRAM, "IGM1")).mode == "unsupported"  # «ẩn» không có → không gọi gì
    assert (await d.remove_post(Channel.THREADS, "T1")).mode == "unsupported"
    assert calls == []
    assert (await d.remove_post(Channel.INSTAGRAM, "IGM1", mode="delete")).mode == "deleted"
    assert (await d.remove_post(Channel.THREADS, "T1", mode="delete")).mode == "deleted"
    ig, th = calls
    assert ig.method == "DELETE" and ig.url.host == "graph.facebook.com" and ig.url.path.endswith("/IGM1")
    assert th.method == "DELETE" and th.url.host == "graph.threads.net" and th.url.path == "/v1.0/T1"
    assert th.url.params["access_token"] == "TT"
    with pytest.raises(IntegrationError):
        await d.restore_post(Channel.INSTAGRAM, "IGM1")


async def test_zalo_and_tiktok_are_manual() -> None:
    z = ZaloDriver()
    assert z.remove_modes(Channel.ZALO_OA) == frozenset()
    assert (await z.remove_post(Channel.ZALO_OA, "x", mode="delete")).mode == "unsupported"


async def test_marketplace_deactivate_request_shapes(monkeypatch) -> None:
    sent: list[tuple[str, str, dict]] = []

    async def fake_call(self, method, path, *, params=None, body=None):
        sent.append((method, path, body))
        return {}

    monkeypatch.setattr(tiktok_shop.Driver, "_call", fake_call)
    monkeypatch.setattr(shopee.Driver, "_call", fake_call)
    tts, sp = tiktok_shop.Driver(), shopee.Driver()
    assert tts.supports_deactivate and sp.supports_deactivate
    await tts.deactivate_product(Channel.TIKTOK_SHOP, "729:111")
    await tts.activate_product(Channel.TIKTOK_SHOP, "729:111")
    await sp.deactivate_product(Channel.SHOPEE, "123")
    await sp.activate_product(Channel.SHOPEE, "123")
    assert sent == [
        ("POST", "/product/202309/products/deactivate", {"product_ids": ["729"]}),
        ("POST", "/product/202309/products/activate", {"product_ids": ["729"]}),
        ("POST", "/api/v2/product/unlist_item", {"item_list": [{"item_id": 123, "unlist": True}]}),
        ("POST", "/api/v2/product/unlist_item", {"item_list": [{"item_id": 123, "unlist": False}]}),
    ]


async def test_shopee_unlist_failure_list_raises(monkeypatch) -> None:
    async def fake_call(self, method, path, *, params=None, body=None):
        return {"failure_list": [{"item_id": 123, "failed_reason": "item not found"}]}

    monkeypatch.setattr(shopee.Driver, "_call", fake_call)
    with pytest.raises(IntegrationError, match="item not found"):
        await shopee.Driver().deactivate_product(Channel.SHOPEE, "123")
