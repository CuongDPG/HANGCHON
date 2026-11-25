"""Sổ khách (h4), khách quen (h5), nhắc mua lại (h6), giới thiệu bạn (h7), khách thử hàng (h8)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import control
from app.core import events
from app.core.enums import Channel, SourcePlatform
from app.core.timeutil import local_today, now_utc
from app.integrations import get_driver
from app.modules.control.models import AIActivity, ApprovalItem, ApprovalStatus, AutonomyLevel
from app.modules.crm import service
from app.modules.crm.models import (
    Broadcast,
    BroadcastStatus,
    CustomerNote,
    NoteKind,
    ReferralUse,
    ReferralUseStatus,
    ReminderStatus,
    ReorderReminder,
)
from app.modules.selection.models import NoteAuthor, TrialNote, TrialNoteKind
from app.modules.sourcing.models import Candidate, CandidateStage
from tests.inbox import factories as f


def _outbox():
    return get_driver("notify", "mock").outbox


# ---- h4 ----------------------------------------------------------------------------------------------------------


async def test_customer_book_search_notes_tags(owner_client, db):
    c = await f.customer(db, "Nguyễn Thị Thu Hà", "0912000111", email="thuha.nguyen@example.com", orders=3)
    await f.customer(db, "Lê Văn Đức", "0988000222")
    await db.commit()
    for q, n in (("thu ha", 1), ("DUC", 1), ("thuha.nguyen@example.net", 1), ("example.com", 0), ("000111", 1)):
        r = await owner_client.get("/api/desk/crm/customers", params={"q": q})
        assert r.json()["total"] == n, q
    r = await owner_client.post(
        f"/api/desk/crm/customers/{c.id}/notes", json={"body": "Thích màu xám", "kind": "preference"}
    )
    assert r.status_code == 201
    note_id = r.json()["id"]
    assert (await owner_client.patch(f"/api/desk/crm/notes/{note_id}", json={"pinned": True})).json()["pinned"]
    r = await owner_client.post(f"/api/desk/crm/customers/{c.id}/tags", json={"tag": "Mua làm quà"})
    assert r.status_code == 201 and "mua-lam-qua" in r.json()["tags"]
    assert (await owner_client.get("/api/desk/crm/customers", params={"q": "mau xam"})).json()["total"] == 1
    assert (await owner_client.get("/api/desk/crm/customers", params={"tag": "mua-lam-qua"})).json()["total"] == 1
    assert (await owner_client.delete(f"/api/desk/crm/customers/{c.id}/tags/mua-lam-qua")).status_code == 204
    assert (await owner_client.delete(f"/api/desk/crm/notes/{note_id}")).status_code == 204
    p = (await owner_client.get(f"/api/desk/crm/customers/{c.id}")).json()
    assert p["is_regular"] and p["tags"] == [] and p["notes"] == []
    assert (await owner_client.get(f"/api/desk/crm/customers/{uuid.uuid4()}")).status_code == 404


async def test_message_received_updates_ai_summary_and_undo(owner_client, db):
    await f.accounts(db)
    p = await f.product(db, stock=5)
    c = await f.customer(db, "Thu Hà", "0912000111", identity=(Channel.FACEBOOK, "psid-ha"))
    await f.order(db, c, p)
    await db.commit()
    r = await owner_client.post(
        "/api/desk/inbox/dev/simulate",
        json={"text": "Bình giữ nhiệt còn màu xám không?", "author_name": "Hà", "author_external_id": "psid-ha"},
    )
    assert r.json()["customer_id"] == str(c.id)
    prof = (await owner_client.get(f"/api/desk/crm/customers/{c.id}")).json()
    assert "Bình giữ nhiệt" in prof["summary"] and "còn hàng" in prof["summary"]
    assert prof["interests"] and prof["recent_questions"][0]["body"].startswith("Bình giữ nhiệt")
    act = (await db.execute(select(AIActivity).where(AIActivity.action == "crm.update_profile"))).scalars().first()
    assert act and act.undoable
    r = await owner_client.post(f"/api/desk/control/activity/{act.id}/undo")
    assert r.status_code == 200, r.text
    assert (await owner_client.get(f"/api/desk/crm/customers/{c.id}")).json()["summary"] is None


async def test_order_created_event_refreshes_summary_idempotently(db):
    p = await f.product(db)
    c = await f.customer(db, "Minh")
    o = await f.order(db, c, p, qty=2)
    await events.emit("order.created", {"order_id": str(o.id)}, db=db)
    await events.emit("order.created", {"order_id": str(o.id)}, db=db)
    notes = (
        (
            await db.execute(
                select(CustomerNote).where(CustomerNote.customer_id == c.id, CustomerNote.kind == NoteKind.AI_SUMMARY)
            )
        )
        .scalars()
        .all()
    )
    assert len(notes) == 1 and "Minh đã mua 1 đơn" in notes[0].body


async def test_opt_out(owner_client, db):
    c = await f.customer(db, "Lan")
    await db.commit()
    r = await owner_client.post(f"/api/desk/crm/customers/{c.id}/opt-out", json={"opt_out": True})
    assert r.json()["opted_out"]
    assert (await owner_client.get("/api/desk/crm/customers", params={"segment": "optout"})).json()["total"] == 1
    r = await owner_client.post(f"/api/desk/crm/customers/{c.id}/opt-out", json={"opt_out": False})
    assert not r.json()["opted_out"]


# ---- h5 ----------------------------------------------------------------------------------------------------------


async def _drop_with_regulars(db):
    p = await f.product(db, "Hộp cơm inox 3 ngăn", 245_000)
    d = await f.open_drop(db, p)
    a = await f.customer(db, "Thu Hà", orders=3, identity=(Channel.ZALO_OA, "zalo-ha"))
    b = await f.customer(db, "Ngọc", orders=2, email="ngoc@example.com")
    out = await f.customer(db, "Từ chối", orders=5)
    await f.customer(db, "Mới", orders=1)
    await service.set_opt_out(db, out.id, True, None)
    await db.commit()
    return d, a, b


async def test_drop_opened_drafts_announcement_for_regulars(owner_client, helper_client, db):
    d, _, _ = await _drop_with_regulars(db)
    regs = (await owner_client.get("/api/desk/crm/regulars")).json()
    assert regs["min_orders"] == 2 and regs["total"] == 3 and regs["reachable"] == 2
    await events.emit("drop.opened", {"drop_id": str(d.id)}, db=db)
    await events.emit("drop.opened", {"drop_id": str(d.id)}, db=db)
    await db.commit()
    bs = (await owner_client.get("/api/desk/crm/broadcasts")).json()
    assert len(bs) == 1 and bs[0]["status"] == "pending_review" and "245.000" in bs[0]["body"]
    assert bs[0]["recipient_count"] == 2 and bs[0]["drop_title"] == d.title and bs[0]["approval_item_id"]
    assert _outbox() == []
    assert (await helper_client.post(f"/api/desk/crm/broadcasts/{bs[0]['id']}/send", json={})).status_code == 403
    r = await owner_client.post(f"/api/desk/crm/broadcasts/{bs[0]['id']}/send", json={"body": "Mở đợt rồi nè"})
    assert r.status_code == 200 and r.json()["status"] == "sent" and r.json()["delivered_count"] == 2
    assert sorted(m.to for m in _outbox()) == ["ngoc@example.com", "zalo-ha"]
    assert all(m.text == "Mở đợt rồi nè" for m in _outbox())
    assert (await owner_client.post(f"/api/desk/crm/broadcasts/{bs[0]['id']}/send", json={})).status_code == 409


async def test_broadcast_auto_level_sends_and_threshold_setting(owner_client, db):
    d, *_ = await _drop_with_regulars(db)
    await control.set_level(db, "crm.send_broadcast", AutonomyLevel.AUTO, None)
    await service.draft_drop_announcement(db, d.id)
    await db.commit()
    b = (await db.execute(select(Broadcast))).scalar_one()
    assert b.status == BroadcastStatus.SENT and len(_outbox()) == 2
    r = await owner_client.patch("/api/desk/crm/settings", json={"regular_min_orders": 3})
    assert r.json()["total"] == 2


async def test_manual_broadcast_and_cancel(owner_client, db):
    await _drop_with_regulars(db)
    r = await owner_client.post("/api/desk/crm/broadcasts", json={"title": "Báo nghỉ Tết", "body": "Mình nghỉ từ 25/1"})
    assert r.status_code == 201 and r.json()["status"] == "pending_review"
    r = await owner_client.post(f"/api/desk/crm/broadcasts/{r.json()['id']}/cancel")
    assert r.json()["status"] == "cancelled"
    assert (await db.execute(select(ApprovalItem))).scalars().one().status == ApprovalStatus.CANCELLED


async def test_group_digest(owner_client, db):
    await f.product(db, "Hộp cơm inox 3 ngăn")
    await db.commit()
    text = (
        "Lan: Hộp cơm inox dùng thích lắm, giữ nóng tốt\n"
        "Hà: Hộp cơm inox có loại 2 ngăn không chị?\n"
        "Minh: Đợt trước mình chờ hơi lâu, chưa về\n"
        "Ngọc: Bao giờ có bình giữ nhiệt lại ạ?"
    )
    r = await owner_client.post("/api/desk/crm/group-digests", json={"text": text})
    assert r.status_code == 201, r.text
    d = r.json()
    assert "4 tin từ 4 người" in d["summary"] and len(d["open_questions"]) == 2
    assert d["product_mentions"][0]["name"] == "Hộp cơm inox 3 ngăn" and d["product_mentions"][0]["count"] == 2
    assert len((await owner_client.get("/api/desk/crm/group-digests")).json()) == 1


# ---- h6 ----------------------------------------------------------------------------------------------------------


async def test_reorder_flow(owner_client, db):
    p = await f.product(db, "Túi lọc trà", 90_000)
    c = await f.customer(db, "Thu Hà", identity=(Channel.ZALO_OA, "zalo-ha"))
    await db.commit()
    rules = (await owner_client.get("/api/desk/crm/reorder-rules")).json()
    assert all(x["product_id"] != str(p.id) for x in rules)  # chưa phải món tiêu hao
    r = await owner_client.put(f"/api/desk/crm/reorder-rules/{p.id}", json={"cycle_days": 30, "active": True})
    rule = next(x for x in r.json() if x["product_id"] == str(p.id))
    assert rule["effective_days"] == 30
    o = await f.order(db, c, p, qty=2, delivered=True)
    await events.emit("order.delivered", {"order_id": str(o.id)}, db=db)
    await events.emit("order.delivered", {"order_id": str(o.id)}, db=db)
    rem = (await db.execute(select(ReorderReminder))).scalars().one()
    assert rem.due_on == local_today() + timedelta(days=60 - 5) and rem.status == ReminderStatus.SCHEDULED
    # tới hạn → AI soạn, chờ chị
    rem.due_on = local_today()
    await db.commit()
    assert (await owner_client.post("/api/desk/crm/reminders/run-due")).json() == {"drafted": 1, "skipped": 0}
    lst = (await owner_client.get("/api/desk/crm/reminders", params={"status": "pending_review"})).json()
    assert len(lst) == 1 and "Túi lọc trà" in lst[0]["message_body"] and lst[0]["customer_name"] == "Thu Hà"
    assert _outbox() == []
    r = await owner_client.post(f"/api/desk/crm/reminders/{lst[0]['id']}/send", json={})
    assert r.status_code == 200 and r.json()["status"] == "sent" and _outbox()[0].to == "zalo-ha"
    # khách mua lại → chuyển «converted»
    o2 = await f.order(db, c, p)
    o2_id = o2.id
    db.expire_all()  # nhắc vừa được gửi ở phiên của API
    await events.emit("order.created", {"order_id": str(o2_id)}, db=db)
    await db.refresh(rem)
    assert rem.status == ReminderStatus.CONVERTED and rem.converted_order_id == o2_id


async def test_reorder_not_twice_per_cycle_and_opt_out(db):
    p = await f.product(db, "Viên tẩy bồn cầu", 120_000, consumable=True, reorder_days=40)
    c = await f.customer(db, "Minh", email="minh@example.com")
    c2 = await f.customer(db, "Lan", email="lan@example.com")
    await service.set_opt_out(db, c2.id, True, None)
    for cust in (c, c, c2):
        o = await f.order(db, cust, p, delivered=True)
        await service.schedule_reminders(db, o.id)
    rows = (await db.execute(select(ReorderReminder))).scalars().all()
    for r in rows:
        r.due_on = local_today()
    await db.flush()
    assert await service.run_due(db) == {"drafted": 1, "skipped": 2}
    statuses = sorted(str(r.status) for r in rows)
    assert statuses == ["pending_review", "skipped", "skipped"]
    assert any("chu kỳ" in (r.reason or "") for r in rows) and any("từ chối" in (r.reason or "") for r in rows)


async def test_reorder_auto_level_sends(db):
    await control.set_level(db, "crm.send_reorder_reminder", AutonomyLevel.AUTO, None)
    p = await f.product(db, "Viên tẩy bồn cầu", 120_000, consumable=True, reorder_days=40)
    c = await f.customer(db, "Minh", email="minh@example.com")
    o = await f.order(db, c, p, delivered=True)
    (r,) = await service.schedule_reminders(db, o.id)
    r.due_on = local_today()
    await db.flush()
    await service.run_due(db)
    assert r.status == ReminderStatus.SENT and _outbox()[0].to == "minh@example.com"


# ---- h7 ----------------------------------------------------------------------------------------------------------


async def test_referral_flow_and_stats(owner_client, db):
    p = await f.product(db)
    ha = await f.customer(db, "Thu Hà", orders=2)
    await db.commit()
    r = await owner_client.post(f"/api/desk/crm/customers/{ha.id}/referral")
    code = r.json()["referral"]["code"]
    assert code.startswith("HA-") and len(code) == 7
    again = (await owner_client.post(f"/api/desk/crm/customers/{ha.id}/referral")).json()["referral"]["code"]
    assert again == code
    lan = await f.customer(db, "Lan")
    o = await f.order(db, lan, p, referral_code=code.lower())
    await events.emit("order.created", {"order_id": str(o.id)}, db=db)
    await events.emit("order.created", {"order_id": str(o.id)}, db=db)
    # tự giới thiệu và đơn không phải đơn đầu: không tính
    own = await f.order(db, ha, p, referral_code=code)
    await events.emit("order.created", {"order_id": str(own.id)}, db=db)
    minh = await f.customer(db, "Minh")
    first = await f.order(db, minh, p)
    first.placed_at = now_utc() - timedelta(days=30)
    second = await f.order(db, minh, p, referral_code=code)
    await events.emit("order.created", {"order_id": str(second.id)}, db=db)
    uses = (await db.execute(select(ReferralUse))).scalars().all()
    assert len(uses) == 1 and uses[0].referred_customer_id == lan.id and uses[0].status == ReferralUseStatus.PENDING
    await events.emit("order.delivered", {"order_id": str(o.id)}, db=db)
    await db.commit()
    lst = (await owner_client.get("/api/desk/crm/referrals/uses")).json()
    assert lst[0]["status"] == "qualified" and lst[0]["referred_name"] == "Lan" and lst[0]["order_code"] == o.code
    r = await owner_client.post(f"/api/desk/crm/referral-uses/{lst[0]['id']}/reward", json={"note": "Phiếu 30k"})
    stats = r.json()
    assert stats["rewarded"] == 1 and stats["orders_from_referrals"] == 1 and stats["referred_customers"] == 1
    assert stats["referred_repeat_rate"] == 0.0
    notes = (await db.execute(select(CustomerNote).where(CustomerNote.ref_type == "referral_uses"))).scalars().all()
    assert len(notes) == 2
    assert (await owner_client.post(f"/api/desk/crm/referral-uses/{lst[0]['id']}/reward", json={})).status_code == 409
    codes = (await owner_client.get("/api/desk/crm/referrals")).json()
    assert codes[0]["uses_count"] == 1 and codes[0]["referrer_name"] == "Thu Hà"


async def test_manual_referral(owner_client, db):
    ha = await f.customer(db, "Thu Hà")
    lan = await f.customer(db, "Lan")
    ref = await service.get_or_create_referral(db, ha.id)
    await db.commit()
    url = f"/api/desk/crm/referrals/{ref.id}/uses"
    assert (await owner_client.post(url, json={"customer_id": str(lan.id)})).status_code == 201
    assert (await owner_client.post(url, json={"customer_id": str(lan.id)})).status_code == 409
    assert (await owner_client.post(url, json={"customer_id": str(ha.id)})).status_code == 400


# ---- h8 ----------------------------------------------------------------------------------------------------------


async def test_tester_invite_and_one_time_feedback(owner_client, client, db):
    cand = Candidate(
        title_vi="Bình giữ nhiệt 480 ml (mẫu Nhật)", source_platform=SourcePlatform.RAKUTEN, stage=CandidateStage.TRIAL
    )
    other = Candidate(title_vi="Món chưa thử", source_platform=SourcePlatform.TAOBAO)
    db.add_all([cand, other])
    await db.flush()
    db.add(
        TrialNote(
            candidate_id=cand.id,
            kind=TrialNoteKind.TEXT,
            text="Ngày 3: giữ nóng tốt",
            recorded_at=now_utc(),
            trial_day=3,
        )
    )
    ha = await f.customer(db, "Nguyễn Thu Hà", orders=3, email="ha@example.com")
    nophone = await f.customer(db, "Không kênh")
    nophone.phone = None
    await db.commit()
    r = await owner_client.post(
        "/api/desk/crm/tester-invites",
        json={"candidate_id": str(cand.id), "customer_ids": [str(ha.id), str(nophone.id)]},
    )
    assert r.status_code == 201, r.text
    invs = {i["customer_name"]: i for i in r.json()}
    assert invs["Nguyễn Thu Hà"]["status"] == "invited" and invs["Không kênh"]["status"] == "draft"
    assert "/thu-hang/" in _outbox()[0].text and "Hà" in _outbox()[0].text
    bad = await owner_client.post(
        "/api/desk/crm/tester-invites", json={"candidate_id": str(other.id), "customer_ids": [str(ha.id)]}
    )
    assert bad.status_code == 400
    token = invs["Nguyễn Thu Hà"]["link"].rsplit("/", 1)[1]
    pub = (await client.get(f"/api/store/crm/thu-hang/{token}")).json()
    assert pub["first_name"] == "Hà" and pub["can_answer"] and "email" not in pub
    r = await client.post(f"/api/store/crm/thu-hang/{token}", json={"action": "accept"})
    assert r.json()["status"] == "accepted" and not r.json()["can_answer"]
    assert (await client.post(f"/api/store/crm/thu-hang/{token}", json={"action": "feedback"})).status_code == 400
    r = await client.post(
        f"/api/store/crm/thu-hang/{token}",
        json={"action": "feedback", "feedback": "Giữ nóng 8 tiếng, nắp hơi chặt", "rating": 4},
    )
    assert r.json()["status"] == "feedback_received" and not r.json()["can_feedback"]
    r = await client.post(f"/api/store/crm/thu-hang/{token}", json={"action": "feedback", "feedback": "lần hai"})
    assert r.status_code == 409
    draft_token = invs["Không kênh"]["link"].rsplit("/", 1)[1]
    assert (await client.get(f"/api/store/crm/thu-hang/{draft_token}")).status_code == 404
    view = (await owner_client.get("/api/desk/crm/testers/candidates")).json()
    assert len(view) == 1 and view[0]["notes"][0]["text"].startswith("Ngày 3")
    fb = next(i for i in view[0]["invites"] if i["feedback"])
    assert fb["feedback_rating"] == 4
    r = await owner_client.post(
        f"/api/desk/crm/tester-invites/{invs['Không kênh']['id']}/status", json={"status": "invited"}
    )
    assert r.json()["status"] == "invited"
    assert (await client.get("/api/store/crm/thu-hang/khong-co")).status_code == 404


@pytest.mark.parametrize("path", ["/api/desk/crm/customers", "/api/desk/crm/regulars", "/api/desk/crm/referrals/stats"])
async def test_desk_routes_require_login(client, path):
    assert (await client.get(path)).status_code == 401


async def test_stat_provider_due(owner_client, db):
    p = await f.product(db, consumable=True, reorder_days=10)
    c = await f.customer(db, email="a@example.com")
    o = await f.order(db, c, p, delivered=True)
    (r,) = await service.schedule_reminders(db, o.id)
    r.due_on = local_today()
    await db.commit()
    stats = (await owner_client.get("/api/desk/control/today")).json()["stats"]
    assert any(s["key"] == "crm.reorder_due" and s["value"] == 1 for s in stats)
    _ = NoteAuthor
