"""e5 theo dõi đơn (tra cứu, hành trình có chặng hàng về, hỏi về đơn, đổi địa chỉ) + g3 tổng hợp đợt
(drop.closed, inbound.arrived, báo hàng đang về) + g8 tồn kho nhỏ."""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx
from sqlalchemy import select

from app.core import events
from app.core.db import SessionLocal
from app.core.timeutil import local_today, now_utc
from app.modules.catalog.models import DropStatus, SaleMode
from app.modules.control.models import AIActivity, ApprovalItem
from app.modules.orders import drops
from app.modules.orders.models import Notification, Order, OrderEvent
from app.modules.supply.models import InboundShipment, InboundStatus, POKind, PurchaseOrder
from tests.orders.conftest import PHONE, cart, make_drop, make_inventory, make_product, place, send_transfer


async def _lot(drop_id: uuid.UUID, status: InboundStatus, note: str = "Rời kho Osaka") -> uuid.UUID:
    async with SessionLocal() as s:
        po = PurchaseOrder(code=f"PO-{uuid.uuid4().hex[:6]}", kind=POKind.BATCH, drop_id=drop_id)
        s.add(po)
        await s.flush()
        lot = InboundShipment(
            purchase_order_id=po.id, code="Lô Osaka", status=status, eta=local_today() + timedelta(days=5),
            milestones=[{"status": status.value, "at": now_utc().isoformat(), "note": note}],
        )  # fmt: skip
        s.add(lot)
        await s.commit()
        return lot.id


async def test_lookup_by_phone_and_code(client: httpx.AsyncClient) -> None:
    p = await make_product()
    d = await make_drop([(p, 100_000, 5)])
    o = await place(client, cart((p, 1, d)))
    r = await client.post(
        "/api/store/orders/lookup", json={"phone": "090 000 0101", "code": o["code"].lower().replace("-", " ")}
    )
    assert r.status_code == 200 and r.json() == {"code": o["code"], "token": o["token"]}
    wrong = await client.post("/api/store/orders/lookup", json={"phone": "0900000999", "code": o["code"]})
    assert wrong.status_code == 404
    assert (await client.get(f"/api/store/orders/{o['code']}", params={"t": "saisaisaisai"})).status_code == 404
    assert (await client.get(f"/api/store/orders/{o['code']}")).status_code == 422


async def test_timeline_includes_inbound_leg(client: httpx.AsyncClient) -> None:
    p = await make_product()
    d = await make_drop([(p, 100_000, 5)])
    o = await place(client, cart((p, 1, d)), payment_method="cod")
    await _lot(d.id, InboundStatus.INTERNATIONAL_TRANSIT)
    async with SessionLocal() as s:
        await drops.on_drop_closed(s, d.id)
        await drops.on_drop_closed(s, d.id)  # lặp lại không ghi trùng
        await s.commit()
    view = (await client.get(f"/api/store/orders/{o['code']}", params={"t": o["token"]})).json()
    steps = {s["key"]: s for s in view["timeline"]}
    assert steps["drop"]["status"] == "done" and steps["inbound"]["status"] == "current"
    assert steps["inbound"]["title"] == "Rời kho Osaka" and steps["arrived"]["meta"].startswith("Dự kiến")
    assert view["headline"] == "Hàng đang trên đường về Việt Nam"
    async with SessionLocal() as s:
        kinds = (await s.execute(select(OrderEvent.kind).where(OrderEvent.kind == "drop_closed"))).scalars().all()
        assert len(kinds) == 1
        assert await drops.notify_arriving(s) == 1
        assert await drops.notify_arriving(s) == 0
        await s.commit()
        n = (await s.execute(select(Notification).where(Notification.event == "stock_arriving"))).scalar_one()
        assert "đang trên đường về" in n.body


async def test_inbound_arrived_moves_orders_when_all_lots_in(client: httpx.AsyncClient) -> None:
    p = await make_product()
    d = await make_drop([(p, 100_000, 5)])
    o = await place(client, cart((p, 1, d)), payment_method="cod")
    lot_a = await _lot(d.id, InboundStatus.DELIVERED, "Về tới kho")
    lot_b = await _lot(d.id, InboundStatus.CUSTOMS, "Đang thông quan")
    async with SessionLocal() as s:
        await events.emit("inbound.arrived", {"inbound_shipment_id": str(lot_a)}, db=s)
        await s.commit()
    assert (await client.get(f"/api/store/orders/{o['code']}", params={"t": o["token"]})).json()[
        "status"
    ] == "awaiting_stock"
    async with SessionLocal() as s:
        lot = await s.get(InboundShipment, lot_b)
        lot.status = InboundStatus.DELIVERED
        await events.emit("inbound.arrived", {"inbound_shipment_id": str(lot_b)}, db=s)
        await events.emit("inbound.arrived", {"inbound_shipment_id": str(lot_b)}, db=s)
        await s.commit()
    view = (await client.get(f"/api/store/orders/{o['code']}", params={"t": o["token"]})).json()
    assert view["status"] == "ready_to_ship" and view["headline"] == "Mình đang chuẩn bị gói hàng"


async def test_arrival_is_one_milestone_in_timeline(client: httpx.AsyncClient) -> None:
    """Lô về kho chỉ hiện một mốc «Về tới kho» (trước đây chặng đường về cũng ghi lại đúng mốc đó)."""
    p = await make_product()
    d = await make_drop([(p, 100_000, 5)])
    o = await place(client, cart((p, 1, d)), payment_method="cod")
    async with SessionLocal() as s:
        po = PurchaseOrder(code=f"PO-{uuid.uuid4().hex[:6]}", kind=POKind.BATCH, drop_id=d.id)
        s.add(po)
        await s.flush()
        t0 = now_utc() - timedelta(days=3)
        lot = InboundShipment(purchase_order_id=po.id, code="Lô 1", status=InboundStatus.DELIVERED, milestones=[
            {"status": "international_transit", "at": t0.isoformat(), "note": None},
            {"status": "delivered", "at": (t0 + timedelta(days=2)).isoformat(), "note": None},
        ])  # fmt: skip
        s.add(lot)
        await s.flush()
        await events.emit("inbound.arrived", {"inbound_shipment_id": str(lot.id)}, db=s)
        await s.commit()
    view = (await client.get(f"/api/store/orders/{o['code']}", params={"t": o["token"]})).json()
    titles = [st["title"] for st in view["timeline"]]
    assert sum("về tới kho" in t.lower() for t in titles) == 1, titles
    steps = {st["key"]: st for st in view["timeline"]}
    assert steps["inbound"]["title"] == "Hàng đã về Việt Nam" and steps["inbound"]["status"] == "done"
    assert steps["arrived"]["status"] == "done" and steps["arrived"]["at"]


async def test_drop_closed_event_and_overview(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    a, b = await make_product(), await make_product(name="Hộp gia vị")
    d = await make_drop([(a, 100_000, 10), (b, 50_000, None)])
    o1 = await place(client, cart((a, 2, d), (b, 1, d)))
    await place(client, cart((a, 1, d)), payment_method="cod", phone="0900000102")
    await send_transfer(client, o1["payment"]["amount_due_vnd"], o1["payment"]["transfer_content"])
    await place(client, cart((a, 3, d)), phone="0900000103")
    async with SessionLocal() as s:
        drop = await s.get(drops.Drop, d.id)
        drop.status = DropStatus.CLOSED
        assert await events.emit("drop.closed", {"drop_id": str(d.id)}, db=s) >= 1
        await s.commit()
    rows = (await owner_client.get("/api/desk/orders/drops")).json()
    ov = next(x for x in rows if x["id"] == str(d.id))
    item_a = next(i for i in ov["items"] if i["product_id"] == str(a.id))
    assert item_a["quantity_confirmed"] == 3 and item_a["quantity_pending"] == 3
    assert (
        ov["orders_total"] == 3 and ov["orders_pending"] == 1 and ov["slots_total"] is None and ov["slots_taken"] == 7
    )
    async with SessionLocal() as s:
        assert len((await s.execute(select(OrderEvent).where(OrderEvent.kind == "drop_closed"))).scalars().all()) == 3


async def test_ask_question_and_owner_replies(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    p = await make_product()
    d = await make_drop([(p, 100_000, 5)])
    o = await place(client, cart((p, 1, d)))
    r = await client.post(
        f"/api/store/orders/{o['code']}/questions", json={"t": o["token"], "message": "Bao giờ hàng về ạ?"}
    )
    assert r.status_code == 201 and any(e["title"] == "Bạn đã hỏi về đơn này" for e in r.json()["events"])
    async with SessionLocal() as s:
        item = (await s.execute(select(ApprovalItem))).scalar_one()
        assert item.action == "orders.customer_question" and item.preview["question"] == "Bao giờ hàng về ạ?"
    a = await owner_client.post(
        f"/api/desk/control/approvals/{item.id}/approve", json={"payload": {"reply": "Khoảng 12/12 bạn nhé."}}
    )
    assert a.json()["status"] == "approved"
    async with SessionLocal() as s:
        n = (await s.execute(select(Notification).where(Notification.event == "other"))).scalar_one()
        assert "Khoảng 12/12" in n.body


async def test_change_address_until_shipped(client: httpx.AsyncClient) -> None:
    p = await make_product()
    d = await make_drop([(p, 100_000, 5)])
    o = await place(client, cart((p, 1, d)))
    r = await client.post(
        f"/api/store/orders/{o['code']}/address",
        json={"t": o["token"], "address_line": "99 Đường Mới", "province": "Đà Nẵng", "recipient_name": "Lan Nguyễn"},
    )
    assert (
        r.status_code == 200
        and r.json()["address_line"] == "99 Đường Mới"
        and r.json()["recipient_name"] == "Lan Nguyễn"
    )
    bad = await client.post(f"/api/store/orders/{o['code']}/address", json={"t": o["token"], "address_line": "x"})
    assert bad.status_code == 400
    async with SessionLocal() as s:
        order = (await s.execute(select(Order))).scalar_one()
        order.status = "shipping"
        await s.commit()
    locked = await client.post(
        f"/api/store/orders/{o['code']}/address", json={"t": o["token"], "address_line": "1 A", "province": "Huế"}
    )
    assert locked.status_code == 409


async def test_address_suggestions(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/store/orders/address-suggestions", params={"q": "ho chi"})
    assert [x["name"] for x in r.json()] == ["TP. Hồ Chí Minh"]
    assert len((await client.get("/api/store/orders/address-suggestions")).json()) == 6


async def test_low_stock_alert_once(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    s_ = await make_product(name="Khăn lau", mode=SaleMode.IN_STOCK, price=89_000)
    await make_inventory(s_, 4, threshold=2)
    await place(client, cart((s_, 1, None)), payment_method="cod")
    async with SessionLocal() as s:
        assert (await s.execute(select(ApprovalItem))).scalars().all() == []
    await place(client, cart((s_, 1, None)), payment_method="cod", phone="0900000102")
    await place(client, cart((s_, 1, None)), payment_method="cod", phone="0900000103")
    async with SessionLocal() as s:
        # mặc định AI tự làm (chỉ báo nội bộ): ghi Nhật ký AI một lần, không lặp mỗi lần bán, không tạo việc chờ
        acts = (await s.execute(select(AIActivity).where(AIActivity.action == "orders.restock_alert"))).scalars().all()
        assert len(acts) == 1 and acts[0].payload["available"] == 2 and "Khăn lau" in acts[0].summary
        assert (await s.execute(select(ApprovalItem))).scalars().all() == []
    inv = (await owner_client.get("/api/desk/orders/inventory")).json()
    assert inv[0]["available"] == 1 and inv[0]["pending_orders_qty"] == 3 and inv[0]["low"] is True
    assert PHONE  # dùng hằng của conftest


async def test_low_stock_alert_ask_level(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    r = await owner_client.patch("/api/desk/control/autonomy/orders.restock_alert", json={"level": "ask"})
    assert r.status_code == 200, r.text
    s_ = await make_product(name="Khăn lau", mode=SaleMode.IN_STOCK, price=89_000)
    await make_inventory(s_, 3, threshold=2)
    await place(client, cart((s_, 1, None)), payment_method="cod")
    await place(client, cart((s_, 1, None)), payment_method="cod", phone="0900000102")
    async with SessionLocal() as s:
        items = (
            (await s.execute(select(ApprovalItem).where(ApprovalItem.action == "orders.restock_alert"))).scalars().all()
        )
        assert len(items) == 1 and items[0].preview["available"] == 1  # việc đang chờ được cập nhật, không lặp
