"""Bảng theo dõi nội dung theo món (Xưởng): trạng thái từng kênh, bước công việc, số liệu bài, không N+1."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import event, func, select

from app.core.db import SessionLocal, engine
from app.core.jobs import JOBS, job_context
from app.core.timeutil import now_utc
from app.modules.catalog.models import ProductStatus
from app.modules.content.models import ContentDraft, PostMetric, PostStatus, ScheduledPost
from app.modules.orders.models import Order, OrderStatus

B = "/api/desk/content/board"


def _row(data, ref_id):
    return next(r for r in data["items"] if r["id"] == str(ref_id))


def _cell(row, channel):
    return next(c for c in row["channels"] if c["channel"] == channel)


async def test_board_states_stages_and_kpis(product_factory, owner_client):
    fresh = await product_factory(name="Khay đá silicon", status=ProductStatus.PENDING_REVIEW)
    gone = await product_factory(name="Món đã ngừng", status=ProductStatus.STOPPED)
    p = await product_factory()

    data = (await owner_client.get(B)).json()
    assert all(r["id"] != str(gone.id) for r in data["items"])
    row = _row(data, fresh.id)
    assert [c["channel"] for c in row["channels"]] == [
        "website",
        "facebook",
        "instagram",
        "threads",
        "tiktok",
        "zalo_oa",
    ]
    assert _cell(row, "website")["state"] == "pending" and _cell(row, "facebook")["state"] == "none"
    assert row["stage"] == "review"  # trang website chờ chị duyệt trước
    assert _row(data, p.id)["stage"] == "todo"  # trang đã đăng, các kênh chưa có bài

    detail = (await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})).json()
    drafts = {d["channel"]: d for d in detail["drafts"]}
    for ch in ("facebook", "instagram"):
        r = await owner_client.post(f"/api/desk/content/drafts/{drafts[ch]['id']}/approve", json={})
        assert r.status_code == 200, r.text
    fb_post, ig_post = drafts["facebook"]["post"]["id"], drafts["instagram"]["post"]["id"]

    row = _row((await owner_client.get(B)).json(), p.id)
    fb = _cell(row, "facebook")
    assert fb["state"] == "scheduled" and fb["scheduled_at"] and fb["approved_at"] and fb["created_at"]
    assert _cell(row, "threads")["state"] == "pending" and row["stage"] == "review"

    # Facebook lên kênh, có số liệu và 1 đơn gắn mã bài; Instagram đăng lỗi
    async with SessionLocal() as db:
        for pid in (fb_post, ig_post):
            x = await db.get(ScheduledPost, pid)
            x.scheduled_at = now_utc() - timedelta(minutes=1)
        await db.commit()
    await JOBS["content.publish_due"](job_context())
    async with SessionLocal() as db:
        ig = await db.get(ScheduledPost, ig_post)
        ig.status, ig.error = PostStatus.FAILED, "Instagram đang bảo trì"
        db.add(
            PostMetric(
                scheduled_post_id=fb_post,
                captured_at=now_utc(),
                reach=1200,
                likes=40,
                comments=5,
                shares=3,
                saves=2,
                clicks=30,
            )
        )
        db.add(
            Order(
                code="HCB1",
                recipient_name="Khách thử",
                recipient_phone="0900000000",
                placed_at=now_utc(),
                total_vnd=385_000,
                status=OrderStatus.CONFIRMED,
                raw={"src": drafts["facebook"]["src_code"]},
            )
        )
        await db.commit()

    row = _row((await owner_client.get(B)).json(), p.id)
    fb = _cell(row, "facebook")
    assert fb["state"] == "published" and fb["published_at"] and fb["external_url"]
    assert fb["kpi"] == {
        "posts": 1,
        "reach": 1200,
        "interactions": 50,
        "clicks": 30,
        "orders": 1,
        "revenue_vnd": 385_000,
        "measured_at": fb["kpi"]["measured_at"],
    }
    assert _cell(row, "instagram")["state"] == "failed" and "bảo trì" in _cell(row, "instagram")["error"]
    assert row["kpi"]["orders"] == 1 and row["kpi"]["reach"] == 1200 and row["kpi"]["posts"] == 1

    # Hồ sơ nội dung (studio) mang cùng dòng theo dõi
    tr = (await owner_client.get(f"/api/desk/content/studio/product/{p.id}")).json()["tracking"]
    assert _cell(tr, "facebook")["kpi"]["orders"] == 1 and tr["stage"] == "review"

    # lọc theo kênh: bước tính riêng trên kênh đó
    fb_only = (await owner_client.get(B, params={"channel": "facebook", "tab": "published"})).json()
    assert [r["id"] for r in fb_only["items"]] == [str(p.id)]
    assert fb_only["counts"]["published"] == 1


async def test_board_tabs_counts_search_and_pages(product_factory, owner_client):
    a = await product_factory(name="Bình giữ nhiệt 480 ml")
    b = await product_factory(name="Hộp cơm inox 3 ngăn")
    c = await product_factory(name="Khăn lau bếp", status=ProductStatus.DRAFT)
    data = (await owner_client.get(B)).json()
    assert data["counts"] == {"todo": 3, "review": 0, "scheduled": 0, "published": 0, "all": 3}
    assert _cell(_row(data, c.id), "website")["state"] == "drafting"

    todo = (await owner_client.get(B, params={"tab": "todo"})).json()
    assert {r["id"] for r in todo["items"]} == {str(a.id), str(b.id), str(c.id)} and todo["total"] == 3

    found = (await owner_client.get(B, params={"q": "hop com"})).json()  # không dấu
    assert [r["id"] for r in found["items"]] == [str(b.id)] and found["counts"]["all"] == 1

    p1 = (await owner_client.get(B, params={"size": 2, "page": 1})).json()
    p2 = (await owner_client.get(B, params={"size": 2, "page": 2})).json()
    assert p1["pages"] == 2 and len(p1["items"]) == 2 and len(p2["items"]) == 1
    assert (await owner_client.get(B, params={"tab": "x"})).status_code == 422


async def test_board_drop_row_has_only_drop_channels(product_factory, drop_factory, owner_client):
    d = await drop_factory([await product_factory()])
    row = _row((await owner_client.get(B)).json(), d.id)
    assert row["kind"] == "drop" and _cell(row, "website")["state"] == "published"
    assert _cell(row, "threads")["state"] == "na" and _cell(row, "tiktok")["state"] == "na"
    assert _cell(row, "facebook")["state"] == "none"


async def test_board_query_count_does_not_grow_per_product(product_factory, owner_client):
    async def count_queries() -> int:
        n = 0

        def on_exec(*_a, **_k):
            nonlocal n
            n += 1

        event.listen(engine.sync_engine, "before_cursor_execute", on_exec)
        try:
            r = await owner_client.get(B)
            assert r.status_code == 200, r.text
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", on_exec)
        return n

    p = await product_factory()
    await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})
    one = await count_queries()
    for _ in range(4):
        q = await product_factory()
        await owner_client.post(f"/api/desk/content/studio/product/{q.id}/compose", json={})
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count(ContentDraft.id))) == 25
    assert await count_queries() == one


async def test_board_requires_login(client):
    assert (await client.get(B)).status_code == 401


async def test_board_tiktok_draft_pushed_counts_as_scheduled(product_factory, owner_client):
    p = await product_factory()
    detail = (await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})).json()
    tt = next(d for d in detail["drafts"] if d["channel"] == "tiktok")
    r = await owner_client.post(f"/api/desk/content/drafts/{tt['id']}/approve", json={})
    assert r.status_code == 200, r.text
    async with SessionLocal() as db:
        x = await db.get(ScheduledPost, tt["post"]["id"])
        x.status = PostStatus.DRAFT_PUSHED
        await db.commit()

    data = (await owner_client.get(B)).json()
    cell = _cell(_row(data, p.id), "tiktok")
    assert cell["state"] == "scheduled" and cell["raw"] == "draft_pushed" and cell["scheduled_at"]
    tr = (await owner_client.get(f"/api/desk/content/studio/product/{p.id}")).json()["tracking"]
    assert _cell(tr, "tiktok")["state"] == "scheduled"

    async with SessionLocal() as db:
        x = await db.get(ScheduledPost, tt["post"]["id"])
        x.status, x.error = PostStatus.FAILED, "lỗi"
        await db.commit()
    assert _cell(_row((await owner_client.get(B)).json(), p.id), "tiktok")["state"] == "failed"
