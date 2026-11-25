"""«AI tự làm = ghi nhật ký, hoàn tác được» cho g2 (khớp tiền), g4 (vận đơn), g5 (báo tin); g8 tồn kho nhỏ
(tồn đầu kỳ, điều chỉnh có lý do + vết, ngưỡng theo món); g9 đẩy trạng thái giao lên sàn (idempotent); driver sàn thật."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.core.enums import Channel
from app.core.timeutil import now_utc
from app.integrations import get_driver
from app.integrations.base import IntegrationError
from app.integrations.marketplaces.shopee import ship_order_body
from app.modules.catalog.models import InventoryItem, InventoryMovement, SaleMode
from app.modules.control.models import AIActivity, ApprovalItem, AuditLog
from app.modules.orders import marketplace
from app.modules.orders.models import Notification, Order, OrderEvent, Payment, Shipment
from tests.orders.conftest import cart, make_drop, make_inventory, make_product, names, place, send_transfer


async def _activities(action: str) -> list[AIActivity]:
    async with SessionLocal() as s:
        return list(
            (await s.execute(select(AIActivity).where(AIActivity.action == action).order_by(AIActivity.created_at)))
            .scalars()
            .all()
        )


async def _order(oid: uuid.UUID | str) -> Order:
    async with SessionLocal() as s:
        return (await s.execute(select(Order).where(Order.id == uuid.UUID(str(oid))))).scalar_one()


# ---- g2: khớp tiền ---------------------------------------------------------------------------------------------------


async def _paid_order(client: httpx.AsyncClient, *, stock: bool = False) -> dict:
    if stock:
        p = await make_product(mode=SaleMode.IN_STOCK, price=150_000)
        await make_inventory(p, 10)
        o = await place(client, cart((p, 1, None)))
    else:
        p = await make_product()
        d = await make_drop([(p, 300_000, 5)])
        o = await place(client, cart((p, 1, d)))
    r = await send_transfer(client, o["payment"]["amount_due_vnd"], o["payment"]["transfer_content"])
    assert r.json()["received"] == 1
    return o


async def test_auto_match_is_logged_and_undo_unmatches(
    client: httpx.AsyncClient, owner_client: httpx.AsyncClient, emitted: list
) -> None:
    o = await _paid_order(client)
    acts = await _activities("orders.match_payment")
    assert len(acts) == 1 and acts[0].undoable and acts[0].mode == "auto" and o["code"] in acts[0].summary
    today = (await owner_client.get("/api/desk/control/today")).json()
    labels = {g["label"]: g["count"] for g in today["ai_done"]["groups"]}
    assert labels["Khớp khoản chuyển tới với đơn"] == 1
    # chị hoàn tác: đơn về chờ chuyển khoản, khoản tiền về «cần xem» để khớp lại đúng đơn
    r = await owner_client.post(f"/api/desk/control/activity/{acts[0].id}/undo")
    assert r.status_code == 200, r.text
    async with SessionLocal() as s:
        order = (await s.execute(select(Order).where(Order.code == o["code"]))).scalar_one()
        pay = (await s.execute(select(Payment))).scalar_one()
        assert order.status == "pending_payment" and order.paid_vnd == 0 and order.paid_at is None
        assert order.payment_state == "unpaid" and order.payment_due_at > now_utc()
        assert pay.status == "needs_review" and pay.order_id is None
        review = (
            await s.execute(select(ApprovalItem).where(ApprovalItem.action == "orders.review_payment"))
        ).scalar_one()
        assert review.status == "pending" and review.payload["decision"] == "match"
    assert names(emitted).count("order.unpaid") == 1
    again = await owner_client.post(f"/api/desk/control/activity/{acts[0].id}/undo")
    assert again.status_code == 409
    # khớp tay lại đúng đơn: đơn được xác nhận lại
    r = await owner_client.post(f"/api/desk/orders/payments/{pay.id}/match", json={"order_code": o["code"]})
    assert r.status_code == 200 and r.json()["status"] == "matched"
    assert (await _order(order.id)).paid_at is not None


async def test_undo_match_refused_once_shipped(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    o = await _paid_order(client, stock=True)
    order = await _order((await owner_client.get("/api/desk/orders", params={"q": o["code"]})).json()["items"][0]["id"])
    assert order.status == "ready_to_ship"
    res = (await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [str(order.id)]})).json()
    assert res["results"][0]["status"] == "applied"
    act = (await _activities("orders.match_payment"))[0]
    r = await owner_client.post(f"/api/desk/control/activity/{act.id}/undo")
    assert r.status_code == 409 and "vận đơn" in r.json()["detail"]
    assert (await _order(order.id)).paid_at is not None  # không đổi gì
    get_driver("shipping", "mock").advance(1)
    await owner_client.post(f"/api/desk/orders/shipments/{res['results'][0]['shipment_id']}/sync")
    r = await owner_client.post(f"/api/desk/control/activity/{act.id}/undo")
    assert r.status_code == 409 and "Đang giao" in r.json()["detail"]


async def test_match_ask_level_waits_then_applies(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    await owner_client.patch("/api/desk/control/autonomy/orders.match_payment", json={"level": "ask"})
    p = await make_product()
    d = await make_drop([(p, 300_000, 5)])
    o = await place(client, cart((p, 1, d)))
    await send_transfer(client, o["payment"]["amount_due_vnd"], o["payment"]["transfer_content"])
    async with SessionLocal() as s:
        item = (await s.execute(select(ApprovalItem).where(ApprovalItem.action == "orders.match_payment"))).scalar_one()
        assert (await s.execute(select(Payment.status))).scalar_one() == "received"
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    assert r.json()["status"] == "approved"
    view = (await client.get(f"/api/store/orders/{o['code']}", params={"t": o["token"]})).json()
    assert view["payment_state"] == "paid"


async def test_match_off_level_goes_to_owner(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    await owner_client.patch("/api/desk/control/autonomy/orders.match_payment", json={"level": "off"})
    p = await make_product()
    d = await make_drop([(p, 300_000, 5)])
    o = await place(client, cart((p, 1, d)))
    await send_transfer(client, o["payment"]["amount_due_vnd"], o["payment"]["transfer_content"])
    async with SessionLocal() as s:
        assert (await s.execute(select(Payment.status))).scalar_one() == "needs_review"
        item = (
            await s.execute(select(ApprovalItem).where(ApprovalItem.action == "orders.review_payment"))
        ).scalar_one()
        assert item.payload["order_code"] == o["code"]


async def test_helper_cannot_undo(client: httpx.AsyncClient, helper_client: httpx.AsyncClient) -> None:
    await _paid_order(client)
    act = (await _activities("orders.match_payment"))[0]
    r = await helper_client.post(f"/api/desk/control/activity/{act.id}/undo")
    assert r.status_code == 403


# ---- g4: vận đơn ------------------------------------------------------------------------------------------------------


async def test_shipment_undo_cancels_it(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    p = await make_product(mode=SaleMode.IN_STOCK, price=150_000)
    await make_inventory(p, 10)
    o = await place(client, cart((p, 1, None)), payment_method="cod")
    oid = (await owner_client.get("/api/desk/orders", params={"q": o["code"]})).json()["items"][0]["id"]
    res = (await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [oid]})).json()["results"][0]
    act = (await _activities("orders.create_shipment"))[0]
    assert act.undoable and act.result["shipment_id"] == res["shipment_id"]
    r = await owner_client.post(f"/api/desk/control/activity/{act.id}/undo")
    assert r.status_code == 200, r.text
    async with SessionLocal() as s:
        assert (await s.execute(select(Shipment.status))).scalar_one() == "cancelled"
    # đơn lại tạo vận đơn được
    again = (await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [oid]})).json()["results"][0]
    assert again["status"] == "applied"
    # hãng đã lấy hàng → không hoàn tác được
    get_driver("shipping", "mock").advance(1)
    await owner_client.post(f"/api/desk/orders/shipments/{again['shipment_id']}/sync")
    act2 = (await _activities("orders.create_shipment"))[1]
    r = await owner_client.post(f"/api/desk/control/activity/{act2.id}/undo")
    assert r.status_code == 409


# ---- g5: báo tin -------------------------------------------------------------------------------------------------------


async def test_notifications_logged_not_undoable(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    p = await make_product(mode=SaleMode.IN_STOCK, price=150_000)
    await make_inventory(p, 10)
    await place(client, cart((p, 1, None)), payment_method="cod")
    acts = await _activities("orders.notify_customer")
    assert len(acts) == 1 and acts[0].undoable is False and acts[0].summary.startswith("Đã gửi qua")
    r = await owner_client.post(f"/api/desk/control/activity/{acts[0].id}/undo")
    assert r.status_code == 400 and r.json()["code"] == "not_undoable"
    lst = (await owner_client.get("/api/desk/control/autonomy")).json()
    spec = next(a for a in lst if a["action"] == "orders.notify_customer")
    assert spec["customer_facing"] is True and spec["level"] == "auto"


async def test_notification_ask_level_waits_and_return_skips(
    client: httpx.AsyncClient, owner_client: httpx.AsyncClient
) -> None:
    await owner_client.patch("/api/desk/control/autonomy/orders.notify_customer", json={"level": "ask"})
    p = await make_product(mode=SaleMode.IN_STOCK, price=150_000)
    await make_inventory(p, 10)
    await place(client, cart((p, 1, None)), payment_method="cod")
    await place(client, cart((p, 1, None)), payment_method="cod", phone="0900000102")
    async with SessionLocal() as s:
        items = list(
            (
                await s.execute(
                    select(ApprovalItem)
                    .where(ApprovalItem.action == "orders.notify_customer")
                    .order_by(ApprovalItem.created_at)
                )
            ).scalars()
        )
        assert len(items) == 2 and "Hàng Chọn đã nhận đơn" in items[0].preview["body"]
        assert {n.status for n in (await s.execute(select(Notification))).scalars()} == {"queued"}
    await owner_client.post(f"/api/desk/control/approvals/{items[0].id}/approve", json={})
    await owner_client.post(f"/api/desk/control/approvals/{items[1].id}/return", json={"note": "Để mình gọi"})
    async with SessionLocal() as s:
        statuses = sorted((await s.execute(select(Notification.status))).scalars())
        assert statuses == ["sent", "skipped"]
    assert len(get_driver("notify").outbox) == 1


async def test_notification_off_level_skips(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    await owner_client.patch("/api/desk/control/autonomy/orders.notify_customer", json={"level": "off"})
    p = await make_product(mode=SaleMode.IN_STOCK, price=150_000)
    await make_inventory(p, 10)
    await place(client, cart((p, 1, None)), payment_method="cod")
    async with SessionLocal() as s:
        n = (await s.execute(select(Notification))).scalar_one()
        assert n.status == "skipped" and "tắt" in n.error
    assert get_driver("notify").outbox == []


# ---- g8: tồn kho nhỏ ---------------------------------------------------------------------------------------------------


async def test_inventory_opening_adjust_threshold(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    p = await make_product(name="Khăn lau", mode=SaleMode.IN_STOCK, price=89_000)
    cands = (await owner_client.get("/api/desk/orders/inventory/candidates")).json()
    assert any(c["product_id"] == str(p.id) for c in cands)
    r = await owner_client.post(
        "/api/desk/orders/inventory", json={"product_id": str(p.id), "on_hand": 12, "note": "Kiểm kho đầu tháng"}
    )
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["on_hand"] == 12 and row["threshold_is_default"] and row["low_stock_threshold"] == 3
    assert row["last_counted_at"] is not None
    dup = await owner_client.post("/api/desk/orders/inventory", json={"product_id": str(p.id), "on_hand": 1})
    assert dup.status_code == 409
    iid = row["inventory_item_id"]
    # bán được thật từ tồn vừa nhập
    await place(client, cart((p, 2, None)), payment_method="cod")
    # điều chỉnh: trừ hỏng, đếm lại, lý do bắt buộc, không âm
    url = f"/api/desk/orders/inventory/{iid}/adjust"
    bad = await owner_client.post(url, json={"mode": "delta", "quantity": -1, "kind": "damaged", "reason": " "})
    assert bad.status_code == 422
    neg = await owner_client.post(url, json={"mode": "delta", "quantity": -50, "kind": "damaged", "reason": "Vỡ"})
    assert neg.status_code == 400
    r = await owner_client.post(url, json={"mode": "delta", "quantity": -2, "kind": "damaged", "reason": "Rách 2 cái"})
    assert r.status_code == 200 and r.json()["on_hand"] == 10 and r.json()["available"] == 8
    r = await owner_client.post(url, json={"mode": "set", "quantity": 9, "reason": "Đếm lại cuối tuần"})
    assert r.json()["on_hand"] == 9
    # ngưỡng riêng theo món, rồi về ngưỡng chung
    r = await owner_client.patch(f"/api/desk/orders/inventory/{iid}", json={"low_stock_threshold": 8})
    assert r.json()["low_stock_threshold"] == 8 and r.json()["threshold_is_default"] is False and r.json()["low"]
    acts = await _activities("orders.restock_alert")
    assert len(acts) == 1  # chạm ngưỡng mới → báo chị (AI tự làm)
    r = await owner_client.patch(f"/api/desk/orders/inventory/{iid}", json={"low_stock_threshold": None})
    assert r.json()["threshold_is_default"] is True and r.json()["low_stock_threshold"] == 3
    moves = (await owner_client.get(f"/api/desk/orders/inventory/{iid}/movements")).json()
    assert [m["delta_on_hand"] for m in moves] == [-1, -2, 12]
    assert moves[1]["reason"] == "damaged" and "Rách 2 cái" in moves[1]["note"] and moves[0]["created_by_name"]
    assert "Tồn đầu kỳ" in moves[2]["note"]
    async with SessionLocal() as s:
        audits = (await s.execute(select(AuditLog.action).where(AuditLog.action.like("orders.inventory%")))).scalars()
        assert sorted(audits) == [
            "orders.inventory_adjusted",
            "orders.inventory_adjusted",
            "orders.inventory_opening",
            "orders.inventory_threshold",
            "orders.inventory_threshold",
        ]


async def test_inventory_restock_alert_again_after_restock(
    client: httpx.AsyncClient, owner_client: httpx.AsyncClient
) -> None:
    p = await make_product(name="Khăn lau", mode=SaleMode.IN_STOCK, price=89_000)
    inv = await make_inventory(p, 3, threshold=2)
    await place(client, cart((p, 1, None)), payment_method="cod")
    assert len(await _activities("orders.restock_alert")) == 1
    url = f"/api/desk/orders/inventory/{inv.id}/adjust"
    await owner_client.post(url, json={"mode": "delta", "quantity": 1, "kind": "received", "reason": "Nhập thêm"})
    await place(client, cart((p, 1, None)), payment_method="cod", phone="0900000102")
    assert len(await _activities("orders.restock_alert")) == 2


async def test_inventory_permissions_and_idempotent_listener(
    helper_client: httpx.AsyncClient, owner_client: httpx.AsyncClient, db
) -> None:
    from app.core import events

    p = await make_product(mode=SaleMode.IN_STOCK)
    r = await helper_client.post("/api/desk/orders/inventory", json={"product_id": str(p.id), "on_hand": 1})
    assert r.status_code == 403
    assert (await helper_client.get("/api/desk/orders/inventory")).status_code == 200
    missing = await owner_client.post(
        f"/api/desk/orders/inventory/{uuid.uuid4()}/adjust", json={"quantity": 1, "reason": "abc"}
    )
    assert missing.status_code == 404
    payload = {"request_id": str(uuid.uuid4()), "product_id": str(p.id), "set_on_hand": 5, "kind": "opening"}
    await events.emit("inventory.adjust_requested", payload, db=db)
    await events.emit("inventory.adjust_requested", payload, db=db)
    await db.commit()
    async with SessionLocal() as s:
        assert (await s.execute(select(InventoryItem.on_hand))).scalar_one() == 5
        assert await s.scalar(select(func.count()).select_from(InventoryMovement)) == 1


# ---- g9: đẩy trạng thái lên sàn ---------------------------------------------------------------------------------------


async def test_marketplace_order_pushes_status_once(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    p = await make_product(mode=SaleMode.IN_STOCK, price=200_000)
    await make_inventory(p, 6)
    await owner_client.post("/api/desk/orders/marketplaces/tiktok_shop/sync-products")
    r = await owner_client.post(
        "/api/desk/orders/marketplaces/tiktok_shop/simulate", json={"product_id": str(p.id), "quantity": 1}
    )
    assert r.json()["created_orders"] == 1
    row = (await owner_client.get("/api/desk/orders", params={"channel": "tiktok_shop"})).json()["items"][0]
    res = (await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [row["id"]]})).json()["results"][0]
    mk = get_driver("marketplaces", "mock")
    order = await _order(row["id"])
    assert mk.status_updates == [(Channel.TIKTOK_SHOP, order.external_id, "shipped", res["tracking_code"])]
    assert order.raw["marketplace_push"]["shipped"] == res["tracking_code"]
    mock = get_driver("shipping", "mock")
    for n in (1, 2, 1):
        mock.advance(n)
        await owner_client.post(f"/api/desk/orders/shipments/{res['shipment_id']}/sync")
    assert [u[2] for u in mk.status_updates] == ["shipped", "delivered"]
    async with SessionLocal() as s:
        assert await marketplace.push_pending(s) == 0  # gọi lặp không gửi lại
        evs = (await s.execute(select(OrderEvent.kind).where(OrderEvent.kind.like("marketplace_%")))).scalars().all()
        assert sorted(evs) == ["marketplace_delivered", "marketplace_shipped"]
    assert len(mk.status_updates) == 2


async def test_marketplace_push_error_retried_by_cron(
    client: httpx.AsyncClient, owner_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = await make_product(mode=SaleMode.IN_STOCK, price=200_000)
    await make_inventory(p, 6)
    await owner_client.post(
        "/api/desk/orders/marketplaces/shopee/simulate", json={"product_id": str(p.id), "quantity": 1}
    )
    row = (await owner_client.get("/api/desk/orders", params={"channel": "shopee"})).json()["items"][0]
    mk = get_driver("marketplaces", "mock")
    real = mk.update_order_status

    async def broken(*a, **kw):
        raise IntegrationError("Sàn đang bảo trì")

    monkeypatch.setattr(mk, "update_order_status", broken)
    res = (await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [row["id"]]})).json()["results"][0]
    assert res["status"] == "applied"  # lỗi sàn không chặn tạo vận đơn
    order = await _order(row["id"])
    assert (
        order.raw["marketplace_push"]["error"] == "Sàn đang bảo trì" and "shipped" not in order.raw["marketplace_push"]
    )
    monkeypatch.setattr(mk, "update_order_status", real)
    async with SessionLocal() as s:
        assert await marketplace.push_pending(s) == 1
        await s.commit()
    order = await _order(row["id"])
    assert (
        order.raw["marketplace_push"]["shipped"] == res["tracking_code"]
        and "error" not in order.raw["marketplace_push"]
    )


async def test_web_orders_do_not_push(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    p = await make_product(mode=SaleMode.IN_STOCK, price=150_000)
    await make_inventory(p, 10)
    o = await place(client, cart((p, 1, None)), payment_method="cod")
    oid = (await owner_client.get("/api/desk/orders", params={"q": o["code"]})).json()["items"][0]["id"]
    await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [oid]})
    assert get_driver("marketplaces", "mock").status_updates == []


def test_shopee_ship_order_body_follows_shipping_parameter() -> None:
    non = ship_order_body("SN1", {"info_needed": {"non_integrated": ["tracking_no"]}}, "GHN123")
    assert non == {"order_sn": "SN1", "non_integrated": {"tracking_number": "GHN123"}}
    param = {
        "info_needed": {"dropoff": [], "pickup": ["address_id", "pickup_time_id"]},
        "pickup": {
            "address_list": [
                {"address_id": 1, "address_flag": ["default_address"], "time_slot_list": []},
                {
                    "address_id": 2,
                    "address_flag": ["pickup_address"],
                    "time_slot_list": [{"pickup_time_id": "a"}, {"pickup_time_id": "b", "flags": ["recommended"]}],
                },
            ]
        },
    }
    assert ship_order_body("SN2", param, "X")["pickup"] == {"address_id": 2, "pickup_time_id": "b"}
    drop = ship_order_body("SN3", {"info_needed": {"dropoff": ["tracking_no"]}}, "T9")
    assert drop["dropoff"] == {"tracking_number": "T9"}
    with pytest.raises(IntegrationError):
        ship_order_body("SN4", {"info_needed": {}}, "T")


async def test_real_drivers_need_keys_and_skip_delivered(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.integrations.base import IntegrationNotConfigured
    from app.integrations.marketplaces import shopee, tiktok_shop

    with pytest.raises(IntegrationNotConfigured):
        await tiktok_shop.Driver().update_order_status(Channel.TIKTOK_SHOP, "1", "shipped", "T")
    await tiktok_shop.Driver().update_order_status(Channel.TIKTOK_SHOP, "1", "delivered", "T")  # sàn tự cập nhật
    await shopee.Driver().update_order_status(Channel.SHOPEE, "SN", "delivered", "T")
    calls: list[tuple[str, str, dict]] = []

    async def fake_call(self, method, path, *, params=None, body=None):
        calls.append((method, path, params or body or {}))
        return {"info_needed": {"non_integrated": []}} if "get_shipping_parameter" in path else {}

    monkeypatch.setattr(shopee.Driver, "_call", fake_call)
    await shopee.Driver().update_order_status(Channel.SHOPEE, "SN9", "shipped", "GHN1")
    assert [c[1] for c in calls] == ["/api/v2/logistics/get_shipping_parameter", "/api/v2/logistics/ship_order"]
    assert calls[1][2] == {"order_sn": "SN9", "non_integrated": {"tracking_number": "GHN1"}}
    monkeypatch.setenv("TIKTOK_SHOP_SHIPPING_PROVIDER_ID", "7117")
    monkeypatch.setattr(tiktok_shop.Driver, "_call", fake_call)
    await tiktok_shop.Driver().update_order_status(Channel.TIKTOK_SHOP, "5770", "shipped", "GHN2")
    assert calls[-1] == (
        "POST", "/fulfillment/202309/orders/5770/packages", {"tracking_number": "GHN2", "shipping_provider_id": "7117"}
    )  # fmt: skip


async def test_drop_order_paid_logged(client: httpx.AsyncClient) -> None:
    """Đơn trong đợt: khớp tiền + báo «đã nhận tiền» đều có dòng nhật ký."""
    p = await make_product()
    d = await make_drop([(p, 300_000, 5)])
    o = await place(client, cart((p, 1, d)))
    await send_transfer(client, o["payment"]["amount_due_vnd"], o["payment"]["transfer_content"])
    notes = await _activities("orders.notify_customer")
    assert [a.title.split(":")[1].split("·")[0].strip() for a in notes] == ["Đã nhận đơn", "Đã nhận tiền"]
