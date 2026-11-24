"""i5 — báo cáo tuần: số liệu từ sổ + đơn + bài đăng + chi phí AI + hàng chờ duyệt; AI viết nhận xét qua control."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import httpx
from sqlalchemy import select

from app import ai
from app.core.db import SessionLocal
from app.core.enums import Channel
from app.core.timeutil import VN_TZ, local_today, now_utc, week_start
from app.modules.content.models import ContentDraft, DraftFormat, PostMetric, ScheduledPost
from app.modules.control.models import AIRun, ApprovalItem, ApprovalStatus, User
from app.modules.finance import jobs
from app.modules.finance.models import WeeklyReport
from tests.finance.factory import make_customer, make_order, pay

WS = week_start(local_today())


def _at(days: int, hour: int = 10) -> datetime:
    return datetime.combine(WS + timedelta(days=days), time(hour), tzinfo=VN_TZ)


async def test_empty_week_still_makes_a_report(owner_client: httpx.AsyncClient) -> None:
    r = await owner_client.post("/api/desk/finance/reports/generate", json={})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["status"] == "ready" and rep["week_start"] == WS.isoformat()
    assert rep["revenue_vnd"] == 0 and rep["order_count"] == 0 and rep["product_margins"] == []
    assert rep["metrics"]["returning_order_pct"] is None and rep["metrics"]["gross_margin_pct"] is None
    assert 1 <= len(rep["highlights"]) <= 3 and "chưa có đơn" in rep["summary"]
    listed = (await owner_client.get("/api/desk/finance/reports")).json()
    assert listed["total"] == 1


async def test_week_numbers_from_orders_posts_ai_and_reviews(owner_client: httpx.AsyncClient, owner: User) -> None:
    async with SessionLocal() as db:
        old, new = await make_customer(db, "Khách cũ"), await make_customer(db, "Khách mới")
        # khách cũ có đơn tuần trước → đơn tuần này tính là «từ khách cũ»
        await make_order(db, customer=old, paid_at=_at(-5), placed_at=_at(-5, 9))
        a = await make_order(db, customer=old, paid_at=_at(1),
                             items=[("Bình giữ nhiệt 480 ml", 2, 245_000, 160_000)], shipping=0)  # fmt: skip
        b = await make_order(db, customer=new, paid_at=_at(2),
                             items=[("Bình giữ nhiệt 480 ml", 1, 245_000, 160_000), ("Hộp cơm inox", 1, 300_000, None)],
                             shipping=0)  # fmt: skip
        for o in (a, b):
            await pay(db, o)
        draft = ContentDraft(channel=Channel.FACEBOOK, format=DraftFormat.POST, title="3 tuần thử 5 chiếc bình")
        db.add(draft)
        await db.flush()
        post = ScheduledPost(draft_id=draft.id, channel=Channel.FACEBOOK, scheduled_at=_at(0), published_at=_at(0))
        db.add(post)
        await db.flush()
        db.add(PostMetric(scheduled_post_id=post.id, captured_at=_at(1), orders_attributed=1))
        db.add(
            PostMetric(
                scheduled_post_id=post.id, captured_at=_at(3), orders_attributed=2, revenue_attributed_vnd=790_000
            )
        )
        r1 = AIRun(task="x", provider="fake", model="fake", tier="fast", status="ok", cost_vnd=12_000)
        db.add(r1)
        await db.flush()
        r1.created_at = _at(1)
        for edited, st in (
            (None, ApprovalStatus.APPROVED),
            ({"a": 1}, ApprovalStatus.APPROVED),
            (None, ApprovalStatus.RETURNED),
        ):
            db.add(ApprovalItem(action="x.y", module="x", title="t", status=st, edited_payload=edited,
                                decided_at=_at(2), decided_by_id=owner.id))  # fmt: skip
        await db.commit()

    rep = (await owner_client.post("/api/desk/finance/reports/generate", json={"week_start": WS.isoformat()})).json()
    assert rep["order_count"] == 2 and rep["revenue_vnd"] == 1_035_000 and rep["customer_count"] == 2
    assert rep["cogs_vnd"] == 480_000 and rep["gross_profit_vnd"] == 555_000
    assert rep["returning_customer_count"] == 1 and rep["metrics"]["returning_order_pct"] == 50.0
    assert rep["metrics"]["cogs_missing_items"] == 1 and rep["metrics"]["gross_margin_pct"] is None
    top = rep["product_margins"][0]
    assert (
        top["name"] == "Bình giữ nhiệt 480 ml" and top["orders"] == 2 and top["qty"] == 3 and top["margin_pct"] == 34.7
    )
    assert next(m for m in rep["product_margins"] if m["name"] == "Hộp cơm inox")["margin_pct"] is None
    assert rep["top_posts"] == [
        {"scheduled_post_id": str(post.id), "title": "3 tuần thử 5 chiếc bình", "channel": "facebook", "orders": 2,
         "revenue_vnd": 790_000, "url": None}
    ]  # fmt: skip
    assert rep["ai_cost_vnd"] >= 12_000
    assert rep["metrics"]["review_decisions"] == 3 and rep["metrics"]["review_minutes"] == 4  # 40+120+60 giây
    assert any("Bình giữ nhiệt" in h for h in rep["highlights"])
    # chạy lại cùng tuần → cập nhật, không tạo dòng mới
    await owner_client.post("/api/desk/finance/reports/generate", json={"week_start": WS.isoformat()})
    async with SessionLocal() as s:
        assert len(list((await s.execute(select(WeeklyReport))).scalars())) == 1


async def test_insights_wait_for_approval_when_ask(owner_client: httpx.AsyncClient) -> None:
    await owner_client.patch("/api/desk/control/autonomy/finance.weekly_insights", json={"level": "ask"})
    rep = (await owner_client.post("/api/desk/finance/reports/generate", json={})).json()
    assert rep["highlights"] == [] and rep["metrics"]["insight_status"] == "pending"
    item = (await owner_client.get("/api/desk/control/approvals?action=finance.weekly_insights")).json()["items"][0]
    assert item["preview"]["list"]
    await owner_client.post(
        f"/api/desk/control/approvals/{item['id']}/approve", json={"payload": {"highlights": ["Sửa tay"]}}
    )
    rep = (await owner_client.get(f"/api/desk/finance/reports/{rep['id']}")).json()
    assert rep["highlights"] == ["Sửa tay"] and "insight_status" not in rep["metrics"]


async def test_ai_error_keeps_numbers(owner_client: httpx.AsyncClient, fake_ai: dict) -> None:
    def refuse(_inp):
        raise ai.FakeRefusal("cyber")

    fake_ai["finance.weekly_insights"] = refuse
    rep = (await owner_client.post("/api/desk/finance/reports/generate", json={})).json()
    assert rep["status"] == "ready" and rep["highlights"] == [] and rep["metrics"]["insight_error"]


async def test_cron_makes_last_week_report_and_permissions(helper_client: httpx.AsyncClient) -> None:
    rid = await jobs.weekly_report({"db": SessionLocal})
    async with SessionLocal() as s:
        rep = await s.get(WeeklyReport, rid)
        assert rep.week_start == WS - timedelta(days=7) and rep.week_end == WS - timedelta(days=1)
    assert (await helper_client.get("/api/desk/finance/reports")).json()["total"] == 1
    assert (await helper_client.post("/api/desk/finance/reports/generate", json={})).status_code == 403
    assert (await helper_client.get(f"/api/desk/finance/reports/{rid}")).status_code == 200
    assert now_utc()  # giữ import
