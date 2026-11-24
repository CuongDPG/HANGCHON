"""Hợp đồng sự kiện (ARCHITECTURE mục 10): mỗi dòng có bên nghe đúng module, và các chuỗi không nằm trong bài vòng đời
(tests/integration/test_lifecycle.py) chạy đúng việc, lặp lại không sinh trùng."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.core import events
from app.core.db import SessionLocal
from app.core.timeutil import local_month_bounds_utc, month_key
from app.modules.catalog.models import InventoryItem, Review, ReviewStatus
from app.modules.content.models import ContentDraft
from app.modules.control.models import AIRun, ApprovalItem, ApprovalStatus
from app.modules.crm.models import Broadcast
from app.modules.finance.models import Expense, LedgerEntry, LedgerKind
from app.modules.selection.models import NoteAuthor, TasteProfile, TrialNote
from app.modules.sourcing.models import CandidateStage, DemandSignal
from app.modules.supply.models import InboundShipment, POKind, POStatus, PurchaseOrder, PurchaseOrderLine
from tests.orders.conftest import make_drop, make_inventory, make_product
from tests.selection.helpers import make_candidate

# sự kiện → module phải nghe (theo bảng ARCHITECTURE mục 10)
CONTRACT: dict[str, set[str]] = {
    "brief.created": set(),
    "candidate.assessed": {"sourcing", "selection"},
    "candidate.stage_changed": {"supply"},
    "candidate.selected": {"catalog", "selection"},
    "candidate.rejected": {"selection"},
    "price.approved": {"catalog"},
    "product.published": {"content"},
    "drop.opened": {"content", "crm"},
    "drop.closed": {"orders", "supply"},
    "order.created": {"crm"},
    "order.paid": {"finance", "catalog"},
    "order.shipped": {"catalog"},
    "order.delivered": {"catalog", "crm"},
    "order.refunded": {"finance", "catalog"},
    "order.cancelled": {"catalog"},
    "inbound.arrived": {"orders", "catalog"},
    "message.received": {"crm", "sourcing", "orders"},
    "customer.identified": {"inbox", "crm"},
    "review.published": {"content"},
    "find_request.created": {"sourcing"},
    "find_request.threshold": {"sourcing"},
    "tester.feedback_received": {"selection"},
    "post.published": set(),
    "expense.recorded": {"finance"},
}


def _listeners(name: str) -> set[str]:
    return {fn.__module__.split(".")[2] for fn in events.handlers(name) if fn.__module__.startswith("app.modules.")}


def test_every_event_has_the_listeners_of_the_contract() -> None:
    for name, expected in CONTRACT.items():
        assert _listeners(name) == expected, f"{name}: có {_listeners(name)}, hợp đồng {expected}"


async def test_candidate_rejected_marks_taste_for_learning(owner_client) -> None:
    c = await make_candidate(stage=CandidateStage.TRIAL)
    r = await owner_client.post(
        f"/api/desk/selection/candidates/{c.id}/stage", json={"to": "rejected", "reason": "Ốc lỏng sau một tuần"}
    )
    assert r.status_code == 200, r.text
    async with SessionLocal() as s:
        assert await s.scalar(select(func.count(TasteProfile.id))) >= 1  # c6: gu được đánh dấu cần học lại


async def test_drop_opened_drafts_content_and_regulars_announcement(owner_client) -> None:
    p = await make_product()
    d = await make_drop([(p, 300_000, 20)])
    async with SessionLocal() as s:
        for _ in range(2):  # lặp lại không sinh trùng
            await events.emit("drop.opened", {"drop_id": str(d.id)}, db=s)
        await s.commit()
        assert await s.scalar(select(func.count(ContentDraft.id)).where(ContentDraft.drop_id == d.id)) >= 1
        assert await s.scalar(select(func.count(Broadcast.id)).where(Broadcast.drop_id == d.id)) == 1


async def test_order_refunded_books_a_refund_once(db) -> None:
    from tests.finance.factory import make_order, pay

    o = await make_order(db)
    await pay(db, o)
    for _ in range(2):
        await events.emit("order.refunded", {"order_id": str(o.id), "amount_vnd": 50_000, "return_id": "r1"}, db=db)
    await db.commit()
    n = await db.scalar(
        select(func.count(LedgerEntry.id)).where(LedgerEntry.order_id == o.id, LedgerEntry.kind == LedgerKind.REFUND)
    )
    assert n == 1


async def test_expense_recorded_from_supply_payload_and_monthly_ai_cost(db) -> None:
    from app.modules.control.jobs import record_ai_cost

    payload = {"expense_id": None, "source": "supply", "source_key": "po:x:pay:1", "amount_vnd": 1_250_000,
               "category": "goods", "incurred_on": "2026-11-20", "description": "Thanh toán đơn LO-1",
               "vendor": "Xưởng Ví Dụ"}  # fmt: skip
    for _ in range(2):
        await events.emit("expense.recorded", payload, db=db)
    start, _ = local_month_bounds_utc(month_key())
    db.add(AIRun(task="sourcing.parse_brief", provider="fake", model="fake", tier="smart", status="ok",
                 cost_vnd=12_345, created_at=start + timedelta(hours=1)))  # fmt: skip
    await db.flush()
    for _ in range(2):
        assert await record_ai_cost(db, month_key()) == 12_345
    await db.commit()
    rows = (await db.execute(select(Expense).order_by(Expense.amount_vnd))).scalars().all()
    assert [(e.category.value, e.amount_vnd) for e in rows] == [("ai", 12_345), ("goods", 1_250_000)]
    assert await db.scalar(select(func.count(LedgerEntry.id)).where(LedgerEntry.kind == LedgerKind.EXPENSE)) == 2


async def test_review_published_suggests_a_post(db) -> None:
    p = await make_product()
    r = Review(product_id=p.id, token=uuid.uuid4().hex, rating=5, body="Giữ nóng tốt, nắp kín.",
               status=ReviewStatus.PUBLISHED, display_name="Khách Ví Dụ")  # fmt: skip
    db.add(r)
    await db.flush()
    for _ in range(2):
        await events.emit("review.published", {"review_id": str(r.id), "product_id": str(p.id)}, db=db)
    await db.commit()
    items = (
        await db.execute(select(ApprovalItem).where(ApprovalItem.ref_type == "reviews", ApprovalItem.ref_id == r.id))
    ).scalars().all()  # fmt: skip
    assert len(items) == 1 and items[0].action == "content.suggest_post" and "«Giữ nóng tốt" in items[0].payload["idea"]


async def test_find_request_created_becomes_demand(client) -> None:
    r = await client.post(
        "/api/store/catalog/finds", json={"title": "Hộp đựng gạo có cốc đong", "contact": "0900000777"}
    )
    assert r.status_code == 201, r.text
    async with SessionLocal() as s:
        assert await s.scalar(select(func.count(DemandSignal.id))) == 1


async def test_tester_feedback_becomes_trial_note(db) -> None:
    from app.modules.crm.models import TesterInvite, TesterInviteStatus
    from app.modules.crm.service import respond_invite
    from tests.finance.factory import make_customer

    c = await make_candidate(stage=CandidateStage.TRIAL)
    cust = await make_customer(db, "Chị Lan Ví Dụ")
    inv = TesterInvite(
        candidate_id=c.id, customer_id=cust.id, token=uuid.uuid4().hex, status=TesterInviteStatus.ACCEPTED
    )
    db.add(inv)
    await db.flush()
    await respond_invite(db, inv.token, "feedback", feedback="Nắp chặt, rửa dễ", rating=4)
    await db.commit()
    note = (await db.execute(select(TrialNote).where(TrialNote.tester_invite_id == inv.id))).scalar_one()
    assert note.author == NoteAuthor.TESTER and note.author_name == "Chị Lan Ví Dụ" and "Nắp chặt" in note.text


async def test_assessed_above_pass_score_suggests_sample(owner_client) -> None:
    from tests.sourcing.util import scanned_brief

    _, items = await scanned_brief(owner_client)
    cid = items[0]["id"]
    a = (await owner_client.post(f"/api/desk/assessment/candidates/{cid}/run", json={})).json()
    async with SessionLocal() as s:
        item = await s.scalar(
            select(ApprovalItem).where(
                ApprovalItem.action == "selection.suggest_sample", ApprovalItem.ref_id == uuid.UUID(cid)
            )
        )
    assert float(a["score_total"]) >= 70 and item is not None and item.status == ApprovalStatus.PENDING
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    card = (await owner_client.get(f"/api/desk/selection/candidates/{cid}")).json()["card"]
    assert card["stage"] == "sample"


async def test_restock_inbound_adds_stock_once(db) -> None:
    from app.modules.supply.models import InboundStatus
    from app.modules.supply.service import add_milestone

    p = await make_product()
    await make_inventory(p, 2)
    po = PurchaseOrder(code=f"LO-{uuid.uuid4().hex[:6]}", kind=POKind.RESTOCK, status=POStatus.SENT)
    po.lines = [PurchaseOrderLine(product_id=p.id, description="Bình", quantity=10, unit_price_amount=30,
                                  line_total_amount=300, unit_cost_vnd=120_000)]  # fmt: skip
    db.add(po)
    await db.flush()
    lot = InboundShipment(purchase_order_id=po.id, milestones=[])
    db.add(lot)
    await db.flush()
    await add_milestone(db, lot, InboundStatus.DELIVERED)
    await events.emit("inbound.arrived", {"inbound_shipment_id": str(lot.id)}, db=db)  # webhook gửi lại
    await db.commit()
    inv = (await db.execute(select(InventoryItem).where(InventoryItem.product_id == p.id))).scalar_one()
    assert inv.on_hand == 12 and inv.unit_cost_vnd == 120_000
