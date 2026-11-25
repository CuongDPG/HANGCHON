"""Driver đăng bài thật (chưa thử với tài khoản thật): kiểm hình dạng yêu cầu theo tài liệu bằng HTTP giả + luật soát."""

from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import settings
from app.core.enums import Channel
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.integrations.social import SocialPost
from app.integrations.social import _ratelimit as rl
from app.integrations.social.meta import Driver as MetaDriver
from app.integrations.social.tiktok_draft import Driver as TikTokDriver
from app.integrations.social.zalo_oa import Driver as ZaloDriver
from app.modules.content.ai_io import ProductFacts
from app.modules.content.checks import (
    build_findings,
    check_claims,
    check_numbers,
    check_process,
    money_mentions,
    status_of,
)
from app.modules.content.models import CheckStatus


@pytest.fixture(autouse=True)
def _fresh_limiter(monkeypatch):
    for mod in (
        "app.integrations.social._meta_publish",
        "app.integrations.social.tiktok_draft",
        "app.integrations.social._zalo_oa_publish",
    ):
        monkeypatch.setattr(f"{mod}.limiter", rl.RateLimiter())


class Recorder:
    def __init__(self, routes):
        self.routes = routes
        self.calls: list[httpx.Request] = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        for (method, frag), resp in self.routes.items():
            if req.method == method and frag in str(req.url):
                body = resp(req) if callable(resp) else resp
                return httpx.Response(200, json=body)
        return httpx.Response(404, json={"error": {"message": f"không có route {req.url}"}})


def _form(req: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(req.content.decode()).items()}


async def test_meta_facebook_text_with_link(monkeypatch):
    monkeypatch.setattr(settings, "meta_page_id", "P1")
    monkeypatch.setattr(settings, "meta_page_token", "TOK")
    rec = Recorder({("POST", "/P1/feed"): {"id": "P1_99"}})
    d = MetaDriver(transport=httpx.MockTransport(rec.handler))
    res = await d.publish(
        SocialPost(channel=Channel.FACEBOOK, text="Xin chào", link_url="https://x.vn/san-pham/a?src=ab")
    )
    assert res.external_id == "P1_99" and res.status == "published"
    f = _form(rec.calls[0])
    assert f["message"] == "Xin chào" and f["link"].endswith("?src=ab") and f["access_token"] == "TOK"


async def test_meta_instagram_carousel_flow(monkeypatch):
    monkeypatch.setattr(settings, "meta_ig_user_id", "IG1")
    monkeypatch.setattr(settings, "meta_page_token", "TOK")
    n = {"i": 0}

    def media(req):
        n["i"] += 1
        return {"id": f"C{n['i']}"}

    rec = Recorder(
        {
            ("POST", "/IG1/media_publish"): {"id": "M1"},
            ("POST", "/IG1/media"): media,
            ("GET", "/M1"): {"permalink": "https://instagram.com/p/x"},
            ("GET", "/C"): {"status_code": "FINISHED"},
        }
    )
    d = MetaDriver(transport=httpx.MockTransport(rec.handler))
    d.poll_interval = 0
    res = await d.publish(
        SocialPost(
            channel=Channel.INSTAGRAM,
            text="Cap",
            media_urls=["https://a/1.jpg", "https://a/2.jpg"],
            media_kind="carousel",
        )
    )
    assert res.external_id == "M1" and res.url == "https://instagram.com/p/x"
    posts = [_form(c) for c in rec.calls if c.method == "POST"]
    assert posts[0]["is_carousel_item"] == "true" and posts[1]["is_carousel_item"] == "true"
    assert posts[2]["media_type"] == "CAROUSEL" and posts[2]["children"] == "C1,C2" and posts[2]["caption"] == "Cap"
    assert posts[3]["creation_id"] == "C3"


async def test_meta_instagram_needs_media(monkeypatch):
    monkeypatch.setattr(settings, "meta_ig_user_id", "IG1")
    monkeypatch.setattr(settings, "meta_page_token", "TOK")
    with pytest.raises(IntegrationError):
        await MetaDriver().publish(SocialPost(channel=Channel.INSTAGRAM, text="x"))


async def test_meta_threads_text(monkeypatch):
    monkeypatch.setattr(settings, "threads_user_id", "U1")
    monkeypatch.setattr(settings, "threads_access_token", "TT")
    rec = Recorder(
        {
            ("POST", "/U1/threads_publish"): {"id": "T9"},
            ("POST", "/U1/threads"): {"id": "CT"},
            ("GET", "/T9"): {"permalink": "https://threads.net/t/9"},
        }
    )
    res = await MetaDriver(transport=httpx.MockTransport(rec.handler)).publish(
        SocialPost(channel=Channel.THREADS, text="a" * 600)
    )
    assert res.external_id == "T9"
    first = _form(rec.calls[0])
    assert first["media_type"] == "TEXT" and len(first["text"]) == 500


async def test_meta_rate_limit_error_and_missing_config(monkeypatch):
    monkeypatch.setattr(settings, "meta_page_id", None)
    with pytest.raises(IntegrationNotConfigured):
        await MetaDriver().publish(SocialPost(channel=Channel.FACEBOOK, text="x"))
    monkeypatch.setattr(settings, "meta_page_id", "P1")
    monkeypatch.setattr(settings, "meta_page_token", "TOK")

    def throttled(req):
        return httpx.Response(400, json={"error": {"code": 32, "message": "Page request limit reached"}})

    d = MetaDriver(transport=httpx.MockTransport(throttled))
    with pytest.raises(rl.RateLimited):
        await d.publish(SocialPost(channel=Channel.FACEBOOK, text="x"))


def test_rate_limiter_window():
    lim = rl.RateLimiter()
    lim.check("k", limit=2, per_seconds=60, label="X")
    lim.check("k", limit=2, per_seconds=60, label="X")
    with pytest.raises(rl.RateLimited):
        lim.check("k", limit=2, per_seconds=60, label="X")


async def test_tiktok_pushes_video_to_inbox(monkeypatch):
    monkeypatch.setattr(settings, "tiktok_access_token", "ACT.abcdefgh")
    rec = Recorder(
        {("POST", "/post/publish/inbox/video/init/"): {"data": {"publish_id": "v_inbox_1"}, "error": {"code": "ok"}}}
    )
    d = TikTokDriver(transport=httpx.MockTransport(rec.handler))
    res = await d.publish(
        SocialPost(channel=Channel.TIKTOK, text="x", media_urls=["https://a/v.mp4"], media_kind="video", mode="draft")
    )
    assert res.status == "draft_pushed" and res.external_id == "v_inbox_1"
    body = json.loads(rec.calls[0].content)
    assert body == {"source_info": {"source": "PULL_FROM_URL", "video_url": "https://a/v.mp4"}}
    assert rec.calls[0].headers["authorization"] == "Bearer ACT.abcdefgh"
    with pytest.raises(IntegrationError, match="cần video"):
        await d.publish(SocialPost(channel=Channel.TIKTOK, text="chỉ có chữ"))


async def test_zalo_creates_and_verifies_article(monkeypatch):
    monkeypatch.setattr(settings, "zalo_oa_access_token", "ZTOK")
    rec = Recorder(
        {
            ("POST", "/article/create"): {"error": 0, "data": {"token": "tk1"}},
            ("POST", "/article/verify"): {"error": 0, "data": {"id": "art1"}},
        }
    )
    res = await ZaloDriver(transport=httpx.MockTransport(rec.handler)).publish(
        SocialPost(
            channel=Channel.ZALO_OA,
            text="Tin cho khách quen\nGiá 385.000đ",
            media_urls=["https://a/1.jpg"],
            media_kind="image",
        )
    )
    assert res.external_id == "art1"
    art = json.loads(rec.calls[0].content)
    assert art["title"] == "Tin cho khách quen" and art["cover"]["photo_url"] == "https://a/1.jpg"
    assert rec.calls[0].headers["access_token"] == "ZTOK"
    assert len(rec.calls) == 2  # không gửi broadcast khi chưa bật


# ---- luật soát lời -----------------------------------------------------------------------------------------------

PF = ProductFacts(id="1", name="Bình", price_vnd=385_000, compare_at_price_vnd=450_000, trial_days=21)


def test_money_mentions():
    vals = [v for _, v in money_mentions("Giá 385k, giá thường 450.000đ, chỉ 1,2 triệu cho 3 cái, 480 ml")]
    assert vals == [385_000, 450_000, 1_200_000]


def test_numbers_and_claims():
    assert check_numbers("Mình thử 5 chiếc trong 3 tuần, giá 385.000đ, bớt 65k", PF, None) == []
    probs = check_numbers("Mình thử 7 chiếc trong 2 tháng, giá 350k", PF, None)
    assert len(probs) == 2  # thời gian thử + giá; số món đã thử thuộc mục «quá trình chọn»
    assert check_claims("Không chữa bệnh gì đâu") and check_claims("Bình TỐT NHẤT") and not check_claims("Bình tốt")


def test_process_mentions_flagged():
    assert check_process("Mình dùng 3 tuần rồi mới chọn. Vì sao mình chọn: nắp tháo rời.") == []
    probs = check_process(
        "Thử 6 mẫu, chọn 1 trong 24. Xem hồ sơ chọn ở link. Mẫu bị loại thì nóng nhanh, mình đã xem 30 món, so kỹ."
    )
    assert len(probs) == 6
    for q in ("Thử 6 mẫu", "hồ sơ chọn", "Mẫu bị loại", "xem 30 món", "so kỹ", "chọn 1 trong 24"):
        assert any(q in p for p in probs), q
    f = build_findings(
        channel=Channel.THREADS,
        title=None,
        body="Thử 6 mẫu, giữ lại một chiếc. Bạn thấy sao?",
        hashtags=[],
        script=[],
        product=PF,
        drop=None,
        ai_generated=True,
        ai=None,
    )
    chip = next(x for x in f if x["key"] == "process")
    assert not chip["ok"] and chip["suggestion"] and status_of(f) == CheckStatus.FAILED


def test_findings_status_and_override_kept():
    f = build_findings(
        channel=Channel.FACEBOOK,
        title=None,
        body="Bình tốt nhất " + "x" * 200,
        hashtags=[],
        script=[],
        product=PF,
        drop=None,
        ai_generated=True,
        ai=None,
    )
    assert status_of(f) == CheckStatus.FAILED
    for x in f:
        if not x["ok"]:
            x.update(overridden=True, override_reason="ok")
    assert status_of(f) == CheckStatus.WARNINGS
    again = build_findings(
        channel=Channel.FACEBOOK,
        title=None,
        body="Bình tốt nhất " + "x" * 200,
        hashtags=[],
        script=[],
        product=PF,
        drop=None,
        ai_generated=True,
        ai=None,
        previous=f,
    )
    assert status_of(again) == CheckStatus.WARNINGS
