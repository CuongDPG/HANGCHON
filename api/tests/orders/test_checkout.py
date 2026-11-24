"""e4: đặt hàng một trang — giá thật, phí giao, chống đặt vượt trong giao dịch, COD, cọc, chống bấm hai lần."""

from __future__ import annotations

import asyncio

import httpx
from sqlalchemy import func, select

from app.core import events
from app.core.db import SessionLocal
from app.integrations import get_driver
from app.modules.catalog.models import DropItem, DropStatus, SaleMode
from app.modules.orders import service
from app.modules.orders.models import Customer, Notification, Order, OrderEvent, OrderStatus
from app.modules.orders.schemas import CartLineIn
from tests.orders.conftest import (
    ADDRESS,
    cart,
    checkout_body,
    make_drop,
    make_inventory,
    make_product,
    names,
    place,
)


async def test_quote_uses_server_price_and_shipping(client: httpx.AsyncClient) -> None:
    p = await make_product(price=400_000)
    d = await make_drop([(p, 385_000, 10)])
    r = await client.post("/api/store/orders/quote", json={"items": cart((p, 2, d)), **ADDRESS})
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["ok"] and q["subtotal_vnd"] == 770_000
    assert q["lines"][0]["unit_price_vnd"] == 385_000 and q["lines"][0]["available"] == 10
    assert q["shipping_fee_vnd"] > 0 and q["total_vnd"] == 770_000 + q["shipping_fee_vnd"]
    assert q["drops"][0]["code"] == d.code and "hàng về dự kiến" in q["delivery_hint"]


async def test_quote_reports_closed_drop_and_drop_only(client: httpx.AsyncClient) -> None:
    p = await make_product()
    closed = await make_drop([(p, 300_000, 5)], status=DropStatus.CLOSED)
    r = await client.post("/api/store/orders/quote", json={"items": cart((p, 1, closed)) + cart((p, 1, None))})
    q = r.json()
    assert not q["ok"]
    assert q["lines"][0]["problem"] == "Đợt này đã đóng, không nhận thêm đơn."
    assert q["lines"][1]["problem"] == "Món này chỉ bán theo đợt."


async def test_checkout_bank_transfer(client: httpx.AsyncClient, emitted: list) -> None:
    p = await make_product()
    d = await make_drop([(p, 385_000, 10)])
    o = await place(client, cart((p, 1, d)), phone="+84 90 000 0101", note="Giao giờ hành chính")
    assert o["code"].startswith("HC-") and len(o["code"]) == 8
    assert o["status"] == "pending_payment" and o["recipient_phone"] == "0900000101"
    pay = o["payment"]
    assert pay["amount_due_vnd"] == o["total_vnd"] and pay["transfer_content"] == f"HC {o['code'][3:]}"
    assert pay["qr_url"].startswith(f"/api/store/orders/{o['code']}/qr.svg?t=")
    assert [s["key"] for s in o["timeline"]][:3] == ["placed", "payment", "drop"]
    assert "order.created" in names(emitted)
    async with SessionLocal() as s:
        c = (await s.execute(select(Customer))).scalar_one()
        assert c.phone == "0900000101" and c.order_count == 1
        n = (await s.execute(select(Notification))).scalar_one()
        assert n.event == "order_received" and n.status == "sent" and o["code"] in n.body
    assert len(get_driver("notify").outbox) == 1
    qr = await client.get(pay["qr_url"])
    assert qr.status_code == 200 and qr.headers["content-type"].startswith("image/svg+xml")


async def test_checkout_cod_goes_to_awaiting_stock(client: httpx.AsyncClient, emitted: list) -> None:
    p = await make_product()
    d = await make_drop([(p, 200_000, None)])
    o = await place(client, cart((p, 3, d)), payment_method="cod")
    assert o["status"] == "awaiting_stock" and o["cod_amount_vnd"] == o["total_vnd"]
    assert o["payment"]["method"] == "cod"
    assert "order.paid" not in names(emitted)  # COD: chỉ coi là đã trả khi hãng giao thu tiền


async def test_client_ref_prevents_double_submit(client: httpx.AsyncClient) -> None:
    p = await make_product()
    d = await make_drop([(p, 100_000, 5)])
    a = await place(client, cart((p, 1, d)), client_ref="ref-123")
    b = await client.post("/api/store/orders", json=checkout_body(cart((p, 1, d)), client_ref="ref-123"))
    assert b.status_code == 201 and b.json()["code"] == a["code"]
    async with SessionLocal() as s:
        assert await s.scalar(select(func.count()).select_from(Order)) == 1


async def test_validation_errors(client: httpx.AsyncClient) -> None:
    p = await make_product()
    d = await make_drop([(p, 100_000, 5)])
    bad = await client.post("/api/store/orders", json=checkout_body(cart((p, 1, d)), phone="12345678"))
    assert bad.status_code == 400 and bad.json()["code"] == "phone_invalid"
    no_addr = await client.post("/api/store/orders", json=checkout_body(cart((p, 1, d)), address_line=None))
    assert no_addr.status_code == 400 and no_addr.json()["code"] == "address_required"
    empty = await client.post("/api/store/orders", json=checkout_body([]))
    assert empty.status_code == 422


async def test_slots_are_held_and_oversell_rejected(client: httpx.AsyncClient) -> None:
    p = await make_product()
    d = await make_drop([(p, 100_000, 3)], max_per_order=2)
    too_many = await client.post("/api/store/orders", json=checkout_body(cart((p, 3, d))))
    assert too_many.status_code == 409 and "tối đa 2" in too_many.json()["detail"]
    await place(client, cart((p, 2, d)))
    r = await client.post("/api/store/orders", json=checkout_body(cart((p, 2, d))))
    assert r.status_code == 409 and r.json()["code"] == "unavailable" and "Chỉ còn 1 suất" in r.json()["detail"]
    q = await client.post("/api/store/orders/quote", json={"items": cart((p, 1, d))})
    assert q.json()["lines"][0]["available"] == 1


async def test_concurrent_orders_cannot_take_the_same_last_slot() -> None:
    p = await make_product()
    d = await make_drop([(p, 100_000, 1)])
    line = [CartLineIn(product_id=p.id, drop_id=d.id, quantity=1)]

    async def attempt(i: int) -> str:
        async with SessionLocal() as s:
            try:
                await service.create_order(
                    s, lines=line, name=f"Khách {i}", phone=f"090000020{i}", address=ADDRESS,
                    payment_method=service.PaymentMethod.BANK_TRANSFER,
                )  # fmt: skip
                await s.commit()
                return "ok"
            except service.Conflict:
                await s.rollback()
                return "full"

    results = await asyncio.gather(attempt(1), attempt(2))
    assert sorted(results) == ["full", "ok"]


async def test_paid_orders_are_not_double_counted_when_catalog_deducts(client: httpx.AsyncClient) -> None:
    """Catalog trừ suất khi nghe order.paid; orders không đếm đơn đã trả lần hai."""
    p = await make_product()
    d = await make_drop([(p, 100_000, 3)])

    @events.on("order.paid")
    async def fake_catalog(db, payload) -> None:  # giả lập catalog
        order = await db.get(Order, __import__("uuid").UUID(payload["order_id"]))
        for it in order.items:
            di = await db.get(DropItem, it.drop_item_id)
            di.slots_reserved += it.quantity

    try:
        o = await place(client, cart((p, 2, d)))
        from tests.orders.conftest import send_transfer

        await send_transfer(client, o["payment"]["amount_due_vnd"], o["payment"]["transfer_content"])
        q = await client.post("/api/store/orders/quote", json={"items": cart((p, 1, d))})
        assert q.json()["lines"][0]["available"] == 1
    finally:
        events._handlers["order.paid"].remove(fake_catalog)


async def test_mixed_drops_rejected_and_stock_checked(client: httpx.AsyncClient) -> None:
    a, b = await make_product(), await make_product(name="Hộp gia vị")
    d1, d2 = await make_drop([(a, 100_000, 5)]), await make_drop([(b, 100_000, 5)])
    r = await client.post("/api/store/orders", json=checkout_body(cart((a, 1, d1), (b, 1, d2))))
    assert r.status_code == 409 and r.json()["code"] == "mixed_drops"

    s = await make_product(name="Khăn lau", mode=SaleMode.IN_STOCK, price=89_000)
    await make_inventory(s, 1)
    o = await place(client, cart((s, 1, None)), payment_method="cod")
    assert o["status"] == "ready_to_ship"
    r2 = await client.post("/api/store/orders", json=checkout_body(cart((s, 1, None))))
    assert r2.status_code == 409 and "Hết hàng" in r2.json()["detail"]


async def test_deposit_drop(client: httpx.AsyncClient) -> None:
    p = await make_product()
    d = await make_drop([(p, 1_000_000, 5)], deposit_pct=30)
    o = await place(client, cart((p, 1, d)))
    assert o["deposit_required_vnd"] > 0 and o["payment"]["amount_due_vnd"] == o["deposit_required_vnd"]
    async with SessionLocal() as s:
        ev = (
            (
                await s.execute(
                    select(OrderEvent.kind).where(
                        OrderEvent.order_id == (await s.execute(select(Order.id))).scalar_one()
                    )
                )
            )
            .scalars()
            .all()
        )
        assert "placed" in ev
    assert OrderStatus.PENDING_PAYMENT.value == o["status"]
