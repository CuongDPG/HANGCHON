"""g4 vận đơn + g5 báo tin: chọn hãng, tạo vận đơn qua control (auto/ask), theo dõi → shipment_events,
order.shipped / order.delivered, thu COD, giao lỗi → việc chờ chị, nhãn in, huỷ vận đơn, webhook."""

from __future__ import annotations

import json
import uuid

import httpx
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.integrations import get_driver
from app.modules.catalog.models import SaleMode
from app.modules.control.models import ApprovalItem
from app.modules.orders import shipping
from app.modules.orders.models import Notification, Order, Payment, Shipment, ShipmentEvent
from tests.orders.conftest import cart, make_inventory, make_product, names, place


async def _ready(client: httpx.AsyncClient, method: str = "cod") -> tuple[dict, uuid.UUID]:
    p = await make_product(mode=SaleMode.IN_STOCK, price=150_000)
    await make_inventory(p, 10)
    o = await place(client, cart((p, 2, None)), payment_method=method)
    async with SessionLocal() as s:
        oid = (await s.execute(select(Order.id).where(Order.code == o["code"]))).scalar_one()
    return o, oid


async def _sync(owner_client: httpx.AsyncClient, shipment_id: str) -> dict:
    r = await owner_client.post(f"/api/desk/orders/shipments/{shipment_id}/sync")
    assert r.status_code == 200, r.text
    return r.json()


async def test_quotes_pick_best_and_auto_create(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    o, oid = await _ready(client)
    q = (await owner_client.get(f"/api/desk/orders/{oid}/shipping-quotes")).json()
    assert {x["service"] for x in q["options"]} == {"standard", "express"} and q["recommended"]["service"] == "standard"
    assert "Chọn" in q["reason"]
    r = await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [str(oid)]})
    res = r.json()["results"][0]
    assert r.status_code == 200 and res["status"] == "applied" and res["tracking_code"].startswith("MK")
    again = (await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [str(oid)]})).json()["results"][0]
    assert again["status"] == "skipped"
    detail = (await owner_client.get(f"/api/desk/orders/{oid}")).json()
    sh = detail["shipments"][0]
    assert sh["status"] == "created" and sh["cod_amount_vnd"] == o["total_vnd"] and sh["selection_reason"]
    assert detail["can_ship"] is False and detail["can_cancel"] is False
    labels = (await owner_client.get("/api/desk/orders/labels", params={"ids": [str(oid)]})).json()
    assert labels[0]["tracking_code"] == sh["tracking_code"] and labels[0]["cod_amount_vnd"] == o["total_vnd"]


async def test_ask_level_waits_for_owner(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    _, oid = await _ready(client)
    await owner_client.patch("/api/desk/control/autonomy/orders.create_shipment", json={"level": "ask"})
    res = (await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [str(oid)]})).json()["results"][0]
    assert res["status"] == "pending"
    async with SessionLocal() as s:
        item = (await s.execute(select(ApprovalItem))).scalar_one()
        assert await s.scalar(select(func.count()).select_from(Shipment)) == 0
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    assert r.json()["status"] == "approved"
    async with SessionLocal() as s:
        assert await s.scalar(select(func.count()).select_from(Shipment)) == 1


async def test_tracking_to_delivered_collects_cod(
    client: httpx.AsyncClient, owner_client: httpx.AsyncClient, emitted: list
) -> None:
    o, oid = await _ready(client)
    sid = (await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [str(oid)]})).json()["results"][0][
        "shipment_id"
    ]
    mock = get_driver("shipping", "mock")
    mock.advance(1)
    assert (await _sync(owner_client, sid))["status"] == "picked_up"
    view = (await client.get(f"/api/store/orders/{o['code']}", params={"t": o["token"]})).json()
    assert view["status"] == "shipping" and view["shipment"]["tracking_code"] and not view["can_change_address"]
    mock.advance(2)
    assert (await _sync(owner_client, sid))["status"] == "out_for_delivery"
    mock.advance(1)
    sh = await _sync(owner_client, sid)
    assert sh["status"] == "delivered" and len(sh["events"]) == 5
    await _sync(owner_client, sid)  # gọi lặp không sinh mốc trùng
    async with SessionLocal() as s:
        assert await s.scalar(select(func.count()).select_from(ShipmentEvent)) == 5
        cod = (await s.execute(select(Payment).where(Payment.provider == "cod"))).scalar_one()
        assert cod.amount_vnd == o["total_vnd"] and cod.match_method == "cod_settlement"
        evs = (await s.execute(select(Notification.event).order_by(Notification.created_at))).scalars().all()
        assert evs == ["order_received", "shipped", "out_for_delivery", "delivered"]
    ns = names(emitted)
    assert ns.count("order.shipped") == 1 and ns.count("order.delivered") == 1 and ns.count("order.paid") == 1
    view = (await client.get(f"/api/store/orders/{o['code']}", params={"t": o["token"]})).json()
    assert view["status"] == "delivered" and view["payment_state"] == "paid" and view["can_request_return"]


async def test_failed_delivery_raises_owner_task(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    _, oid = await _ready(client)
    r = await owner_client.post(
        "/api/desk/orders/shipments", json={"order_ids": [str(oid)], "driver": "mock", "service": "fail"}
    )
    sid = r.json()["results"][0]["shipment_id"]
    get_driver("shipping", "mock").advance(6)
    assert (await _sync(owner_client, sid))["status"] == "returned"
    async with SessionLocal() as s:
        items = (
            (await s.execute(select(ApprovalItem).where(ApprovalItem.action == "orders.delivery_problem")))
            .scalars()
            .all()
        )
        assert len(items) == 1 and items[0].status == "pending"
        assert (await s.execute(select(Order.status).where(Order.id == oid))).scalar_one() == "returned"


async def test_cancel_shipment_and_webhook(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    _, oid = await _ready(client)
    res = (await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [str(oid)]})).json()["results"][0]
    r = await owner_client.post(f"/api/desk/orders/shipments/{res['shipment_id']}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    res2 = (await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [str(oid)]})).json()["results"][0]
    assert res2["status"] == "applied"
    mock = get_driver("shipping", "mock")
    mock.advance(2)
    info = await mock.track(res2["tracking_code"])
    body = json.dumps({"events": [e.model_dump(mode="json") for e in info.events]}).encode()
    hook = await client.post(
        "/api/hooks/shipping/mock", content=body, headers={"X-Mock-Signature": get_driver("payments").sign(body)}
    )
    assert hook.status_code == 200 and hook.json()["received"] == 3
    async with SessionLocal() as s:
        assert (await s.execute(select(Order.status).where(Order.id == oid))).scalar_one() == "shipping"


async def test_only_ready_orders_ship(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    _, oid = await _ready(client, method="bank_transfer")
    res = (await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [str(oid)]})).json()["results"][0]
    assert res["status"] == "skipped" and "Chờ chuyển khoản" in res["message"]


async def test_poll_active(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    _, oid = await _ready(client)
    await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [str(oid)]})
    get_driver("shipping", "mock").advance(1)
    async with SessionLocal() as s:
        assert await shipping.poll_active(s) >= 1
        await s.commit()
