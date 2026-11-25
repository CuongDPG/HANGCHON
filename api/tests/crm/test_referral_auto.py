"""h7: quà giới thiệu bạn tự áp — bạn mới giảm ngay ở đơn đầu; người giới thiệu được tặng phần giảm cho đơn kế tiếp
khi đơn đầu của bạn đã trả tiền và đã giao (AI tự làm, ghi nhật ký, hoàn tác được). Chống lạm dụng."""

from __future__ import annotations

import httpx
from sqlalchemy import select

from app.core.db import SessionLocal
from app.integrations import get_driver
from app.modules.catalog.models import SaleMode
from app.modules.control.models import AIActivity, ApprovalItem
from app.modules.crm.models import ReferralUse
from app.modules.orders.models import Customer, Order
from tests.orders.conftest import cart, make_inventory, make_product, place

HA = "0900000201"
LAN = "0900000202"
MINH = "0900000203"


async def _setup(client: httpx.AsyncClient, owner_client: httpx.AsyncClient):
    p = await make_product(mode=SaleMode.IN_STOCK, price=200_000)
    await make_inventory(p, 50)
    await place(client, cart((p, 1, None)), payment_method="cod", phone=HA, name="Thu Hà")
    async with SessionLocal() as s:
        ha = (await s.execute(select(Customer).where(Customer.phone == HA))).scalar_one()
    code = (await owner_client.post(f"/api/desk/crm/customers/{ha.id}/referral")).json()["referral"]["code"]
    return p, ha, code


async def _order_id(code: str) -> str:
    async with SessionLocal() as s:
        return str((await s.execute(select(Order.id).where(Order.code == code))).scalar_one())


async def _deliver(owner_client: httpx.AsyncClient, order_code: str) -> None:
    oid = await _order_id(order_code)
    res = (await owner_client.post("/api/desk/orders/shipments", json={"order_ids": [oid]})).json()["results"][0]
    assert res["status"] == "applied", res
    mock = get_driver("shipping", "mock")
    for n in (1, 2, 1):
        mock.advance(n)
        await owner_client.post(f"/api/desk/orders/shipments/{res['shipment_id']}/sync")


async def _view(owner_client: httpx.AsyncClient) -> dict:
    rows = (await owner_client.get("/api/desk/crm/referrals/uses")).json()
    assert len(rows) == 1
    return rows[0]


async def _use() -> ReferralUse:
    async with SessionLocal() as s:
        return (await s.execute(select(ReferralUse))).scalar_one()


async def test_gifts_for_both_sides_automatically(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    p, ha, code = await _setup(client, owner_client)
    q = (
        await client.post("/api/store/orders/quote", json={"items": cart((p, 1, None)), "referral_code": code.lower()})
    ).json()
    assert q["referral_discount_vnd"] == 30_000 and "đơn đầu tiên của bạn" in q["referral_note"]
    assert "chị" not in q["referral_note"].lower()
    # bạn mới có mã: giảm ngay
    lan = await place(client, cart((p, 1, None)), payment_method="cod", phone=LAN, name="Lan", referral_code=code)
    assert lan["discount_vnd"] == 30_000
    v = await _view(owner_client)
    assert v["status"] == "pending" and v["referred_discount_vnd"] == 30_000 and v["referrer_credit_vnd"] == 0
    # tự giới thiệu mình, đơn thứ hai của bạn: không giảm
    own = await place(client, cart((p, 1, None)), payment_method="cod", phone=HA, referral_code=code)
    assert own["discount_vnd"] == 0
    lan2 = await place(client, cart((p, 1, None)), payment_method="cod", phone=LAN, referral_code=code)
    assert lan2["discount_vnd"] == 0
    # Hà chưa có quà (đơn của Lan chưa giao)
    pre = await place(client, cart((p, 1, None)), payment_method="cod", phone=HA)
    assert pre["discount_vnd"] == 0
    # đơn đầu của Lan giao xong + đã thu tiền (COD) → AI tự tặng quà cho Hà, ghi nhật ký
    await _deliver(owner_client, lan["code"])
    v = await _view(owner_client)
    assert v["status"] == "rewarded" and v["referrer_credit_vnd"] == 30_000 and v["credit_order_code"] is None
    async with SessionLocal() as s:
        act = (await s.execute(select(AIActivity).where(AIActivity.action == "crm.reward_referral"))).scalar_one()
        assert act.undoable and code in act.summary
    # đơn kế tiếp của Hà tự trừ quà; dùng một lần
    nxt = await place(client, cart((p, 1, None)), payment_method="cod", phone=HA)
    assert nxt["discount_vnd"] == 30_000
    assert (await _view(owner_client))["credit_order_code"] == nxt["code"]
    later = await place(client, cart((p, 1, None)), payment_method="cod", phone=HA)
    assert later["discount_vnd"] == 0
    # đã dùng → không hoàn tác được
    r = await owner_client.post(f"/api/desk/control/activity/{act.id}/undo")
    assert r.status_code == 409
    # đơn dùng quà bị huỷ → quà được dùng lại ở đơn sau
    oid = await _order_id(nxt["code"])
    r = await owner_client.post(f"/api/desk/orders/{oid}/cancel", json={"reason": "Khách đổi ý"})
    assert r.status_code == 200, r.text
    again = await place(client, cart((p, 1, None)), payment_method="cod", phone=HA)
    assert again["discount_vnd"] == 30_000
    assert (await _view(owner_client))["credit_order_code"] == again["code"]
    stats = (await owner_client.get("/api/desk/crm/referrals/stats")).json()
    assert stats["rewarded"] == 1 and stats["referred_customers"] == 1
    assert ha.id


async def test_unpaid_first_order_gets_no_reward_and_undo(
    client: httpx.AsyncClient, owner_client: httpx.AsyncClient
) -> None:
    p, _, code = await _setup(client, owner_client)
    # đơn chuyển khoản chưa trả, bị huỷ → bạn vẫn dùng được mã ở đơn mới (đơn mới thành đơn đầu)
    first = await place(client, cart((p, 1, None)), phone=MINH, name="Minh", referral_code=code)
    assert first["discount_vnd"] == 30_000
    await owner_client.post(f"/api/desk/orders/{await _order_id(first['code'])}/cancel", json={"reason": "Quá hạn"})
    second = await place(client, cart((p, 1, None)), payment_method="cod", phone=MINH, referral_code=code)
    assert second["discount_vnd"] == 30_000
    use = await _use()
    assert str(use.order_id) == await _order_id(second["code"])
    await _deliver(owner_client, second["code"])
    use = await _use()
    assert use.status == "rewarded"
    async with SessionLocal() as s:
        act = (await s.execute(select(AIActivity).where(AIActivity.action == "crm.reward_referral"))).scalar_one()
    r = await owner_client.post(f"/api/desk/control/activity/{act.id}/undo")
    assert r.status_code == 200, r.text
    v = await _view(owner_client)
    assert v["status"] == "qualified" and v["referrer_credit_vnd"] == 0
    plain = await place(client, cart((p, 1, None)), payment_method="cod", phone=HA)
    assert plain["discount_vnd"] == 0


async def test_reward_ask_level_waits_for_owner(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    await owner_client.patch("/api/desk/control/autonomy/crm.reward_referral", json={"level": "ask"})
    p, _, code = await _setup(client, owner_client)
    lan = await place(client, cart((p, 1, None)), payment_method="cod", phone=LAN, referral_code=code)
    await _deliver(owner_client, lan["code"])
    assert (await _use()).status == "qualified"
    async with SessionLocal() as s:
        item = (await s.execute(select(ApprovalItem).where(ApprovalItem.action == "crm.reward_referral"))).scalar_one()
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    assert r.json()["status"] == "approved"
    assert (await _view(owner_client))["referrer_credit_vnd"] == 30_000


async def test_bad_code_quote_note(client: httpx.AsyncClient) -> None:
    p = await make_product(mode=SaleMode.IN_STOCK, price=200_000)
    await make_inventory(p, 5)
    q = (await client.post("/api/store/orders/quote", json={"items": cart((p, 1, None)), "referral_code": "XX"})).json()
    assert q["referral_discount_vnd"] == 0 and "không còn dùng được" in q["referral_note"]
    o = await place(client, cart((p, 1, None)), payment_method="cod", referral_code="XX")
    assert o["discount_vnd"] == 0
