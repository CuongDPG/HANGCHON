"""g1 gom đơn mọi kênh (danh sách, lọc, tìm không dấu, đếm, tạo đơn tay), phân quyền, mẫu tin g5, chống báo trùng,
chuẩn hoá số điện thoại, số liệu «Hôm nay»."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.errors import BadRequest
from app.integrations import get_driver
from app.modules.catalog.models import SaleMode
from app.modules.orders import notify, service
from app.modules.orders.models import Notification, Order
from app.modules.orders.util import normalize_phone
from tests.orders.conftest import cart, make_drop, make_inventory, make_product, place


def test_normalize_phone() -> None:
    for raw in ("0900000101", "+84 900 000 101", "84900000101", "090.000.0101", "090-000-0101"):
        assert normalize_phone(raw) == "0900000101"
    for bad in ("12345", "0123", "+1 415 555 0100"):
        with pytest.raises(BadRequest):
            normalize_phone(bad)


async def _orders(client: httpx.AsyncClient) -> None:
    p = await make_product()
    d = await make_drop([(p, 100_000, None)])
    await place(client, cart((p, 1, d)), name="Nguyễn Thị Lân")
    await place(client, cart((p, 1, d)), name="Trần Văn Tùng", phone="0900000102", payment_method="cod")


async def test_list_filter_search_counts(
    client: httpx.AsyncClient, owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient
) -> None:
    await _orders(client)
    assert (await client.get("/api/desk/orders")).status_code == 401
    all_ = (await helper_client.get("/api/desk/orders")).json()
    assert all_["total"] == 2
    waiting = (await owner_client.get("/api/desk/orders", params={"nhom": "cho_thanh_toan"})).json()["items"]
    assert [o["recipient_name"] for o in waiting] == ["Nguyễn Thị Lân"] and waiting[0][
        "status_label"
    ] == "Chờ chuyển khoản"
    by_name = (await owner_client.get("/api/desk/orders", params={"q": "lan"})).json()["items"]
    assert [o["recipient_name"] for o in by_name] == ["Nguyễn Thị Lân"]  # tìm không dấu
    by_phone = (await owner_client.get("/api/desk/orders", params={"q": "0102"})).json()["items"]
    assert [o["recipient_name"] for o in by_phone] == ["Trần Văn Tùng"]
    code = all_["items"][0]["code"]
    assert (await owner_client.get("/api/desk/orders", params={"q": code})).json()["total"] == 1
    c = (await owner_client.get("/api/desk/orders/counts")).json()
    assert c["cho_thanh_toan"] == 1 and c["cho_hang"] == 1 and c["tat_ca"] == 2 and c["new_today"] == 2
    bad = await owner_client.get("/api/desk/orders", params={"nhom": "khong-co"})
    assert bad.status_code == 422


async def test_manual_order(owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient) -> None:
    p = await make_product(mode=SaleMode.IN_STOCK, price=150_000)
    await make_inventory(p, 3)
    body = {
        "items": [{"product_id": str(p.id), "quantity": 2, "unit_price_vnd": 140_000}], "name": "Khách gọi điện",
        "phone": "0900000150", "address_line": "4 Phố Thử", "province": "Hà Nội", "channel": "phone",
        "payment_method": "cash", "shipping_fee_vnd": 0, "already_paid": True, "internal_note": "Lấy tại nhà",
    }  # fmt: skip
    cat = (await helper_client.get("/api/desk/orders/catalog")).json()
    assert cat[0]["product_id"] == str(p.id) and cat[0]["stock_available"] == 3 and cat[0]["drops"] == []
    r = await helper_client.post("/api/desk/orders", json=body)
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["channel"] == "phone" and o["subtotal_vnd"] == 280_000 and o["payment_state"] == "paid"
    assert o["status"] == "ready_to_ship" and o["payments"][0]["provider"] == "manual"
    assert o["public_url"].startswith("http") and o["events"]
    patched = await helper_client.patch(
        f"/api/desk/orders/{o['id']}", json={"address_line": "5 Phố Thử", "recipient_phone": "+84900000151"}
    )
    assert patched.json()["address_line"] == "5 Phố Thử" and patched.json()["recipient_phone"] == "0900000151"


async def test_templates_edit_and_use(
    client: httpx.AsyncClient, owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient
) -> None:
    t = (await helper_client.get("/api/desk/orders/templates")).json()
    assert set(t["templates"]) == set(notify.DEFAULT_TEMPLATES) and "ma_don" in t["placeholders"]
    body = {"templates": {"order_received": "Chào {ten}, đơn {ma_don} đã vào sổ. {link}"}}
    assert (await helper_client.put("/api/desk/orders/templates", json=body)).status_code == 403
    r = await owner_client.put("/api/desk/orders/templates", json=body)
    assert r.status_code == 200 and r.json()["templates"]["order_received"].startswith("Chào {ten}")
    bad = await owner_client.put("/api/desk/orders/templates", json={"templates": {"order_received": "Sai {ngoac"}})
    assert bad.status_code == 400
    unknown = await owner_client.put("/api/desk/orders/templates", json={"templates": {"khong_co": "x"}})
    assert unknown.status_code == 400
    p = await make_product()
    d = await make_drop([(p, 100_000, None)])
    o = await place(client, cart((p, 1, d)))
    sent = get_driver("notify").outbox[-1]
    assert sent.text.startswith(f"Chào Nguyễn Thị Lan, đơn {o['code']} đã vào sổ.") and sent.to == "0900000101"


async def test_notify_dedupe_disabled_and_failure(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    p = await make_product()
    d = await make_drop([(p, 100_000, None)])
    await place(client, cart((p, 1, d)))
    async with SessionLocal() as s:
        order = (await s.execute(select(Order))).scalar_one()
        a = await notify.notify_order(s, order, "order_received")
        b = await notify.notify_order(s, order, "order_received")
        assert a is not None and b is not None and a.id == b.id
        await s.commit()
    await owner_client.patch("/api/desk/control/settings/orders.notify_enabled", json={"value": False})
    await place(client, cart((p, 1, d)), phone="0900000102")
    await owner_client.patch("/api/desk/control/settings/orders.notify_enabled", json={"value": True})
    async with SessionLocal() as s:
        statuses = (await s.execute(select(Notification.status).order_by(Notification.created_at))).scalars().all()
        assert statuses == ["sent", "skipped"]
        order = (await s.execute(select(Order).order_by(Order.created_at))).scalars().first()
        order.recipient_phone = "fail-0900"
        n = await notify.notify_order(s, order, "delivered")
        assert n.status == "failed" and n.error


async def test_cancel_unpaid_and_today_stats(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    p = await make_product()
    d = await make_drop([(p, 100_000, 1)])
    await place(client, cart((p, 1, d)))
    async with SessionLocal() as s:
        oid = (await s.execute(select(Order.id))).scalar_one()
    r = await owner_client.post(
        f"/api/desk/orders/{oid}/cancel", json={"reason": "Khách nhắn huỷ", "notify_customer": False}
    )
    assert r.status_code == 200 and r.json()["status"] == "cancelled" and not r.json()["returns"]
    again = await owner_client.post(f"/api/desk/orders/{oid}/cancel", json={"reason": "lần nữa"})
    assert again.status_code == 409
    await place(client, cart((p, 1, d)), phone="0900000103")  # suất đã được trả
    today = (await owner_client.get("/api/desk/control/today")).json()
    stats = {s["key"]: s for s in today["stats"]}
    assert stats["orders.new_today"]["value"] == 1 and stats["orders.waiting_payment"]["value"] == 1


async def test_detail_not_found_and_draft_guard(owner_client: httpx.AsyncClient) -> None:
    import uuid

    assert (await owner_client.get(f"/api/desk/orders/{uuid.uuid4()}")).status_code == 404
    async with SessionLocal() as s:
        draft = await service.new_draft(s, channel=service.Channel.ZALO, recipient_name=None, recipient_phone=None)
        await s.commit()
    r = await owner_client.post(f"/api/desk/orders/{draft.id}/confirm-draft", json={})
    assert r.status_code == 400 and r.json()["code"] == "missing_info"
