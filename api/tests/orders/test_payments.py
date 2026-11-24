"""g2: khớp thanh toán — webhook, khớp theo nội dung + số tiền, thiếu/thừa/sai nội dung → việc chờ chị,
đơn quá hạn: nhắc rồi tự huỷ, trả suất. Driver SePay (xác thực + VietQR)."""

from __future__ import annotations

import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.timeutil import now_utc
from app.integrations import get_driver
from app.integrations.base import IntegrationError
from app.modules.control.models import ApprovalItem
from app.modules.orders import payments
from app.modules.orders.models import Notification, Order, Payment
from app.modules.orders.util import find_codes_in_transfer
from tests.orders.conftest import cart, make_drop, make_product, names, place, send_transfer


async def _order(client: httpx.AsyncClient, slots: int | None = 5, qty: int = 1) -> dict:
    p = await make_product()
    d = await make_drop([(p, 300_000, slots)])
    return await place(client, cart((p, qty, d)))


def test_find_codes_in_transfer() -> None:
    assert find_codes_in_transfer("HC 48213") == ["HC-48213"]
    assert find_codes_in_transfer("MBVCB.3278907687.HC48213.CT tu 0123") == ["HC-48213"]
    assert find_codes_in_transfer("chuyen tien hc-48213 don hang") == ["HC-48213"]
    assert find_codes_in_transfer("NGUYEN VAN A CHUYEN TIENHC48213") == ["HC-48213"]
    assert find_codes_in_transfer("HC 482131 sai so") == []
    assert find_codes_in_transfer("tien an trua") == []


async def test_webhook_matches_and_confirms_once(client: httpx.AsyncClient, emitted: list) -> None:
    o = await _order(client)
    content = o["payment"]["transfer_content"].replace(" ", "")  # ngân hàng bỏ dấu cách
    r = await send_transfer(client, o["payment"]["amount_due_vnd"], f"NGUYEN THI LAN {content}", external_id="TX1")
    assert r.status_code == 200 and r.json() == {"success": True, "received": 1}
    again = await send_transfer(client, o["payment"]["amount_due_vnd"], content, external_id="TX1")
    assert again.json()["received"] == 0  # cùng mã giao dịch: không ghi lần hai
    view = (await client.get(f"/api/store/orders/{o['code']}", params={"t": o["token"]})).json()
    assert (
        view["status"] == "awaiting_stock"
        and view["payment_state"] == "paid"
        and view["payment"]["amount_due_vnd"] == 0
    )
    assert names(emitted).count("order.paid") == 1
    paid = next(p for n, p in emitted if n == "order.paid")
    async with SessionLocal() as s:
        pay = (await s.execute(select(Payment))).scalar_one()
        assert pay.status == "matched" and pay.match_method == "auto_code" and str(pay.id) == paid["payment_id"]
        events = (await s.execute(select(Notification.event))).scalars().all()
        assert sorted(events) == ["order_received", "payment_confirmed"]


async def test_bad_signature_rejected(client: httpx.AsyncClient) -> None:
    body = json.dumps({"transfers": []}).encode()
    r = await client.post("/api/hooks/payments/mock", content=body, headers={"X-Mock-Signature": "sha256=sai"})
    assert r.status_code == 502 and r.json()["code"] == "invalid_signature"
    assert (await client.post("/api/hooks/payments/sepay", content=b"{}")).status_code == 404  # chưa bật sepay


async def test_underpaid_then_topped_up(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    o = await _order(client)
    due = o["payment"]["amount_due_vnd"]
    await send_transfer(client, due - 50_000, o["payment"]["transfer_content"])
    view = (await client.get(f"/api/store/orders/{o['code']}", params={"t": o["token"]})).json()
    assert view["status"] == "pending_payment" and view["payment"]["amount_due_vnd"] == 50_000
    async with SessionLocal() as s:
        item = (await s.execute(select(ApprovalItem))).scalar_one()
        assert (
            item.action == "orders.review_payment" and item.payload["kind"] == "underpaid" and item.status == "pending"
        )
    await send_transfer(client, 50_000, o["payment"]["transfer_content"])
    view = (await client.get(f"/api/store/orders/{o['code']}", params={"t": o["token"]})).json()
    assert view["payment_state"] == "paid" and view["status"] == "awaiting_stock"
    rows = (await owner_client.get("/api/desk/orders/payments", params={"status": "needs_review"})).json()
    assert rows["total"] == 1 and rows["items"][0]["order_code"] == o["code"]


async def test_overpaid_creates_review(client: httpx.AsyncClient) -> None:
    o = await _order(client)
    await send_transfer(client, o["payment"]["amount_due_vnd"] + 20_000, o["payment"]["transfer_content"])
    async with SessionLocal() as s:
        item = (await s.execute(select(ApprovalItem))).scalar_one()
        assert item.payload["kind"] == "overpaid" and item.payload["decision"] == "keep"
        assert (await s.execute(select(Order))).scalar_one().payment_state == "paid"


async def test_wrong_content_suggests_order_and_owner_approves(
    client: httpx.AsyncClient, owner_client: httpx.AsyncClient
) -> None:
    o = await _order(client)
    await send_transfer(client, o["payment"]["amount_due_vnd"], "chuyen tien mua binh")
    async with SessionLocal() as s:
        item = (await s.execute(select(ApprovalItem))).scalar_one()
        assert item.payload == {**item.payload, "kind": "unmatched", "decision": "match", "order_code": o["code"]}
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    view = (await client.get(f"/api/store/orders/{o['code']}", params={"t": o["token"]})).json()
    assert view["payment_state"] == "paid"


async def test_manual_match_and_ignore_from_desk(
    client: httpx.AsyncClient, owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient
) -> None:
    o = await _order(client)
    await send_transfer(client, 123_000, "khong ro")
    await send_transfer(client, o["payment"]["amount_due_vnd"], "tien hang")
    rows = (await owner_client.get("/api/desk/orders/payments", params={"status": "needs_review"})).json()["items"]
    assert len(rows) == 2
    target = next(r for r in rows if r["amount_vnd"] == o["payment"]["amount_due_vnd"])
    other = next(r for r in rows if r["amount_vnd"] == 123_000)
    assert (
        await helper_client.post(f"/api/desk/orders/payments/{target['id']}/match", json={"order_code": o["code"]})
    ).status_code == 403
    r = await owner_client.post(f"/api/desk/orders/payments/{target['id']}/match", json={"order_code": o["code"][3:]})
    assert r.status_code == 200 and r.json()["status"] == "matched" and r.json()["order_code"] == o["code"]
    r = await owner_client.post(f"/api/desk/orders/payments/{other['id']}/ignore")
    assert r.json()["status"] == "ignored"
    async with SessionLocal() as s:
        assert set((await s.execute(select(ApprovalItem.status))).scalars()) == {"cancelled"}


async def test_expiry_reminds_then_cancels_and_frees_slot(client: httpx.AsyncClient) -> None:
    p = await make_product()
    d = await make_drop([(p, 300_000, 1)])
    o = await place(client, cart((p, 1, d)))
    async with SessionLocal() as s:
        order = (await s.execute(select(Order))).scalar_one()
        order.placed_at = now_utc() - timedelta(hours=7)
        await s.commit()
    async with SessionLocal() as s:
        assert (await payments.expire_unpaid(s))["reminded"] == 1
        assert (await payments.expire_unpaid(s))["reminded"] == 0  # không nhắc lần hai
        await s.commit()
    async with SessionLocal() as s:
        order = (await s.execute(select(Order))).scalar_one()
        order.payment_due_at = now_utc() - timedelta(minutes=1)
        await s.commit()
    async with SessionLocal() as s:
        assert (await payments.expire_unpaid(s))["cancelled"] == 1
        await s.commit()
    view = (await client.get(f"/api/store/orders/{o['code']}", params={"t": o["token"]})).json()
    assert view["status"] == "cancelled" and view["timeline"][-1]["key"] == "cancelled"
    q = await client.post("/api/store/orders/quote", json={"items": cart((p, 1, d))})
    assert q.json()["lines"][0]["available"] == 1  # suất đã được trả
    async with SessionLocal() as s:
        evs = set((await s.execute(select(Notification.event))).scalars())
        assert {"payment_reminder", "other"} <= evs


async def test_late_payment_on_cancelled_order_reopens(
    client: httpx.AsyncClient, owner_client: httpx.AsyncClient
) -> None:
    o = await _order(client)
    async with SessionLocal() as s:
        order = (await s.execute(select(Order))).scalar_one()
        order.payment_due_at = now_utc() - timedelta(minutes=1)
        await s.commit()
    async with SessionLocal() as s:
        await payments.expire_unpaid(s)
        await s.commit()
    await send_transfer(client, o["payment"]["amount_due_vnd"], o["payment"]["transfer_content"])
    async with SessionLocal() as s:
        item = (
            await s.execute(select(ApprovalItem).where(ApprovalItem.action == "orders.review_payment"))
        ).scalar_one()
        assert item.payload["kind"] == "cancelled_order" and item.payload["decision"] == "reopen"
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    assert r.json()["status"] == "approved", r.json()
    view = (await client.get(f"/api/store/orders/{o['code']}", params={"t": o["token"]})).json()
    assert view["status"] == "awaiting_stock" and view["payment_state"] == "paid"


async def test_manual_payment_owner_only(
    client: httpx.AsyncClient, owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient
) -> None:
    await _order(client)
    async with SessionLocal() as s:
        oid = (await s.execute(select(Order.id))).scalar_one()
    body = {"amount_vnd": 10_000_000, "method": "cash"}
    assert (await helper_client.post(f"/api/desk/orders/{oid}/payments", json=body)).status_code == 403
    r = await owner_client.post(f"/api/desk/orders/{oid}/payments", json=body)
    assert r.status_code == 201 and r.json()["payment_state"] == "paid"


# ---- driver SePay -------------------------------------------------------------------------------------------------


def test_vietqr_payload_and_crc() -> None:
    from app.integrations.payments.sepay import crc16_ccitt, vietqr_payload

    assert crc16_ccitt("123456789") == "29B1"  # vector chuẩn CRC-16/CCITT-FALSE
    s = vietqr_payload("970436", "0123456789", 407000, "HC 48213")
    assert s.startswith("000201010212") and "0010A000000727" in s and "5303704" in s and "5406407000" in s
    assert "0808HC 48213" in s and s[-8:-4] == "6304" and crc16_ccitt(s[:-4]) == s[-4:]


async def test_sepay_webhook(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "payments_driver", "sepay")
    monkeypatch.setattr(settings, "sepay_webhook_secret", "khoa-thu")
    monkeypatch.setattr(settings, "bank_code", "VCB")
    o = await _order(client)
    assert o["payment"]["bank_code"] == "970436" and o["payment"]["qr_payload"].startswith("0002")
    hook = {
        "id": 92704, "gateway": "Vietcombank", "transactionDate": "2026-11-25 14:02:37", "accountNumber": "0123499999",
        "code": None, "content": f"{o['payment']['transfer_content']} NGUYEN THI LAN", "transferType": "in",
        "transferAmount": o["payment"]["amount_due_vnd"], "accumulated": 1, "referenceCode": "MBVCB.1", "description": "",
    }  # fmt: skip
    body = json.dumps(hook).encode()
    bad = await client.post("/api/hooks/payments/sepay", content=body, headers={"Authorization": "Apikey sai"})
    assert bad.status_code == 502
    ok = await client.post("/api/hooks/payments/sepay", content=body, headers={"Authorization": "Apikey khoa-thu"})
    assert ok.status_code == 200 and ok.json()["success"] is True and ok.json()["received"] == 1
    out_hook = await client.post(
        "/api/hooks/payments/sepay", content=json.dumps({**hook, "id": 1, "transferType": "out"}).encode(),
        headers={"Authorization": "Apikey khoa-thu"},
    )  # fmt: skip
    assert out_hook.json()["received"] == 0
    async with SessionLocal() as s:
        assert (
            await s.scalar(
                select(func.count())
                .select_from(Payment)
                .where(Payment.provider == "sepay", Payment.external_id == "92704")
            )
            == 1
        )
        assert (await s.execute(select(Order))).scalar_one().payment_state == "paid"


async def test_sepay_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.integrations.base import IntegrationNotConfigured

    monkeypatch.setattr(settings, "sepay_webhook_secret", None)
    with pytest.raises(IntegrationNotConfigured):
        await get_driver("payments", "sepay").parse_webhook({}, b"{}")
    monkeypatch.setattr(settings, "sepay_webhook_secret", "x")
    with pytest.raises(IntegrationError):
        await get_driver("payments", "sepay").parse_webhook({"Authorization": "Bearer x"}, b"{}")
