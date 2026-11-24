"""a5 radar xu hướng · a6 nghe khách muốn gì (sự kiện message.received, find_request.created/threshold)."""

from __future__ import annotations

import uuid

from app.core import events
from app.core.db import SessionLocal
from app.core.enums import Actor, Channel
from app.core.timeutil import now_utc
from app.modules.catalog.models import FindRequest, FindRequestStatus
from app.modules.inbox.models import Direction, Intent, Message, Thread, ThreadKind
from app.modules.sourcing import jobs
from app.modules.sourcing.models import DemandMention, DemandSignal, TrendSignal
from tests.sourcing.util import API


async def test_trend_radar_and_open_brief(owner_client):
    run = (await owner_client.post(f"{API}/trends/refresh")).json()
    assert run["kind"] == "trend_radar" and run["status"] == "succeeded"
    trends = (await owner_client.get(f"{API}/trends")).json()["items"]
    assert trends and all(t["reason"] for t in trends)
    assert all("lượt nhắc" in t["reason"] for t in trends)
    total = len(trends)
    await owner_client.post(f"{API}/trends/refresh")  # cùng ngày → không sinh trùng
    assert (await owner_client.get(f"{API}/trends")).json()["total"] == total
    t = trends[0]
    r = await owner_client.post(f"{API}/trends/{t['id']}/brief")
    assert r.status_code == 201
    brief = r.json()
    assert brief["input_mode"] == "trend" and brief["status"] == "draft"
    assert brief["filters"]["trend_signal_id"] == t["id"]
    t2 = next(x for x in (await owner_client.get(f"{API}/trends")).json()["items"] if x["id"] == t["id"])
    assert t2["status"] == "watching" and t2["brief_id"] == brief["id"]
    await owner_client.post(f"{API}/briefs/{brief['id']}/run")
    t3 = next(x for x in (await owner_client.get(f"{API}/trends")).json()["items"] if x["id"] == t["id"])
    assert t3["status"] == "converted" and t3["candidate_id"]
    r = await owner_client.post(f"{API}/trends/{trends[1]['id']}/dismiss")
    assert r.json()["status"] == "dismissed"
    assert (await owner_client.get(f"{API}/trends")).json()["total"] == total - 1


async def test_trend_cron(db):
    await jobs.trend_radar_daily({"db": SessionLocal})
    assert (await db.execute(TrendSignal.__table__.select())).first() is not None


async def _message(db, body: str, *, thread: Thread | None = None, direction=Direction.INBOUND, intent=None):
    if thread is None:
        thread = Thread(channel=Channel.FACEBOOK, kind=ThreadKind.DIRECT_MESSAGE, external_thread_id=uuid.uuid4().hex)
        db.add(thread)
        await db.flush()
    m = Message(
        thread_id=thread.id,
        direction=direction,
        sender=Actor.CUSTOMER if direction == Direction.INBOUND else Actor.OWNER,
        body=body,
        sent_at=now_utc(),
        intent=intent,
    )
    db.add(m)
    await db.flush()
    return thread, m


async def _emit_msg(db, thread, m):
    await events.emit("message.received", {"thread_id": str(thread.id), "message_id": str(m.id)}, db=db)


async def test_message_received_builds_demand(db, owner_client):
    t1, m1 = await _message(db, "Shop có bán giá phơi gấp gọn không ạ, nhà em ban công bé")
    await _emit_msg(db, t1, m1)
    await _emit_msg(db, t1, m1)  # lặp lại sự kiện → không trùng
    _, m2 = await _message(db, "Chị ơi còn giá phơi gấp gọn inox không", thread=t1)
    await _emit_msg(db, t1, m2)
    t3, m3 = await _message(db, "Có giá phơi gấp gọn treo lan can không shop")
    await _emit_msg(db, t3, m3)
    t4, m4 = await _message(db, "Bao giờ đơn của em giao vậy ạ")
    await _emit_msg(db, t4, m4)
    t5, m5 = await _message(db, "Có bán giá phơi không", direction=Direction.OUTBOUND)
    await _emit_msg(db, t5, m5)
    t6, m6 = await _message(db, "shop có bán giá phơi không", intent=Intent.ASK_PRICE)
    await _emit_msg(db, t6, m6)
    await db.commit()
    items = (await owner_client.get(f"{API}/demand")).json()["items"]
    assert len(items) == 1
    s = items[0]
    assert s["title"].startswith("giá phơi gấp gọn")
    assert s["mention_count"] == 3 and s["ask_count"] == 2  # hai hội thoại khác nhau
    assert len(s["mentions"]) == 3
    r = await owner_client.post(f"{API}/demand/{s['id']}/brief")
    assert r.status_code == 201
    assert r.json()["input_mode"] == "demand" and r.json()["demand_signal_id"] == s["id"]
    s2 = (await owner_client.get(f"{API}/demand")).json()["items"][0]
    assert s2["status"] == "searching" and s2["brief_id"] == r.json()["id"]
    # mở lại lần nữa → trả đúng đề cũ
    assert (await owner_client.post(f"{API}/demand/{s['id']}/brief")).json()["id"] == r.json()["id"]


async def test_find_request_events(db, owner_client):
    fr = FindRequest(
        public_slug="hop-gia-vi", title="Hộp đựng gia vị có nắp kín", status=FindRequestStatus.OPEN, vote_count=3
    )
    db.add(fr)
    await db.flush()
    await events.emit("find_request.created", {"find_request_id": str(fr.id)}, db=db)
    await events.emit("find_request.created", {"find_request_id": str(fr.id)}, db=db)
    sig = (await db.execute(DemandSignal.__table__.select())).all()
    assert len(sig) == 1
    fr.vote_count = 12
    fr.status = FindRequestStatus.THRESHOLD_REACHED
    await db.flush()
    await events.emit("find_request.threshold", {"find_request_id": str(fr.id)}, db=db)
    await events.emit("find_request.threshold", {"find_request_id": str(fr.id)}, db=db)  # cùng dedupe → một việc
    await db.commit()
    items = (await owner_client.get(f"{API}/demand")).json()["items"]
    assert items[0]["find_request_id"] == str(fr.id) and items[0]["ask_count"] == 12
    pend = (
        await owner_client.get(
            "/api/desk/control/approvals", params={"action": "sourcing.suggest_demand_brief", "status": "pending"}
        )
    ).json()
    assert pend["total"] == 1
    r = await owner_client.post(f"/api/desk/control/approvals/{pend['items'][0]['id']}/approve", json={})
    assert r.status_code == 200, r.text
    briefs = (await owner_client.get(f"{API}/briefs")).json()["items"]
    assert briefs[0]["find_request_id"] == str(fr.id) and briefs[0]["demand_signal_id"] == items[0]["id"]


async def test_demand_digest_sweeps_missed(db, owner_client):
    _t, _m = await _message(db, "Nhờ chị tìm thảm chùi chân phòng tắm khô nhanh", intent=Intent.FIND_REQUEST)
    await db.commit()
    run = (await owner_client.post(f"{API}/demand/digest")).json()
    assert run["status"] == "succeeded" and run["new_count"] == 1
    assert (await db.execute(DemandMention.__table__.select())).first() is not None
    run = (await owner_client.post(f"{API}/demand/digest")).json()
    assert run["found_count"] == 0  # đã ghi rồi thì không rà lại


async def test_dismiss_demand(db, owner_client):
    t, m = await _message(db, "Có bán bình giữ nhiệt cho bé không ạ")
    await _emit_msg(db, t, m)
    await db.commit()
    s = (await owner_client.get(f"{API}/demand")).json()["items"][0]
    assert (await owner_client.post(f"{API}/demand/{s['id']}/dismiss")).json()["status"] == "dismissed"
    assert (await owner_client.get(f"{API}/demand")).json()["total"] == 0
