"""«Mời thử cùng» (27/11): sổ người dùng thử, link riêng theo món, chọn người, cảm nhận → đề xuất hoàn tiền, lỡ hạn.
Số điện thoại / tên trong test là ví dụ, không phải khách thật."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from app.core.enums import SourcePlatform
from app.integrations import get_driver
from app.modules.control.models import ApprovalItem, ApprovalStatus
from app.modules.crm import cotrial
from app.modules.crm import models as crm_models
from app.modules.orders.models import Customer
from app.modules.selection.models import NoteAuthor, TrialNote
from app.modules.sourcing.models import Candidate, CandidateStage

PHONE_A = "0900000201"
PHONE_B = "0900000202"
PHONE_C = "0900000203"


def _outbox():
    return get_driver("notify", "mock").outbox


async def _candidate(db, stage=CandidateStage.TRIAL, title="Hộp cơm giữ nhiệt 2 tầng") -> Candidate:
    c = Candidate(title_vi=title, source_platform=SourcePlatform.TAOBAO, stage=stage)
    db.add(c)
    await db.commit()
    return c


async def _offer(owner_client, cand, **kw) -> dict:
    body = {"candidate_id": str(cand.id), "price_vnd": 250_000, "refund_pct": 60, "slots": 2, "feedback_days": 7, **kw}
    r = await owner_client.post("/api/desk/crm/cotrial/offers", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _token(link: str) -> str:
    return link.rsplit("/", 1)[1]


async def _apply(client, token, phone, name="Lan Ví Dụ", **kw):
    return await client.post(
        f"/api/store/crm/dung-thu/m/{token}", json={"name": name, "phone": phone, "agree": True, **kw}
    )


async def _status(owner_client, app_id, action, **kw):
    return await owner_client.post(f"/api/desk/crm/cotrial/applications/{app_id}/status", json={"action": action, **kw})


async def test_registry_signup_matches_or_creates_customer(client, owner_client, db):
    old = Customer(name="Khách Cũ", phone=PHONE_A)
    db.add(old)
    await db.commit()
    assert (await client.post("/api/store/crm/dung-thu", json={"name": "A", "phone": PHONE_A})).status_code == 400
    assert (await client.post("/api/store/crm/dung-thu", json={"name": "A", "agree": True})).status_code == 400
    r = await client.post(
        "/api/store/crm/dung-thu", json={"name": "Lan", "phone": "+84 900 000 201", "agree": True, "interests": ["x"]}
    )
    assert r.status_code == 201, r.text
    assert set(r.json()) == {"ok", "message"}  # không trả lại dữ liệu cá nhân
    r = await client.post("/api/store/crm/dung-thu", json={"name": "Mai", "email": "Mai@Example.com", "agree": True})
    assert r.status_code == 201
    await db.refresh(old)
    assert old.name == "Khách Cũ"  # không ghi đè tên chị đã có
    reg = (await owner_client.get("/api/desk/crm/cotrial/testers")).json()
    assert {t["name"] for t in reg} == {"Khách Cũ", "Mai"}
    mai = next(t for t in reg if t["name"] == "Mai")
    assert mai["email"] == "mai@example.com" and mai["phone"] is None and not mai["excluded"]
    assert await db.scalar(select(func.count(crm_models.TesterProfile.id))) == 2
    # đăng ký lại cùng số: không sinh hồ sơ mới
    await client.post("/api/store/crm/dung-thu", json={"name": "Lan", "phone": PHONE_A, "agree": True})
    assert await db.scalar(select(func.count(crm_models.TesterProfile.id))) == 2


async def test_offer_link_privacy_stage_and_slots(client, owner_client, db):
    cand = await _candidate(db)
    idle = await _candidate(db, CandidateStage.CANDIDATE, "Món chưa thử")
    r = await owner_client.post(
        "/api/desk/crm/cotrial/offers", json={"candidate_id": str(idle.id), "price_vnd": 100_000, "refund_vnd": 50_000}
    )
    assert r.status_code == 400
    r = await owner_client.post(
        "/api/desk/crm/cotrial/offers", json={"candidate_id": str(cand.id), "price_vnd": 100_000}
    )
    assert r.status_code == 400  # phải có tiền hoàn hoặc %
    offer = await _offer(owner_client, cand, slots=1)
    assert "/dung-thu/m/" in offer["link"] and offer["refund_amount_vnd"] == 150_000
    token = _token(offer["link"])
    assert (await client.get("/api/store/crm/dung-thu/m/khong-co-that")).status_code == 404
    pub = (await client.get(f"/api/store/crm/dung-thu/m/{token}")).json()
    assert pub["title"] == cand.title_vi and pub["refund_vnd"] == 150_000 and not pub["full"]
    assert not {"candidate_id", "source_url", "stage", "token"} & set(pub)

    assert (await _apply(client, token, PHONE_A, agree=False)).status_code == 400
    assert (await _apply(client, token, PHONE_A)).status_code == 201
    assert (await _apply(client, token, PHONE_A)).status_code == 409  # đã đăng ký
    assert (await _apply(client, token, PHONE_B, name="Hoa")).status_code == 201
    detail = (await owner_client.get(f"/api/desk/crm/cotrial/offers/{offer['id']}")).json()
    a, b = detail["applications"]
    assert a["status"] == "applied" and a["history"]["orders"] == 0
    assert (await _status(owner_client, a["id"], "select")).status_code == 200
    r = await _status(owner_client, b["id"], "select")
    assert r.status_code == 409 and r.json()["code"] == "full"
    assert (await client.get(f"/api/store/crm/dung-thu/m/{token}")).json()["full"] is True
    assert (await _apply(client, token, PHONE_C, name="Cúc")).status_code == 409

    r = await owner_client.patch(f"/api/desk/crm/cotrial/offers/{offer['id']}", json={"status": "closed"})
    assert r.json()["status"] == "closed"
    assert (await client.get(f"/api/store/crm/dung-thu/m/{token}")).status_code == 404
    assert (await _apply(client, token, PHONE_C, name="Cúc")).status_code == 404
    # lời mời h8 cũ không lẫn vào màn «Khách thử hàng»
    assert (await owner_client.get("/api/desk/crm/testers/candidates")).json()[0]["invites"] == []


async def test_selection_feedback_and_refund_proposal(client, owner_client, db):
    cand = await _candidate(db)
    offer = await _offer(owner_client, cand)
    token = _token(offer["link"])
    await _apply(client, token, PHONE_A, note="Nhà mình hay mang cơm đi làm")
    (app,) = (await owner_client.get(f"/api/desk/crm/cotrial/offers/{offer['id']}")).json()["applications"]
    assert app["note"] == "Nhà mình hay mang cơm đi làm"
    assert (await _status(owner_client, app["id"], "shipped")).status_code == 409  # chưa trả tiền
    n_out = len(_outbox())
    r = await _status(owner_client, app["id"], "select")
    assert r.json()["status"] == "selected"
    msg = _outbox()[n_out]
    assert "/thu-hang/" in msg.text and "150.000" in msg.text and "chị" not in msg.text.lower()
    fb_token = _token(r.json()["link"])
    form = {"rating": "4", "liked": "Giữ ấm tới trưa", "disliked": "Nắp hơi chặt", "would_buy": "maybe"}
    r = await client.post(f"/api/store/crm/thu-hang/{fb_token}/cam-nhan", data=form)
    assert r.status_code == 409 and r.json()["code"] == "not_shipped"
    assert (await _status(owner_client, app["id"], "paid")).json()["paid_vnd"] == 250_000
    shipped = (await _status(owner_client, app["id"], "shipped")).json()
    assert shipped["feedback_due_at"]
    pub = (await client.get(f"/api/store/crm/thu-hang/{fb_token}")).json()
    assert pub["can_feedback"] and pub["cotrial"]["refund_vnd"] == 150_000 and pub["product_title"] == offer["title"]
    # h8: hành động cũ không dùng cho «Mời thử cùng»
    assert (await client.post(f"/api/store/crm/thu-hang/{fb_token}", json={"action": "accept"})).status_code == 400

    r = await client.post(f"/api/store/crm/thu-hang/{fb_token}/cam-nhan", data={**form, "disliked": " "})
    assert r.status_code == 400 and r.json()["code"] == "incomplete"
    r = await client.post(
        f"/api/store/crm/thu-hang/{fb_token}/cam-nhan", data={**form, "refund_account": "STK ví dụ 0000"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "refund_proposed"
    assert (await client.post(f"/api/store/crm/thu-hang/{fb_token}/cam-nhan", data=form)).status_code == 409

    item = await db.scalar(select(ApprovalItem).where(ApprovalItem.action == cotrial.ACTION_REFUND))
    assert item.status == ApprovalStatus.PENDING and item.payload["refund_vnd"] == 150_000
    assert item.preview["refund_account"] == "STK ví dụ 0000"
    note = await db.scalar(select(TrialNote).where(TrialNote.candidate_id == cand.id))
    assert note.author == NoteAuthor.TESTER and "Nắp hơi chặt" in note.text and not note.is_public
    detail = (await owner_client.get(f"/api/desk/selection/candidates/{cand.id}")).json()
    assert any(n["author"] == "tester" for n in detail["notes"])  # cảm nhận vào hồ sơ món ở Bàn chọn

    r = await owner_client.post(
        f"/api/desk/control/approvals/{item.id}/approve", json={"payload": {"refund_vnd": 140_000}}
    )
    assert r.status_code == 200, r.text
    app = (await owner_client.get(f"/api/desk/crm/cotrial/offers/{offer['id']}")).json()["applications"][0]
    assert app["status"] == "refunded" and app["refund_vnd"] == 140_000 and app["refunded_at"]
    assert app["history"]["completed"] == 1


async def test_refund_returned_can_be_proposed_again(client, owner_client, db):
    cand = await _candidate(db)
    offer = await _offer(owner_client, cand)
    await _apply(client, _token(offer["link"]), PHONE_A)
    (app,) = (await owner_client.get(f"/api/desk/crm/cotrial/offers/{offer['id']}")).json()["applications"]
    for step in ("select", "paid", "shipped"):
        await _status(owner_client, app["id"], step)
    form = {"rating": "5", "liked": "Gọn", "disliked": "Không có gì", "would_buy": "yes"}
    await client.post(f"/api/store/crm/thu-hang/{_token(app['link'])}/cam-nhan", data=form)
    item = await db.scalar(select(ApprovalItem).where(ApprovalItem.action == cotrial.ACTION_REFUND))
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/return", json={"note": "Hỏi lại STK"})
    assert r.status_code == 200, r.text
    assert (await _status(owner_client, app["id"], "propose_refund")).json()["status"] == "refund_proposed"


async def test_deadline_reminder_then_missed_excludes_from_next_offer(client, owner_client, db):
    cand = await _candidate(db)
    offer = await _offer(owner_client, cand)
    await _apply(client, _token(offer["link"]), PHONE_A)
    (app,) = (await owner_client.get(f"/api/desk/crm/cotrial/offers/{offer['id']}")).json()["applications"]
    for step in ("select", "paid", "shipped"):
        await _status(owner_client, app["id"], step)
    inv = await db.get(crm_models.TesterInvite, app["id"])
    due = inv.feedback_due_at
    n_out = len(_outbox())
    assert await cotrial.run_deadlines(db, due - timedelta(days=3)) == {"reminded": 0, "missed": 0}
    assert await cotrial.run_deadlines(db, due - timedelta(days=1)) == {"reminded": 1, "missed": 0}
    assert "hạn gửi cảm nhận" in _outbox()[n_out].text
    assert await cotrial.run_deadlines(db, due - timedelta(hours=1)) == {"reminded": 0, "missed": 0}  # nhắc một lần
    assert await cotrial.run_deadlines(db, due + timedelta(minutes=1)) == {"reminded": 0, "missed": 1}
    await db.commit()
    form = {"rating": "5", "liked": "a", "disliked": "b", "would_buy": "yes"}
    r = await client.post(f"/api/store/crm/thu-hang/{_token(app['link'])}/cam-nhan", data=form)
    assert r.status_code == 409 and r.json()["code"] == "missed"

    reg = (await owner_client.get("/api/desk/crm/cotrial/testers")).json()
    assert reg[0]["excluded"] and "Lỡ hạn" in reg[0]["excluded_reason"] and reg[0]["history"]["missed"] == 1
    other = await _candidate(db, title="Bình lọc nước để bàn")
    offer2 = await _offer(owner_client, other)
    assert (await _apply(client, _token(offer2["link"]), PHONE_A)).status_code == 201  # vẫn đăng ký được
    (app2,) = (await owner_client.get(f"/api/desk/crm/cotrial/offers/{offer2['id']}")).json()["applications"]
    assert app2["excluded"] and app2["history"]["missed"] == 1
    r = await _status(owner_client, app2["id"], "select")
    assert r.status_code == 409 and r.json()["code"] == "excluded"
    assert (await _status(owner_client, app2["id"], "select", override=True)).json()["status"] == "selected"
    r = await owner_client.patch(f"/api/desk/crm/cotrial/testers/{reg[0]['id']}", json={"excluded": False})
    assert r.json()["excluded"] is False and r.json()["excluded_reason"] is None
