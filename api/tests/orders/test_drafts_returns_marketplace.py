"""g6 chốt đơn từ tin nhắn, g7 đổi trả / hoàn tiền (luôn hỏi chị), g9 bán trên sàn."""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx
from sqlalchemy import func, select

from app.core import events
from app.core.db import SessionLocal
from app.core.enums import Actor, Channel
from app.core.timeutil import now_utc
from app.modules.catalog.models import SaleMode
from app.modules.control.models import ApprovalItem
from app.modules.inbox.models import ChannelAccount, Direction, Message, Thread, ThreadKind
from app.modules.orders.models import CustomerIdentity, Order, Payment
from tests.orders.conftest import cart, make_drop, make_inventory, make_product, names, place

# ---- g6 ------------------------------------------------------------------------------------------------------------


async def _message(text: str, thread: Thread | None = None) -> tuple[Thread, Message]:
    async with SessionLocal() as s:
        if thread is None:
            acc = ChannelAccount(channel=Channel.FACEBOOK, name="Trang thử", external_id=f"page-{uuid.uuid4().hex[:6]}")
            s.add(acc)
            await s.flush()
            thread = Thread(
                channel_account_id=acc.id, channel=Channel.FACEBOOK, kind=ThreadKind.DIRECT_MESSAGE,
                external_thread_id=uuid.uuid4().hex, participant_name="Chị Hoa", participant_external_id="psid-123",
            )  # fmt: skip
            s.add(thread)
            await s.flush()
        m = Message(
            thread_id=thread.id, direction=Direction.INBOUND, sender=Actor.CUSTOMER, body=text, sent_at=now_utc()
        )
        s.add(m)
        await s.commit()
        return thread, m


async def _emit_message(thread: Thread, m: Message) -> None:
    async with SessionLocal() as s:
        await events.emit("message.received", {"thread_id": str(thread.id), "message_id": str(m.id)}, db=s)
        await s.commit()


async def test_purchase_message_creates_draft_with_missing_info(owner_client: httpx.AsyncClient) -> None:
    p = await make_product(name="Bình giữ nhiệt 480 ml")
    await make_drop([(p, 385_000, 10)])
    thread, m = await _message("Chị ơi em lấy 2 cái bình giữ nhiệt 480 ml nhé")
    await _emit_message(thread, m)
    await _emit_message(thread, m)  # sự kiện lặp: không tạo đơn thứ hai
    async with SessionLocal() as s:
        draft = (await s.execute(select(Order))).scalar_one()
        assert draft.status == "draft" and draft.ai_generated and draft.thread_id == thread.id
        assert draft.items[0].product_id == p.id and draft.items[0].quantity == 2 and draft.drop_id is not None
        item = (await s.execute(select(ApprovalItem))).scalar_one()
        assert item.action == "orders.confirm_draft" and item.status == "pending"
        assert "số điện thoại" in item.preview["missing"]
    lst = (await owner_client.get("/api/desk/orders", params={"nhom": "nhap"})).json()
    assert lst["total"] == 1 and "số điện thoại" in lst["items"][0]["missing_info"]

    # khách nhắn tiếp số điện thoại + địa chỉ → cập nhật cùng đơn nháp
    _, m2 = await _message("sđt 0900000111, địa chỉ: 5 Ngõ Mẫu, Hà Nội. Tên: Hoa", thread)
    await _emit_message(thread, m2)
    async with SessionLocal() as s:
        draft = (await s.execute(select(Order))).scalar_one()
        assert draft.recipient_phone == "0900000111" and draft.province == "Hà Nội"
        assert await s.scalar(select(func.count()).select_from(CustomerIdentity)) == 1
        item = (await s.execute(select(ApprovalItem))).scalar_one()
        assert item.preview["missing"] == []
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    assert r.json()["status"] == "approved", r.json()
    async with SessionLocal() as s:
        o = (await s.execute(select(Order))).scalar_one()
        assert o.status == "pending_payment" and o.total_vnd > 770_000 and o.channel == "facebook"


async def test_non_purchase_message_ignored() -> None:
    await make_product(name="Bình giữ nhiệt")
    thread, m = await _message("Bình này giữ nóng bao lâu vậy chị?")
    await _emit_message(thread, m)
    async with SessionLocal() as s:
        assert await s.scalar(select(func.count()).select_from(Order)) == 0


async def test_confirm_draft_from_desk_with_edits(owner_client: httpx.AsyncClient) -> None:
    p = await make_product(name="Kệ úp bát inox", mode=SaleMode.IN_STOCK, price=320_000)
    await make_inventory(p, 5)
    thread, m = await _message("chốt cho mình 1 kệ úp bát inox")
    await _emit_message(thread, m)
    async with SessionLocal() as s:
        oid = (await s.execute(select(Order.id))).scalar_one()
    bad = await owner_client.post(f"/api/desk/orders/{oid}/confirm-draft", json={})
    assert bad.status_code == 400 and bad.json()["code"] == "missing_info"
    r = await owner_client.post(
        f"/api/desk/orders/{oid}/confirm-draft",
        json={
            "recipient_name": "Hoa",
            "recipient_phone": "0900000112",
            "address_line": "1 Phố Mẫu",
            "province": "Huế",
            "payment_method": "cod",
        },
    )
    assert r.status_code == 200 and r.json()["status"] == "ready_to_ship" and r.json()["payment_method"] == "cod"
    async with SessionLocal() as s:
        assert (await s.execute(select(ApprovalItem.status))).scalar_one() == "cancelled"


async def test_auto_level_with_missing_info_fails_safely(owner_client: httpx.AsyncClient) -> None:
    await owner_client.patch("/api/desk/control/autonomy/orders.confirm_draft", json={"level": "auto"})
    p = await make_product(name="Bình giữ nhiệt 480 ml")
    await make_drop([(p, 385_000, 10)])
    thread, m = await _message("em lấy 1 bình giữ nhiệt 480 ml")
    await _emit_message(thread, m)
    async with SessionLocal() as s:
        assert (await s.execute(select(Order.status))).scalar_one() == "draft"  # thiếu thông tin: không tự chốt


# ---- g7 ------------------------------------------------------------------------------------------------------------


async def _delivered(client: httpx.AsyncClient) -> dict:
    p = await make_product(mode=SaleMode.IN_STOCK, price=200_000)
    await make_inventory(p, 10)
    o = await place(client, cart((p, 1, None)))
    from tests.orders.conftest import send_transfer

    await send_transfer(client, o["payment"]["amount_due_vnd"], o["payment"]["transfer_content"])
    async with SessionLocal() as s:
        order = (await s.execute(select(Order).where(Order.code == o["code"]))).scalar_one()
        order.status = "delivered"
        order.delivered_at = now_utc() - timedelta(days=2)
        await s.commit()
    return o


async def test_customer_return_needs_owner_and_refunds(
    client: httpx.AsyncClient, owner_client: httpx.AsyncClient, emitted: list
) -> None:
    o = await _delivered(client)
    r = await client.post(
        f"/api/store/orders/{o['code']}/returns",
        json={"t": o["token"], "reason": "defect", "description": "Nắp bị nứt"},
    )
    assert (
        r.status_code == 201
        and r.json()["returns"][0]["status"] == "pending_decision"
        and not r.json()["can_request_return"]
    )
    again = await client.post(f"/api/store/orders/{o['code']}/returns", json={"t": o["token"], "reason": "defect"})
    assert again.status_code == 409
    async with SessionLocal() as s:
        item = (await s.execute(select(ApprovalItem).where(ApprovalItem.action == "orders.decide_return"))).scalar_one()
        assert item.status == "pending" and len(item.preview["options"]) == 2 and item.preview["checks"][0]["ok"]
    locked = await owner_client.patch("/api/desk/control/autonomy/orders.decide_return", json={"level": "auto"})
    assert locked.status_code == 403
    a = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    assert a.json()["status"] == "approved", a.json()
    rets = (await owner_client.get("/api/desk/orders/returns")).json()["items"]
    assert rets[0]["status"] == "awaiting_item" and rets[0]["refund_amount_vnd"] > 0
    assert (await client.post(f"/api/desk/orders/returns/{rets[0]['id']}/received")).status_code == 401
    done = await owner_client.post(f"/api/desk/orders/returns/{rets[0]['id']}/received")
    assert done.status_code == 200 and done.json()["status"] == "refunded"
    assert "order.refunded" in names(emitted)
    refunded = next(p for n, p in emitted if n == "order.refunded")
    assert refunded["amount_vnd"] == rets[0]["refund_amount_vnd"]
    async with SessionLocal() as s:
        out = (await s.execute(select(Payment).where(Payment.direction == "out"))).scalar_one()
        assert out.amount_vnd == rets[0]["refund_amount_vnd"]


async def test_return_out_of_window_suggests_reject(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    o = await _delivered(client)
    async with SessionLocal() as s:
        order = (await s.execute(select(Order))).scalar_one()
        order.delivered_at = now_utc() - timedelta(days=30)
        await s.commit()
    await client.post(f"/api/store/orders/{o['code']}/returns", json={"t": o["token"], "reason": "changed_mind"})
    async with SessionLocal() as s:
        item = (await s.execute(select(ApprovalItem))).scalar_one()
        assert item.payload["decision"] == "reject"
    # chị trả lại kèm lời nhắn → AI soạn lại (việc mới đang chờ)
    await owner_client.post(f"/api/desk/control/approvals/{item.id}/return", json={"note": "Khách quen, cho đổi"})
    async with SessionLocal() as s:
        items = (await s.execute(select(ApprovalItem).order_by(ApprovalItem.created_at))).scalars().all()
        assert [i.status for i in items] == ["returned", "pending"]
    a = await owner_client.post(f"/api/desk/control/approvals/{items[1].id}/approve", json={})
    assert a.json()["status"] == "approved"
    view = (await client.get(f"/api/store/orders/{o['code']}", params={"t": o["token"]})).json()
    assert view["returns"][0]["status"] == "rejected"


async def test_cancel_paid_order_opens_refund(
    client: httpx.AsyncClient, owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient, emitted: list
) -> None:
    p = await make_product()
    d = await make_drop([(p, 100_000, 5)])
    o = await place(client, cart((p, 1, d)))
    from tests.orders.conftest import send_transfer

    await send_transfer(client, o["payment"]["amount_due_vnd"], o["payment"]["transfer_content"])
    async with SessionLocal() as s:
        oid = (await s.execute(select(Order.id))).scalar_one()
    assert (
        await helper_client.post(f"/api/desk/orders/{oid}/cancel", json={"reason": "Khách đổi ý"})
    ).status_code == 403
    r = await owner_client.post(f"/api/desk/orders/{oid}/cancel", json={"reason": "Khách đổi ý"})
    assert (
        r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["returns"][0]["kind"] == "refund_only"
    )
    assert "order.cancelled" in names(emitted)
    async with SessionLocal() as s:
        item = (await s.execute(select(ApprovalItem).where(ApprovalItem.action == "orders.decide_return"))).scalar_one()
    await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    detail = (await owner_client.get(f"/api/desk/orders/{oid}")).json()
    assert detail["payment_state"] == "refunded" and detail["refunded_vnd"] == o["total_vnd"]


# ---- g9 ------------------------------------------------------------------------------------------------------------


async def test_marketplace_sync_and_pull_without_duplicates(owner_client: httpx.AsyncClient, emitted: list) -> None:
    p = await make_product(name="Khăn lau sợi tre", mode=SaleMode.IN_STOCK, price=89_000)
    await make_inventory(p, 6)
    r = await owner_client.post("/api/desk/orders/marketplaces/shopee/sync-products")
    assert r.json()["synced"] == 1
    lst = (await owner_client.get("/api/desk/orders/marketplaces/listings")).json()
    assert lst[0]["marketplace"] == "shopee" and lst[0]["synced_stock"] == 6 and lst[0]["status"] == "active"
    sim = await owner_client.post(
        "/api/desk/orders/marketplaces/shopee/simulate", json={"product_id": str(p.id), "quantity": 2}
    )
    assert sim.json()["created_orders"] == 1
    again = await owner_client.post("/api/desk/orders/marketplaces/shopee/pull-orders")
    assert again.json() == {**again.json(), "created_orders": 0, "skipped": 1}
    rows = (await owner_client.get("/api/desk/orders", params={"channel": "shopee"})).json()["items"]
    assert len(rows) == 1 and rows[0]["status"] == "ready_to_ship" and rows[0]["payment_method"] == "marketplace"
    assert names(emitted).count("order.paid") == 1
    bad = await owner_client.post("/api/desk/orders/marketplaces/facebook/pull-orders")
    assert bad.status_code == 400
