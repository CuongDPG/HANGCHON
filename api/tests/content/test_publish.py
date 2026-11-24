"""Đăng tự động (f4) + Đo và học (f7)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core import events
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.enums import Channel
from app.core.jobs import JOBS, job_context
from app.core.timeutil import now_utc
from app.integrations import get_driver
from app.integrations.base import IntegrationError
from app.modules.content.models import ContentDraft, ContentInsight, DraftStatus, PostMetric, PostStatus, ScheduledPost
from app.modules.content.publishing import AI_LABEL, driver_for
from app.modules.content.service import ACTION_RETRY
from app.modules.control.models import ApprovalItem, ApprovalStatus
from app.modules.orders.models import Order, OrderStatus


async def _compose_and_approve(owner_client, product, channels=None):
    detail = (await owner_client.post(f"/api/desk/content/studio/product/{product.id}/compose", json={})).json()
    out = {}
    for d in detail["drafts"]:
        if channels and d["channel"] not in channels:
            continue
        r = await owner_client.post(f"/api/desk/content/drafts/{d['id']}/approve", json={})
        assert r.status_code == 200, r.text
        out[d["channel"]] = r.json()
    return out


async def _make_due(post_ids):
    async with SessionLocal() as db:
        for pid in post_ids:
            p = await db.get(ScheduledPost, pid)
            p.scheduled_at = now_utc() - timedelta(minutes=1)
        await db.commit()


@pytest.fixture
def seen_published():
    got: list[str] = []

    @events.on("post.published")
    async def _listen(db, payload):
        got.append(payload["scheduled_post_id"])

    yield got
    events._handlers["post.published"].remove(_listen)


async def test_publish_due_posts_and_tiktok_draft(product_factory, owner_client, seen_published):
    p = await product_factory()
    approved = await _compose_and_approve(owner_client, p, ["facebook", "tiktok"])
    fb_post, tt_post = approved["facebook"]["post"]["id"], approved["tiktok"]["post"]["id"]
    assert await JOBS["content.publish_due"](job_context()) == 0  # chưa tới giờ
    await _make_due([fb_post, tt_post])
    assert await JOBS["content.publish_due"](job_context()) == 2
    async with SessionLocal() as db:
        fb = await db.get(ScheduledPost, fb_post)
        tt = await db.get(ScheduledPost, tt_post)
        draft = await db.get(ContentDraft, fb.draft_id)
    assert fb.status == PostStatus.PUBLISHED and fb.external_post_id and fb.ai_label_applied
    assert draft.status == DraftStatus.PUBLISHED
    assert tt.status == PostStatus.DRAFT_PUSHED and tt.external_url is None
    assert seen_published == [fb_post]  # TikTok mới đẩy nháp, chưa phát
    sent = [sp for sp, _ in get_driver("social").published]
    fb_sp = next(sp for sp in sent if sp.channel == Channel.FACEBOOK)
    assert AI_LABEL in fb_sp.text and fb_sp.link_url and "?src=" in fb_sp.link_url
    assert next(sp for sp in sent if sp.channel == Channel.TIKTOK).mode == "draft"

    # chị bấm đăng trong app TikTok rồi báo lại
    r = await owner_client.post(
        f"/api/desk/content/posts/{tt_post}/mark-published", json={"url": "https://www.tiktok.com/@x/video/1"}
    )
    assert r.status_code == 200 and r.json()["display_status"] == "published"
    assert seen_published == [fb_post, tt_post]
    r = await owner_client.post(f"/api/desk/content/posts/{fb_post}/mark-published", json={})
    assert r.status_code == 409


async def test_publish_failure_retries_then_asks(product_factory, owner_client, monkeypatch):
    p = await product_factory()
    approved = await _compose_and_approve(owner_client, p, ["facebook"])
    pid = approved["facebook"]["post"]["id"]
    drv = get_driver("social")

    async def boom(post):
        raise IntegrationError("Facebook đang bảo trì")

    monkeypatch.setattr(drv, "publish", boom)
    for attempt in range(1, 4):
        async with SessionLocal() as db:  # tua thời gian: lần thử trước đã qua thời gian chờ
            x = await db.get(ScheduledPost, pid)
            x.scheduled_at = now_utc() - timedelta(minutes=1)
            x.updated_at = now_utc() - timedelta(hours=1)
            await db.commit()
        await JOBS["content.publish_due"](job_context())
        async with SessionLocal() as db:
            x = await db.get(ScheduledPost, pid)
        assert x.attempts == attempt
    assert x.status == PostStatus.FAILED and "bảo trì" in x.error
    async with SessionLocal() as db:
        item = await db.scalar(select(ApprovalItem).where(ApprovalItem.action == ACTION_RETRY))
    assert item.status == ApprovalStatus.PENDING

    monkeypatch.undo()
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    assert r.json()["status"] == "approved", r.text
    async with SessionLocal() as db:
        x = await db.get(ScheduledPost, pid)
    assert x.status == PostStatus.PUBLISHED


async def test_metrics_attribution_and_insights(product_factory, owner_client):
    p = await product_factory()
    approved = await _compose_and_approve(owner_client, p, ["facebook", "instagram"])
    ids = [approved["facebook"]["post"]["id"], approved["instagram"]["post"]["id"]]
    await _make_due(ids)
    await JOBS["content.publish_due"](job_context())
    fb_code = approved["facebook"]["src_code"]
    async with SessionLocal() as db:
        for i, st in enumerate([OrderStatus.CONFIRMED, OrderStatus.DELIVERED, OrderStatus.CANCELLED]):
            db.add(
                Order(
                    code=f"HCT{i}",
                    recipient_name="Khách thử",
                    recipient_phone="0900000000",
                    placed_at=now_utc(),
                    total_vnd=385_000,
                    status=st,
                    raw={"src": fb_code.upper()},
                )
            )
        await db.commit()
    assert await JOBS["content.pull_metrics"](job_context()) == 2
    async with SessionLocal() as db:
        m = await db.scalar(select(PostMetric).where(PostMetric.scheduled_post_id == ids[0]))
    assert m.orders_attributed == 2 and m.revenue_attributed_vnd == 770_000 and m.reach > 0

    perf = (await owner_client.get("/api/desk/content/performance")).json()
    assert perf["posts"][0]["scheduled_post_id"] == ids[0]  # bài ra đơn lên đầu
    assert perf["totals"]["orders"] == 2

    r = await owner_client.post("/api/desk/content/insights/run")
    assert r.status_code == 200, r.text
    ins = r.json()
    assert 2 <= len(ins["findings"]) <= 3 and "Facebook" in ins["findings"][0]["pattern"]
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count(ContentInsight.id))) == 1


async def test_driver_for_channel_mapping(monkeypatch):
    assert driver_for(Channel.FACEBOOK).name == "mock"
    monkeypatch.setattr(settings, "social_channel_drivers", "facebook=meta, tiktok=tiktok_draft_publish")
    assert driver_for(Channel.FACEBOOK).name == "meta"
    assert driver_for(Channel.TIKTOK).name == "tiktok_draft"  # tên cũ vẫn hiểu
    assert driver_for(Channel.INSTAGRAM).name == "mock"
    # cùng một cấu hình cho hộp thư
    from app.modules.inbox.channels import messaging_driver

    assert messaging_driver("mock", Channel.FACEBOOK).name == "meta"
    assert messaging_driver("mock", Channel.ZALO_OA).name == "mock"


async def test_reschedule_and_cancel(product_factory, owner_client):
    p = await product_factory()
    approved = await _compose_and_approve(owner_client, p, ["threads"])
    pid = approved["threads"]["post"]["id"]
    new = (now_utc() + timedelta(days=2)).replace(microsecond=0)
    r = await owner_client.patch(f"/api/desk/content/posts/{pid}", json={"scheduled_at": new.isoformat()})
    assert r.status_code == 200 and r.json()["display_status"] == "approved"
    r = await owner_client.patch(
        f"/api/desk/content/posts/{pid}", json={"scheduled_at": (now_utc() - timedelta(hours=1)).isoformat()}
    )
    assert r.status_code == 400
    r = await owner_client.post(f"/api/desk/content/posts/{pid}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"


async def test_publish_now(product_factory, owner_client):
    p = await product_factory()
    approved = await _compose_and_approve(owner_client, p, ["zalo_oa"])
    r = await owner_client.post(f"/api/desk/content/posts/{approved['zalo_oa']['post']['id']}/publish-now")
    assert r.status_code == 200 and r.json()["status"] == "published"
