"""Driver thật (Meta, Zalo OA) — kiểm theo tài liệu bằng HTTP giả (respx), CHƯA thử với tài khoản thật."""

from __future__ import annotations

import json
from datetime import timedelta

import httpx
import pytest
import respx

from app.core.config import settings
from app.core.enums import Channel
from app.core.security import hmac_sha256
from app.core.timeutil import now_utc
from app.integrations import IntegrationError, get_driver
from app.integrations.social.zalo_oa import zalo_signature
from app.modules.inbox.models import Thread, ThreadKind
from app.modules.inbox.policy import reply_window


@pytest.fixture
def meta_env(monkeypatch):
    for k, v in dict(
        meta_app_secret="app-secret", meta_page_id="PAGE1", meta_page_token="tok", meta_webhook_verify_token="verify-me"
    ).items():
        monkeypatch.setattr(settings, k, v)


@pytest.fixture
def zalo_env(monkeypatch):
    monkeypatch.setattr(settings, "zalo_oa_secret", "oa-secret")
    monkeypatch.setattr(settings, "zalo_oa_access_token", "ztok")
    monkeypatch.setattr(settings, "zalo_app_id", "app9")


def _meta_body(obj: str, entry: dict) -> bytes:
    return json.dumps({"object": obj, "entry": [entry]}).encode()


def _sig(body: bytes) -> dict[str, str]:
    return {"X-Hub-Signature-256": "sha256=" + hmac_sha256("app-secret", body)}


@respx.mock
async def test_meta_messenger_and_comment_webhook(meta_env):
    respx.get(url__regex=r"https://graph.facebook.com/v\d+\.\d+/PSID1.*").mock(
        return_value=httpx.Response(200, json={"name": "Trần Thu Hà"})
    )
    d = get_driver("social", "meta")
    body = _meta_body(
        "page",
        {
            "id": "PAGE1",
            "messaging": [
                {"sender": {"id": "PSID1"}, "recipient": {"id": "PAGE1"}, "timestamp": 1764000000000,
                 "message": {"mid": "m.1", "text": "Còn hàng không?"}},
                {"sender": {"id": "PAGE1"}, "recipient": {"id": "PSID1"}, "timestamp": 1764000000001,
                 "message": {"mid": "m.2", "text": "echo", "is_echo": True}},
                {"sender": {"id": "PSID1"}, "recipient": {"id": "PAGE1"}, "delivery": {"mids": ["m.0"]}},
            ],
            "changes": [
                {"field": "feed", "value": {"item": "comment", "verb": "add", "comment_id": "P_c2", "post_id": "P",
                                            "parent_id": "P_c1", "from": {"id": "U2", "name": "Ngọc"},
                                            "message": "Giá sao ạ", "created_time": 1764000000}},
                {"field": "feed", "value": {"item": "comment", "verb": "add", "comment_id": "P_c3", "post_id": "P",
                                            "parent_id": "P", "from": {"id": "PAGE1", "name": "Trang"},
                                            "message": "Trang tự trả lời"}},
            ],
        },
    )  # fmt: skip
    evs = await d.parse_webhook(_sig(body), body)
    assert [(e.kind, e.thread_external_id, e.author_name) for e in evs] == [
        ("direct_message", "PSID1", "Trần Thu Hà"),
        ("comment", "c:P_c1", "Ngọc"),
    ]
    assert evs[0].channel == Channel.FACEBOOK and evs[1].post_external_id == "P"
    with pytest.raises(IntegrationError):
        await d.parse_webhook({"X-Hub-Signature-256": "sha256=sai"}, body)


async def test_meta_instagram_webhook_and_verify(meta_env):
    d = get_driver("social", "meta")
    body = _meta_body(
        "instagram",
        {"id": "IG1", "changes": [{"field": "comments", "value": {"id": "c9", "text": "Còn màu xanh không?",
                                                                  "from": {"id": "u9", "username": "ngoc.home"},
                                                                  "media": {"id": "med1"}}}]},
    )  # fmt: skip
    (ev,) = await d.parse_webhook(_sig(body), body)
    assert ev.channel == Channel.INSTAGRAM and ev.author_name == "ngoc.home" and ev.thread_external_id == "c:c9"
    ok = {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42"}
    assert d.verify_subscription(ok) == "42"
    assert d.verify_subscription({**ok, "hub.verify_token": "sai"}) is None


@respx.mock
async def test_meta_send_uses_response_or_human_agent_tag(meta_env):
    route = respx.post(url__regex=r"https://graph.facebook.com/v\d+\.\d+/PAGE1/messages").mock(
        return_value=httpx.Response(200, json={"recipient_id": "PSID1", "message_id": "mid.9"})
    )
    reply = respx.post(url__regex=r".*/c1/comments").mock(return_value=httpx.Response(200, json={"id": "c1_r"}))
    d = get_driver("social", "meta")
    s = await d.send_message(Channel.FACEBOOK, "PSID1", "Dạ còn ạ")
    assert s.external_id == "mid.9"
    assert json.loads(route.calls[-1].request.content) == {
        "recipient": {"id": "PSID1"}, "message": {"text": "Dạ còn ạ"}, "messaging_type": "RESPONSE",
    }  # fmt: skip
    await d.send_message(Channel.FACEBOOK, "PSID1", "Dạ", tag="HUMAN_AGENT")
    sent = json.loads(route.calls[-1].request.content)
    assert sent["messaging_type"] == "MESSAGE_TAG" and sent["tag"] == "HUMAN_AGENT"
    await d.send_private_reply(Channel.FACEBOOK, "c2", "Mình nhắn riêng nhé")
    assert json.loads(route.calls[-1].request.content)["recipient"] == {"comment_id": "c2"}
    assert (await d.reply_comment(Channel.FACEBOOK, "c1", "Dạ")).external_id == "c1_r"
    assert reply.calls[-1].request.url.params["access_token"] == "tok"


@respx.mock
async def test_meta_error_is_reported(meta_env):
    respx.post(url__regex=r".*/PAGE1/messages").mock(
        return_value=httpx.Response(400, json={"error": {"message": "Outside window", "code": 10}})
    )
    with pytest.raises(IntegrationError) as e:
        await get_driver("social", "meta").send_message(Channel.FACEBOOK, "PSID1", "Dạ")
    assert "Outside window" in e.value.message and e.value.code == "meta_10"


@respx.mock
async def test_zalo_webhook_signature_and_send(zalo_env):
    respx.get(url__regex=r"https://openapi.zalo.me/v3.0/oa/user/detail.*").mock(
        return_value=httpx.Response(200, json={"error": 0, "data": {"display_name": "Anh Minh"}})
    )
    send = respx.post("https://openapi.zalo.me/v3.0/oa/message/cs").mock(
        return_value=httpx.Response(200, json={"error": 0, "data": {"message_id": "zm1"}})
    )
    d = get_driver("social", "zalo_oa")
    payload = {
        "app_id": "app9", "event_name": "user_send_text", "timestamp": "1764000000000",
        "sender": {"id": "zu1"}, "recipient": {"id": "oa1"}, "message": {"msg_id": "zmsg1", "text": "Đơn bị móp"},
    }  # fmt: skip
    body = json.dumps(payload).encode()
    mac = zalo_signature("app9", body, "1764000000000", "oa-secret")
    (ev,) = await d.parse_webhook({"X-ZEvent-Signature": f"mac={mac}"}, body)
    assert ev.channel == Channel.ZALO_OA and ev.author_name == "Anh Minh" and ev.account_external_id == "oa1"
    with pytest.raises(IntegrationError):
        await d.parse_webhook({"X-ZEvent-Signature": "mac=sai"}, body)
    follow = json.dumps({**payload, "event_name": "follow"}).encode()
    assert (
        await d.parse_webhook(
            {"X-ZEvent-Signature": f"mac={zalo_signature('app9', follow, '1764000000000', 'oa-secret')}"}, follow
        )
        == []
    )
    s = await d.send_message(Channel.ZALO_OA, "zu1", "Dạ chị xin lỗi ạ")
    assert s.external_id == "zm1" and send.calls[-1].request.headers["access_token"] == "ztok"
    assert json.loads(send.calls[-1].request.content)["recipient"] == {"user_id": "zu1"}


async def test_real_webhook_route_rejects_bad_signature(client, meta_env):
    body = _meta_body("page", {"id": "PAGE1", "messaging": []})
    r = await client.post("/api/hooks/social/facebook", content=body, headers={"X-Hub-Signature-256": "sha256=x"})
    assert r.status_code == 403
    r = await client.post("/api/hooks/social/facebook", content=body, headers=_sig(body))
    assert r.status_code == 200 and r.json() == {"received": 0, "new": 0}
    r = await client.get(
        "/api/hooks/social/facebook",
        params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "c"},
    )
    assert r.status_code == 200 and r.text == "c"
    assert (await client.get("/api/hooks/social/facebook", params={"hub.mode": "subscribe"})).status_code == 403
    assert (await client.post("/api/hooks/social/tiktok", content=b"{}")).status_code == 404


def test_reply_window_rules():
    now = now_utc()
    t = Thread(channel=Channel.FACEBOOK, kind=ThreadKind.DIRECT_MESSAGE, external_thread_id="x")
    t.last_inbound_at = now - timedelta(hours=2)
    assert reply_window(t, human=False).allowed
    t.last_inbound_at = now - timedelta(days=2)
    assert not reply_window(t, human=False).allowed
    assert reply_window(t, human=True).tag == "HUMAN_AGENT"
    t.last_inbound_at = now - timedelta(days=8)
    assert not reply_window(t, human=True).allowed
    c = Thread(channel=Channel.INSTAGRAM, kind=ThreadKind.COMMENT, external_thread_id="c:1")
    c.last_inbound_at = now - timedelta(days=30)
    assert reply_window(c, human=False).allowed
    assert not reply_window(c, human=True, private=True).allowed
    z = Thread(channel=Channel.ZALO_OA, kind=ThreadKind.DIRECT_MESSAGE, external_thread_id="z")
    z.last_inbound_at = now - timedelta(days=3)
    assert reply_window(z, human=False).allowed
    g = Thread(channel=Channel.ZALO_GROUP, kind=ThreadKind.GROUP, external_thread_id="g")
    assert not reply_window(g, human=True).allowed


@respx.mock
async def test_facebook_webhook_end_to_end_with_meta_driver(client, owner_client, meta_env, db):
    """Webhook Facebook thật → tài khoản driver «meta» → AI soạn → chị gửi → Send API (giả bằng respx)."""
    from tests.inbox import factories as f

    await f.product(db)
    await db.commit()
    respx.get(url__regex=r".*/PSID7.*").mock(return_value=httpx.Response(200, json={"name": "Thu Hà"}))
    send = respx.post(url__regex=r".*/PAGE1/messages").mock(
        return_value=httpx.Response(200, json={"recipient_id": "PSID7", "message_id": "mid.out"})
    )
    body = _meta_body(
        "page",
        {"id": "PAGE1", "messaging": [{"sender": {"id": "PSID7"}, "recipient": {"id": "PAGE1"},
                                       "timestamp": int(now_utc().timestamp() * 1000),
                                       "message": {"mid": "m.7", "text": "Bình giữ nhiệt giá bao nhiêu ạ?"}}]},
    )  # fmt: skip
    r = await client.post("/api/hooks/social/facebook", content=body, headers=_sig(body))
    assert r.json() == {"received": 1, "new": 1}
    lst = (await owner_client.get("/api/desk/inbox/threads")).json()["items"]
    assert lst[0]["participant_name"] == "Thu Hà" and lst[0]["draft"]["kind"] == "instant"
    r = await owner_client.post(f"/api/desk/inbox/drafts/{lst[0]['draft']['id']}/send", json={})
    assert r.status_code == 200, r.text
    sent = json.loads(send.calls[-1].request.content)
    assert sent["recipient"] == {"id": "PSID7"} and sent["messaging_type"] == "RESPONSE"
    assert "385.000" in sent["message"]["text"]
