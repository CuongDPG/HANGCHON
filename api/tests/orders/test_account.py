"""Đăng nhập của khách bằng mã một lần («Của tôi» → Đơn của tôi): gửi/nhập mã, giới hạn tần suất, không lộ ai đã mua,
hết hạn, phiên khách không dùng được cho bàn làm việc, danh sách chỉ có đơn của chính khách."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.enums import Channel
from app.integrations.notify import driver_for
from app.main import app as fastapi_app
from app.modules.catalog.models import SaleMode
from app.modules.orders.models import Customer, CustomerLoginCode
from tests.orders.conftest import cart, make_inventory, make_product, place

OTHER_PHONE = "0900000202"
UNKNOWN_PHONE = "0900000303"


@pytest.fixture
async def shopper() -> AsyncIterator[httpx.AsyncClient]:
    """Trình duyệt riêng của khách (giữ cookie phiên khách, tách khỏi client đặt hàng)."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test") as c:
        yield c


def outbox() -> list:
    return driver_for(Channel.ZALO_OA).outbox


async def sign_in(c: httpx.AsyncClient, contact: str) -> httpx.Response:
    r = await c.post("/api/store/account/code", json={"contact": contact})
    assert r.status_code == 200, r.text
    return await c.post("/api/store/account/verify", json={"contact": contact, "code": r.json()["dev_code"]})


async def two_orders(client: httpx.AsyncClient) -> tuple[dict, dict]:
    p = await make_product(mode=SaleMode.IN_STOCK)
    await make_inventory(p, 10)
    mine = await place(client, cart((p, 1, None)), phone="0900000101")
    other = await place(client, cart((p, 2, None)), phone=OTHER_PHONE, name="Người Khác")
    return mine, other


async def test_code_is_sent_to_known_phone_and_verify_sets_session(client, shopper) -> None:
    mine, _ = await two_orders(client)
    r = await shopper.post("/api/store/account/code", json={"contact": "090 000 0101"})
    assert r.status_code == 200, r.text
    code = r.json()["dev_code"]
    sent = [m for m in outbox() if m.kind == "login_code"]
    assert len(sent) == 1 and sent[0].to == "0900000101" and code in sent[0].text
    assert sent[0].data["ma_dang_nhap"] == code
    # chỉ lưu bản băm
    async with SessionLocal() as s:
        row = (await s.execute(select(CustomerLoginCode))).scalar_one()
        assert code not in row.code_hash

    v = await shopper.post("/api/store/account/verify", json={"contact": "0900000101", "code": code})
    assert v.status_code == 200, v.text
    assert v.json() == {"signed_in": True, "kind": "phone", "contact": "090•••0101"}
    assert settings.customer_cookie_name in v.cookies
    me = await shopper.get("/api/store/account/me")
    assert me.json()["signed_in"] is True

    orders = (await shopper.get("/api/store/account/orders")).json()
    assert [o["code"] for o in orders["items"]] == [mine["code"]]  # không có đơn của số khác
    assert orders["items"][0]["token"] == mine["token"]
    # mã đã dùng không dùng lại được
    again = await shopper.post("/api/store/account/verify", json={"contact": "0900000101", "code": code})
    assert again.status_code == 400


async def test_no_enumeration_unknown_contact_gets_same_answer_and_no_message(client) -> None:
    await two_orders(client)
    known = await client.post("/api/store/account/code", json={"contact": "0900000101"})
    unknown = await client.post("/api/store/account/code", json={"contact": UNKNOWN_PHONE})
    email = await client.post("/api/store/account/code", json={"contact": "ai.do@example.com"})
    for r in (known, unknown, email):
        assert r.status_code == 200
    strip = lambda r: {k: v for k, v in r.json().items() if k != "dev_code"}  # noqa: E731
    assert strip(known) == strip(unknown) == strip(email)
    assert [m.to for m in outbox() if m.kind == "login_code"] == ["0900000101"]


async def test_wrong_code_attempts_then_code_is_dropped(client, shopper) -> None:
    await two_orders(client)
    r = await shopper.post("/api/store/account/code", json={"contact": "0900000101"})
    good = r.json()["dev_code"]
    bad = "000000" if good != "000000" else "111111"
    for _ in range(5):
        v = await shopper.post("/api/store/account/verify", json={"contact": "0900000101", "code": bad})
        assert v.status_code == 400
        assert v.json()["code"] == "code_invalid"
    # sai 5 lần: mã bị bỏ, kể cả nhập đúng
    v = await shopper.post("/api/store/account/verify", json={"contact": "0900000101", "code": good})
    assert v.status_code == 400
    assert (await shopper.get("/api/store/account/me")).json() == {"signed_in": False, "kind": None, "contact": None}


async def test_new_code_replaces_old_one(client, shopper) -> None:
    await two_orders(client)
    first = (await shopper.post("/api/store/account/code", json={"contact": "0900000101"})).json()["dev_code"]
    second = (await shopper.post("/api/store/account/code", json={"contact": "0900000101"})).json()["dev_code"]
    if first != second:
        old = await shopper.post("/api/store/account/verify", json={"contact": "0900000101", "code": first})
        assert old.status_code == 400
    ok = await shopper.post("/api/store/account/verify", json={"contact": "0900000101", "code": second})
    assert ok.status_code == 200


async def test_expired_code_is_rejected(client, shopper) -> None:
    await two_orders(client)
    code = (await shopper.post("/api/store/account/code", json={"contact": "0900000101"})).json()["dev_code"]
    async with SessionLocal() as s:
        await s.execute(
            update(CustomerLoginCode).values(expires_at=CustomerLoginCode.created_at - timedelta(minutes=1))
        )
        await s.commit()
    v = await shopper.post("/api/store/account/verify", json={"contact": "0900000101", "code": code})
    assert v.status_code == 400


async def test_rate_limits_sending_and_verifying(client) -> None:
    for _ in range(3):
        assert (await client.post("/api/store/account/code", json={"contact": UNKNOWN_PHONE})).status_code == 200
    r = await client.post("/api/store/account/code", json={"contact": UNKNOWN_PHONE})
    assert r.status_code == 429
    # nhập sai liên tục theo một liên hệ: sau 10 lần sai bị chặn (kể cả khi đã có mã mới)
    for i in range(10):
        v = await client.post("/api/store/account/verify", json={"contact": "0900000404", "code": f"{i:06d}"})
        assert v.status_code == 400
    v = await client.post("/api/store/account/verify", json={"contact": "0900000404", "code": "123456"})
    assert v.status_code == 429


async def test_invalid_contact_is_rejected(client) -> None:
    assert (await client.post("/api/store/account/code", json={"contact": "abc@"})).status_code == 400
    assert (await client.post("/api/store/account/code", json={"contact": "12345"})).status_code == 400


async def test_customer_session_cannot_access_desk(client, shopper, owner) -> None:
    await two_orders(client)
    v = await sign_in(shopper, "0900000101")
    assert v.status_code == 200
    token = shopper.cookies[settings.customer_cookie_name]
    assert (await shopper.get("/api/desk/auth/me")).status_code == 401
    assert (await shopper.get("/api/desk/orders")).status_code == 401
    bearer = await client.get("/api/desk/orders", headers={"Authorization": f"Bearer {token}"})
    assert bearer.status_code == 401
    # cookie bàn làm việc đặt vào ô cookie khách cũng không thành phiên khách
    login = await client.post("/api/desk/auth/login", json={"email": "chi@test.local", "password": "matkhau-chi-123"})
    desk_token = login.cookies[settings.cookie_name]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fastapi_app),
        base_url="http://test",
        cookies={settings.customer_cookie_name: desk_token},
    ) as forged:
        assert (await forged.get("/api/store/account/me")).json()["signed_in"] is False
        assert (await forged.get("/api/store/account/orders")).status_code == 401


async def test_logout_and_signed_out_orders(shopper, client) -> None:
    await two_orders(client)
    assert (await shopper.get("/api/store/account/orders")).status_code == 401
    await sign_in(shopper, "0900000101")
    r = await shopper.post("/api/store/account/logout")
    assert r.status_code == 204
    assert (await shopper.get("/api/store/account/me")).json()["signed_in"] is False


async def test_email_sign_in_does_not_reach_phone_customers(client, shopper) -> None:
    """Email trong sổ khách do khách tự điền (chưa xác minh): gắn vào hồ sơ có SĐT thì không mở đơn của hồ sơ đó."""
    await two_orders(client)
    async with SessionLocal() as s:
        c = (await s.execute(select(Customer).where(Customer.phone == "0900000101"))).scalar_one()
        c.email = "nguoi.la@example.com"
        await s.commit()
    v = await sign_in(shopper, "Nguoi.La@example.com")
    assert v.status_code == 200
    assert v.json()["kind"] == "email"
    assert (await shopper.get("/api/store/account/orders")).json()["items"] == []
    assert [m for m in driver_for(Channel.EMAIL).outbox if m.kind == "login_code"] == []
