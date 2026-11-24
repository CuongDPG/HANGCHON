"""e3 mở bán theo đợt: tạo, mở qua control.propose, hẹn giờ, tự đóng, trừ suất theo đơn đã trả, «Nhắc mình»."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core import events
from app.core.timeutil import now_utc
from app.integrations import get_driver
from app.modules.catalog import drops as svc
from app.modules.catalog.models import Drop, DropStatus
from app.modules.control.models import ApprovalItem, ApprovalStatus
from tests.catalog.factories import published_product


@pytest.fixture
def drop_events():
    seen: list[tuple[str, dict]] = []

    async def opened(db, payload):
        seen.append(("opened", payload))

    async def closed(db, payload):
        seen.append(("closed", payload))

    events.on("drop.opened")(opened)
    events.on("drop.closed")(closed)
    yield seen
    events._handlers["drop.opened"].remove(opened)
    events._handlers["drop.closed"].remove(closed)


def _body(p, **kw):
    return {
        "title": "Đồ bếp gọn", "closes_at": (now_utc() + timedelta(days=3)).isoformat(),
        "expected_arrival_date": (now_utc() + timedelta(days=20)).date().isoformat(),
        "items": [{"product_id": str(p.id), "slots_total": 2, "max_per_order": 2}], **kw,
    }  # fmt: skip


async def test_owner_creates_and_opens_drop(db, owner_client, drop_events):
    p = await published_product(db)
    await db.commit()
    r = await owner_client.post("/api/desk/catalog/drops", json=_body(p))
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["code"] == "D1" and d["label"] == "Đợt 1" and d["status"] == "draft"
    assert d["items"][0]["price_vnd"] == 385000
    r = await owner_client.post(f"/api/desk/catalog/drops/{d['id']}/open")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "open"
    assert drop_events == [("opened", {"drop_id": d["id"]})]
    item = await db.get(ApprovalItem, r.json()["approval_item_id"])
    assert item.status == ApprovalStatus.APPROVED and not item.ai_generated
    pub = (await owner_client.get("/api/store/catalog/drops")).json()
    assert [x["slug"] for x in pub["open"]] == [d["slug"]]
    detail = (await owner_client.get(f"/api/store/catalog/drops/{d['slug']}")).json()
    assert detail["items"][0]["slots_left"] == 2 and detail["items"][0]["available"]
    shelf = (await owner_client.get("/api/store/catalog/shelf")).json()
    assert shelf["items"][0]["drop"]["label"] == "Đợt 1" and shelf["items"][0]["available"]


async def test_helper_open_waits_for_owner(db, owner_client, helper_client, drop_events):
    p = await published_product(db)
    await db.commit()
    d = (await helper_client.post("/api/desk/catalog/drops", json=_body(p))).json()
    r = await helper_client.post(f"/api/desk/catalog/drops/{d['id']}/open")
    assert r.json()["status"] == "pending_review" and drop_events == []
    r = await owner_client.post(f"/api/desk/control/approvals/{r.json()['approval_item_id']}/approve", json={})
    assert r.status_code == 200, r.text
    assert (await owner_client.get(f"/api/desk/catalog/drops/{d['id']}")).json()["status"] == "open"
    assert len(drop_events) == 1


async def test_open_validation(db, owner_client):
    p = await published_product(db)
    p.status = p.status.__class__.PAUSED
    await db.commit()
    d = (await owner_client.post("/api/desk/catalog/drops", json=_body(p))).json()
    r = await owner_client.post(f"/api/desk/catalog/drops/{d['id']}/open")
    assert r.status_code == 400 and r.json()["code"] == "drop_unpublished"
    past = (
        await owner_client.post(
            "/api/desk/catalog/drops", json=_body(p, closes_at=(now_utc() - timedelta(hours=1)).isoformat())
        )
    ).json()
    r = await owner_client.post(f"/api/desk/catalog/drops/{past['id']}/open")
    assert r.json()["code"] == "drop_deadline"
    empty = (await owner_client.post("/api/desk/catalog/drops", json={**_body(p), "items": []})).json()
    assert (await owner_client.post(f"/api/desk/catalog/drops/{empty['id']}/open")).json()["code"] == "drop_empty"


async def test_scheduled_then_tick_opens_and_closes(db, owner_client, client, drop_events):
    p = await published_product(db)
    await db.commit()
    opens = now_utc() + timedelta(days=1)
    d = (await owner_client.post("/api/desk/catalog/drops", json=_body(p, opens_at=opens.isoformat()))).json()
    r = await owner_client.post(f"/api/desk/catalog/drops/{d['id']}/open")
    assert r.json()["status"] == "scheduled" and drop_events == []
    # khách bấm «Nhắc mình» ở đợt sắp mở (trùng số thì không thêm)
    assert (
        await client.post(f"/api/store/catalog/drops/{d['slug']}/remind", json={"contact": "+84 000 000 001"})
    ).json() == {"added": True}
    assert (
        await client.post(f"/api/store/catalog/drops/{d['slug']}/remind", json={"contact": "0000000001"})
    ).json() == {"added": False}
    upcoming = (await client.get("/api/store/catalog/drops")).json()["upcoming"]
    assert upcoming[0]["slug"] == d["slug"]

    assert await svc.tick(db, now=opens + timedelta(minutes=1)) == {"opened": 1, "closed": 0}
    await db.commit()
    assert drop_events[0][0] == "opened"
    # khách đã bấm nhắc → một việc chờ «nhắn khách»
    item = (
        await db.execute(select(ApprovalItem).where(ApprovalItem.action == "catalog.send_drop_reminders"))
    ).scalar_one()
    assert item.preview["count"] == 1
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    assert r.json()["result"] == {"sent": 1}
    assert get_driver("notify").outbox[0].to == "0000000001"
    r = await client.post(f"/api/store/catalog/drops/{d['slug']}/remind", json={"contact": "0000000002"})
    assert r.status_code == 409

    assert await svc.tick(db, now=now_utc() + timedelta(days=5)) == {"opened": 0, "closed": 1}
    await db.commit()
    assert [e[0] for e in drop_events] == ["opened", "closed"]
    assert await svc.tick(db, now=now_utc() + timedelta(days=6)) == {"opened": 0, "closed": 0}


async def test_order_paid_recounts_slots_and_closes_sold_out(db, owner_client, drop_events):
    from app.modules.orders.models import Order, OrderItem, OrderStatus, PaymentState

    p = await published_product(db)
    await db.commit()
    d = (await owner_client.post("/api/desk/catalog/drops", json=_body(p))).json()
    await owner_client.post(f"/api/desk/catalog/drops/{d['id']}/open")
    item_id = d["items"][0]["id"]
    o = Order(code="HCTEST1", drop_id=d["id"], status=OrderStatus.CONFIRMED, payment_state=PaymentState.PAID,
              recipient_name="Khách thử", recipient_phone="0000000000", placed_at=now_utc())  # fmt: skip
    db.add(o)
    await db.flush()
    db.add(OrderItem(order_id=o.id, product_id=p.id, drop_item_id=item_id, name=p.name, quantity=2))
    await db.flush()
    for _ in range(2):  # phát lặp lại vẫn đếm đúng
        await events.emit("order.paid", {"order_id": str(o.id), "payment_id": None}, db=db)
    await db.commit()
    drop = await db.get(Drop, d["id"])
    await db.refresh(drop, ["items"])
    assert drop.items[0].slots_reserved == 2
    assert drop.status == DropStatus.CLOSED and drop_events[-1][0] == "closed"


async def test_arrived_and_cancel(db, owner_client, helper_client):
    p = await published_product(db)
    await db.commit()
    d = (await owner_client.post("/api/desk/catalog/drops", json=_body(p))).json()
    assert (
        await owner_client.post(f"/api/desk/catalog/drops/{d['id']}/arrived", json={"arrived_on": "2026-12-12"})
    ).status_code == 409
    await owner_client.post(f"/api/desk/catalog/drops/{d['id']}/open")
    assert (await helper_client.post(f"/api/desk/catalog/drops/{d['id']}/close")).status_code == 403
    assert (await owner_client.post(f"/api/desk/catalog/drops/{d['id']}/close")).json()["status"] == "closed"
    r = await owner_client.post(f"/api/desk/catalog/drops/{d['id']}/arrived", json={"arrived_on": "2026-12-12"})
    assert r.json()["status"] == "fulfilling" and r.json()["actual_arrival_date"] == "2026-12-12"
    pub = (await owner_client.get("/api/store/catalog/drops")).json()
    assert pub["arrived"][0]["slug"] == d["slug"]
    other = (await owner_client.post("/api/desk/catalog/drops", json=_body(p, title="Đợt khác"))).json()
    assert (await owner_client.post(f"/api/desk/catalog/drops/{other['id']}/cancel")).json()["status"] == "cancelled"
    assert (await owner_client.get(f"/api/store/catalog/drops/{other['slug']}")).status_code == 404
