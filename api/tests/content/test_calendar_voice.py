"""Lịch đăng (f3) + Giọng của chị (f2)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.timeutil import local_today, now_utc, to_local, week_start
from app.modules.content.models import ContentDraft, DraftStatus, ScheduledPost, VoiceProfile
from app.modules.content.service import ACTION_SUGGEST, ACTION_VOICE
from app.modules.control.models import AIActivity, ApprovalItem, ApprovalStatus


async def test_calendar_week_view_and_slots(product_factory, owner_client):
    p = await product_factory()
    await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})
    async with SessionLocal() as db:
        posts = list((await db.execute(select(ScheduledPost))).scalars())
    days = [to_local(x.scheduled_at).date() for x in posts]
    assert all(d.weekday() != 6 for d in days), "Chủ nhật nghỉ"
    assert len({(d, x.channel) for d, x in zip(days, posts, strict=True)}) == 5
    for d in set(days):
        assert days.count(d) <= 3, "tối đa 3 bài/ngày"
    hours = {x.channel.value: to_local(x.scheduled_at).strftime("%H:%M") for x in posts}
    assert hours["facebook"] == "20:00" and hours["instagram"] == "12:00" and hours["zalo_oa"] == "19:30"

    wk = min(days)
    cal = (await owner_client.get("/api/desk/content/calendar", params={"week": wk.isoformat()})).json()
    assert len(cal["days"]) == 7 and cal["days"][6]["rest"] is True
    cards = [c for d in cal["days"] for c in d["posts"]]
    assert cards and all(c["display_status"] == "pending" for c in cards)
    assert {b["source"] for b in cal["best_times"]} == {"default"}


async def test_plan_week_suggests_empty_days_and_accept(product_factory, owner_client):
    await product_factory()
    ws = week_start(local_today() + timedelta(days=7))
    r = await owner_client.post("/api/desk/content/calendar/plan", json={"week": ws.isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["suggested"] == 6  # T2–T7 trống
    r2 = await owner_client.post("/api/desk/content/calendar/plan", json={"week": ws.isoformat()})
    assert r2.json()["suggested"] == 0  # không gợi ý trùng
    cal = (await owner_client.get("/api/desk/content/calendar", params={"week": ws.isoformat()})).json()
    sugg = [s for d in cal["days"] for s in d["suggestions"]]
    assert len(sugg) == 6 and all(s["idea"] for s in sugg)

    first = sugg[0]
    r = await owner_client.post(f"/api/desk/content/calendar/suggestions/{first['id']}/accept")
    assert r.status_code == 200, r.text
    day = next(d for d in r.json()["days"] if d["day"] == to_local_iso(first["slot_at"]))
    assert len(day["posts"]) == 1 and not day["suggestions"]
    assert day["posts"][0]["channel"] == first["channel"]

    r = await owner_client.post(f"/api/desk/content/calendar/suggestions/{sugg[1]['id']}/dismiss")
    assert r.status_code == 204
    async with SessionLocal() as db:
        st = (await db.get(ApprovalItem, sugg[1]["id"])).status
    assert st == ApprovalStatus.RETURNED


def to_local_iso(s: str) -> str:
    from datetime import datetime

    return to_local(datetime.fromisoformat(s)).date().isoformat()


async def test_plan_week_moves_clashing_planned_posts(product_factory, owner_client):
    p = await product_factory()
    detail = (await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})).json()
    ids = [d["post"]["id"] for d in detail["drafts"][:2]]
    async with SessionLocal() as db:  # đẩy hai bài vào giờ đã qua
        for pid in ids:
            x = await db.get(ScheduledPost, pid)
            x.scheduled_at = now_utc() - timedelta(hours=2)
        await db.commit()
    r = await owner_client.post("/api/desk/content/calendar/plan", json={})
    assert r.json()["moved"] >= 2
    async with SessionLocal() as db:
        for pid in ids:
            assert (await db.get(ScheduledPost, pid)).scheduled_at > now_utc()


async def test_suggestion_accept_owner_only(product_factory, helper_client, owner_client):
    await product_factory()
    ws = week_start(local_today() + timedelta(days=7))
    await helper_client.post("/api/desk/content/calendar/plan", json={"week": ws.isoformat()})
    async with SessionLocal() as db:
        item = await db.scalar(select(ApprovalItem).where(ApprovalItem.action == ACTION_SUGGEST))
    r = await helper_client.post(f"/api/desk/content/calendar/suggestions/{item.id}/accept")
    assert r.status_code == 403


SAMPLES = [
    "Cả nhà ơi, mình mới thử cái giá phơi này 2 tuần. Phơi chăn mùa đông không võng. Gấp lại dày 6 cm, dựng sau cửa. Ai cần nhắn mình nha?",
    "Mình dùng hộp cơm này mang đi làm cả tháng. Nắp kín, không đổ canh. Mỗi tội hơi nặng. Cả nhà thấy sao?",
]


async def test_learn_voice_and_use_in_compose(product_factory, owner_client, helper_client):
    r = await helper_client.post("/api/desk/content/voice/learn", json={"samples": SAMPLES})
    assert r.status_code == 403
    r = await owner_client.post("/api/desk/content/voice/learn", json={"samples": []})
    assert r.status_code == 400
    r = await owner_client.post(
        "/api/desk/content/voice/learn", json={"samples": SAMPLES, "notes": "Không dùng chữ «siêu phẩm»"}
    )
    assert r.status_code == 200, r.text
    v = r.json()["voice"]
    assert r.json()["status"] == "applied"
    assert "mình" in v["pronouns"] and "cả nhà" in v["pronouns"]
    assert any("siêu phẩm" in a for a in v["avoid"]) and v["examples"] and v["version"] == 2
    assert v["samples_count"] == 3  # 2 bài + 1 ghi chú

    r = await owner_client.patch(
        "/api/desk/content/voice", json={"rules": ["Luôn nói giá cuối bài"], "pronouns": "Xưng «mình» – gọi «cả nhà»"}
    )
    assert r.status_code == 200 and r.json()["rules"] == ["Luôn nói giá cuối bài"] and r.json()["avoid"] == v["avoid"]

    p = await product_factory()
    await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})
    async with SessionLocal() as db:
        vp = await db.scalar(select(VoiceProfile))
        d = await db.scalar(select(ContentDraft).where(ContentDraft.status != DraftStatus.ARCHIVED).limit(1))
    assert d.voice_profile_id == vp.id

    async with SessionLocal() as db:  # hoàn tác lần học (nhật ký AI)
        act = await db.scalar(select(AIActivity).where(AIActivity.action == ACTION_VOICE))
    assert act.undoable
    r = await owner_client.post(f"/api/desk/control/activity/{act.id}/undo")
    assert r.status_code == 200, r.text
    v2 = (await owner_client.get("/api/desk/content/voice")).json()
    assert v2["samples_count"] == 0
