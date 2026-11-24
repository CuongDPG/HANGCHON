"""Hộp thư gộp (h1), AI soạn sẵn (h2), chuyển chị (h3) — chạy trọn bằng driver mock + AI fake."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import control
from app.core import events
from app.core.config import settings
from app.core.enums import Channel
from app.core.errors import Forbidden
from app.core.security import hmac_sha256
from app.core.timeutil import now_utc
from app.integrations import get_driver
from app.modules.control.models import AIActivity, ApprovalItem, ApprovalStatus, AutonomyLevel
from app.modules.inbox.models import Message, ReplyDraft, ReplyStatus, Thread, ThreadStatus
from tests.inbox import factories as f


@pytest.fixture
async def shop(db):
    await f.accounts(db)
    p = await f.product(db, stock=12)
    await db.commit()
    return p


async def _simulate(client, text, **kw):
    r = await client.post("/api/desk/inbox/dev/simulate", json={"text": text, **kw})
    assert r.status_code == 201, r.text
    return r.json()


async def test_price_question_becomes_faq_draft_waiting_for_owner(owner_client, shop, db):
    seen = []

    @events.on("message.received")
    async def spy(_db, payload):
        seen.append(payload)

    try:
        t = await _simulate(owner_client, "Bình giữ nhiệt giá bao nhiêu shop?", author_name="Thu Hà")
    finally:
        events._handlers["message.received"].remove(spy)
    assert t["status"] == "needs_owner" and not t["needs_owner"]
    assert t["last_intent"] == "ask_price"
    d = t["draft"]
    assert d["kind"] == "instant" and "385.000" in d["body"] and d["approval_item_id"]
    assert seen and seen[0]["thread_id"] == t["id"]
    item = await db.get(ApprovalItem, __import__("uuid").UUID(d["approval_item_id"]))
    assert item.action == "inbox.reply_faq" and item.status == ApprovalStatus.PENDING
    assert get_driver("social", "mock").sent == []  # chưa gửi gì cho khách
    counts = (await owner_client.get("/api/desk/inbox/counts")).json()
    assert counts == {"waiting": 1, "ai": 0, "all": 1}


async def test_faq_auto_sends_immediately_and_logs(owner_client, shop, db):
    await control.set_level(db, "inbox.reply_faq", AutonomyLevel.AUTO, None)
    await db.commit()
    t = await _simulate(owner_client, "Bình giữ nhiệt còn hàng không shop?", channel="instagram", author_name="Ngọc")
    assert t["status"] == "ai_handled" and t["draft"] is None, json.dumps(t, ensure_ascii=False)
    sent = get_driver("social", "mock").sent
    assert len(sent) == 1 and "còn 12" in sent[0]["text"]
    out = [m for m in t["messages"] if m["direction"] == "outbound"]
    assert out[0]["sender"] == "ai" and out[0]["ai_generated"]
    acts = (await db.execute(select(AIActivity).where(AIActivity.action == "inbox.reply_faq"))).scalars().all()
    assert len(acts) == 1 and acts[0].mode == "auto"
    assert (await owner_client.get("/api/desk/inbox/counts")).json()["ai"] == 1


async def test_complaint_is_escalated_never_auto_answered(owner_client, shop, db):
    await control.set_level(db, "inbox.reply_faq", AutonomyLevel.AUTO, None)
    await db.commit()
    t = await _simulate(owner_client, "Đơn mình nhận bị móp nắp, buồn quá", channel="zalo_oa", author_name="anh Minh")
    assert t["needs_owner"] and t["status"] == "needs_owner" and t["escalation_reason"] == "defect"
    d = t["draft"]
    assert d["kind"] == "escalation" and "hàng lỗi" in d["body"] and 1 <= len(d["options"]) <= 2
    assert all(o["label"] and o["reply"] for o in d["options"])
    assert get_driver("social", "mock").sent == []
    item = await db.get(ApprovalItem, __import__("uuid").UUID(d["approval_item_id"]))
    assert item.action == "inbox.escalate" and await control.get_level(db, "inbox.escalate") == "locked_ask"
    # chị chọn phương án 1 rồi gửi
    r = await owner_client.post(f"/api/desk/inbox/drafts/{d['id']}/send", json={"body": d["options"][0]["reply"]})
    assert r.status_code == 200, r.text
    t2 = r.json()
    assert not t2["needs_owner"] and t2["status"] == "waiting_customer" and t2["draft"] is None
    assert get_driver("social", "mock").sent[-1]["text"] == d["options"][0]["reply"]


async def test_escalation_ack_follows_autonomy_setting(owner_client, shop, db):
    t = await _simulate(owner_client, "Mình bị dị ứng có dùng được không?", author_name="Lan")
    assert t["escalation_reason"] == "health"
    assert get_driver("social", "mock").sent == []  # mặc định tắt
    await control.set_level(db, "inbox.ack_escalation", AutonomyLevel.AUTO, None)
    await db.commit()
    t = await _simulate(owner_client, "Hàng giao sai màu rồi shop", author_name="Mai")
    sent = get_driver("social", "mock").sent
    assert len(sent) == 1 and "trong hôm nay" in sent[0]["text"]
    # khách nhắn thêm: vẫn chờ chị, không báo lần hai, không tự trả lời
    t = await _simulate(owner_client, "Giá bao nhiêu vậy?", author_name="Mai")
    assert t["needs_owner"] and t["draft"]["kind"] == "escalation" and "nhắn thêm" in t["draft"]["body"]
    assert len(get_driver("social", "mock").sent) == 1


async def test_general_question_is_always_a_draft(owner_client, shop, db):
    with pytest.raises(Forbidden):
        await control.set_level(db, "inbox.reply_general", AutonomyLevel.AUTO, None)
    t = await _simulate(owner_client, "Bình này rửa máy rửa bát được không chị?", author_name="Hà")
    assert t["draft"]["kind"] == "draft" and t["last_intent"] == "ask_product"
    # sửa rồi gửi
    r = await owner_client.post(f"/api/desk/inbox/drafts/{t['draft']['id']}/send", json={"body": "Dạ nên rửa tay ạ."})
    assert r.status_code == 200
    assert get_driver("social", "mock").sent[-1]["text"] == "Dạ nên rửa tay ạ."
    d = (await db.execute(select(ReplyDraft))).scalars().one()
    assert d.status == ReplyStatus.SENT and d.body == "Dạ nên rửa tay ạ."


async def test_helper_cannot_send_draft_but_can_reply(helper_client, owner_client, shop):
    t = await _simulate(owner_client, "Bình giữ nhiệt giá sao chị?", author_name="Hà")
    r = await helper_client.post(f"/api/desk/inbox/drafts/{t['draft']['id']}/send", json={})
    assert r.status_code == 403
    r = await helper_client.post(f"/api/desk/inbox/threads/{t['id']}/reply", json={"body": "Dạ 385k ạ"})
    assert r.status_code == 200 and r.json()["status"] == "waiting_customer" and r.json()["draft"] is None


async def test_missing_data_escalates_low_confidence(owner_client, shop, db):
    t = await _simulate(owner_client, "Phí ship về Đà Nẵng bao nhiêu?", author_name="Khoa")
    assert t["needs_owner"] and t["escalation_reason"] == "low_confidence"
    await control.set_setting(db, "inbox.shipping_policy", "Phí giao 25.000–35.000đ tuỳ tỉnh", None)
    await db.commit()
    t = await _simulate(owner_client, "Phí ship về Huế bao nhiêu?", author_name="Khoa 2")
    assert t["draft"]["kind"] == "instant" and "25.000" in t["draft"]["body"]


async def test_new_message_supersedes_pending_draft(owner_client, shop, db):
    t1 = await _simulate(owner_client, "Bình giữ nhiệt giá bao nhiêu?", author_name="Hà", author_external_id="u1")
    t2 = await _simulate(owner_client, "Còn hàng không?", author_name="Hà", author_external_id="u1")
    assert t1["id"] == t2["id"] and t1["draft"]["id"] != t2["draft"]["id"]
    old = await db.get(ReplyDraft, __import__("uuid").UUID(t1["draft"]["id"]))
    assert old.status == ReplyStatus.SUPERSEDED
    pending = (await db.execute(select(func.count()).where(ApprovalItem.status == ApprovalStatus.PENDING))).scalar_one()
    assert pending == 1
    r = await owner_client.post(f"/api/desk/inbox/drafts/{t1['draft']['id']}/send", json={})
    assert r.status_code == 409


async def test_returned_draft_is_redrafted_with_note(owner_client, shop, db, fake_ai):
    t = await _simulate(owner_client, "Bình giữ nhiệt giá bao nhiêu?", author_name="Hà")
    notes = []
    from app.modules.inbox.ai_tasks import _fake_draft

    def spy(inp):
        notes.append(inp.owner_note)
        return _fake_draft(inp)

    fake_ai["inbox.draft_reply"] = spy
    r = await owner_client.post(
        f"/api/desk/control/approvals/{t['draft']['approval_item_id']}/return", json={"note": "Nhắc khách đợt sắp đóng"}
    )
    assert r.status_code == 200, r.text
    assert notes == ["Nhắc khách đợt sắp đóng"]
    t2 = (await owner_client.get(f"/api/desk/inbox/threads/{t['id']}")).json()
    assert t2["draft"] and t2["draft"]["id"] != t["draft"]["id"]


async def test_ai_unavailable_escalates(owner_client, shop, fake_ai):
    from app import ai

    def boom(_):
        raise ai.FakeRefusal("cyber")

    fake_ai["inbox.draft_reply"] = boom
    t = await _simulate(owner_client, "Giá bao nhiêu?", author_name="Hà")
    assert t["needs_owner"] and t["escalation_reason"] == "low_confidence"


async def test_search_tabs_and_customer_link(owner_client, shop, db):
    c = await f.customer(db, "Đào Thu Hà", "0912345678", email="thuha.dao@example.com")
    c2 = await f.customer(db, "Lê Minh", identity=(Channel.FACEBOOK, "psid-minh"))
    await db.commit()
    t1 = await _simulate(owner_client, "Số mình 0912 345 678, giá bao nhiêu?", author_name="Hà Đào")
    assert t1["customer_id"] == str(c.id)  # nhận ra qua số điện thoại
    t2 = await _simulate(owner_client, "Còn hàng không?", author_name="Minh", author_external_id="psid-minh")
    assert t2["customer_id"] == str(c2.id)  # nhận ra qua định danh kênh
    for q, expect in (("dao thu", 1), ("THUHA.DAO", 1), ("example.com", 0), ("con hang", 1), ("345678", 1)):
        r = await owner_client.get("/api/desk/inbox/threads", params={"tab": "all", "q": q})
        assert r.json()["total"] == expect, q
    t3 = await _simulate(owner_client, "Cảm ơn shop", author_name="Khách lạ", author_external_id="x9")
    # người lạ có hồ sơ khách ngay (orders tạo qua message.received → customer.identified)
    assert t3["customer_id"] not in (None, str(c.id), str(c2.id)) and t3["customer"]["name"] == "Khách lạ"
    r = await owner_client.post(f"/api/desk/inbox/threads/{t3['id']}/customer", json={"customer_id": str(c.id)})
    assert r.json()["customer"]["name"] == "Đào Thu Hà"
    r = await owner_client.post(f"/api/desk/inbox/threads/{t3['id']}/status", json={"status": "closed"})
    assert r.json()["status"] == "closed" and r.json()["draft"] is None
    assert (await owner_client.get("/api/desk/inbox/threads", params={"tab": "waiting"})).json()["total"] == 2


async def test_comment_reply_and_public_tone(owner_client, shop):
    t = await _simulate(
        owner_client, "Bình giữ nhiệt giá bao nhiêu ạ", kind="comment", author_name="Hà", post_external_id="post1"
    )
    assert t["kind"] == "comment" and "nhắn riêng" in t["draft"]["body"]
    assert t["capabilities"]["private_reply"] is False  # mock không có nhắn riêng
    r = await owner_client.post(f"/api/desk/inbox/drafts/{t['draft']['id']}/send", json={})
    assert r.status_code == 200
    assert "comment" in get_driver("social", "mock").sent[-1]


async def test_mock_webhook_signature_and_idempotency(client, owner_client, shop, db):
    mock = get_driver("social", "mock")
    ev = mock.simulate_inbound("Giá bao nhiêu?", author_name="Webhook")
    body = json.dumps({"events": [ev.model_dump(mode="json")]}).encode()
    sig = "sha256=" + hmac_sha256(settings.hooks_mock_secret, body)
    r = await client.post("/api/hooks/social/mock", content=body, headers={"X-Mock-Signature": "sha256=sai"})
    assert r.status_code == 403
    r = await client.post("/api/hooks/social/mock", content=body, headers={"X-Mock-Signature": sig})
    assert r.status_code == 200 and r.json() == {"received": 1, "new": 1}
    r = await client.post("/api/hooks/social/mock", content=body, headers={"X-Mock-Signature": sig})
    assert r.json() == {"received": 1, "new": 0}
    assert (await db.execute(select(func.count()).select_from(Message))).scalar_one() == 1
    # việc nền đã soạn nháp (JOBS_EAGER)
    assert (await db.execute(select(func.count()).select_from(ReplyDraft))).scalar_one() == 1


async def test_simulate_disabled_in_prod(owner_client, shop, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "prod")
    r = await owner_client.post("/api/desk/inbox/dev/simulate", json={"text": "hi"})
    assert r.status_code == 404
    r = await owner_client.post("/api/hooks/social/mock", content=b"{}")
    assert r.status_code == 404


async def test_window_blocks_late_auto_reply_and_tags_human(owner_client, shop, db):
    t = await _simulate(owner_client, "Bình này rửa máy được không?", author_name="Hà")
    th = await db.get(Thread, __import__("uuid").UUID(t["id"]))
    th.last_inbound_at = now_utc() - timedelta(days=3)
    await db.commit()
    detail = (await owner_client.get(f"/api/desk/inbox/threads/{t['id']}")).json()
    assert detail["capabilities"] == {
        "can_reply": True,
        "reason": None,
        "human_agent_tag": True,
        "private_reply": False,
    }
    th.last_inbound_at = now_utc() - timedelta(days=8)
    await db.commit()
    r = await owner_client.post(f"/api/desk/inbox/threads/{t['id']}/reply", json={"body": "Dạ"})
    assert r.status_code == 400 and r.json()["code"] == "outside_window"


async def test_list_requires_login(client):
    assert (await client.get("/api/desk/inbox/threads")).status_code == 401


async def test_stat_provider(owner_client, shop):
    await _simulate(owner_client, "Giá bao nhiêu?", author_name="Hà")
    today = (await owner_client.get("/api/desk/control/today")).json()
    assert any(s["key"] == "inbox.waiting" and s["value"] == 1 for s in today["stats"])


async def test_spam_thread_is_ignored(owner_client, shop, db):
    t = await _simulate(owner_client, "Giá?", author_name="Spam", author_external_id="sp")
    await owner_client.post(f"/api/desk/inbox/threads/{t['id']}/status", json={"status": "spam"})
    await _simulate(owner_client, "Giá??", author_name="Spam", author_external_id="sp")
    th = await db.get(Thread, __import__("uuid").UUID(t["id"]))
    await db.refresh(th)
    assert th.status == ThreadStatus.SPAM
    assert (await owner_client.get("/api/desk/inbox/counts")).json()["all"] == 0
