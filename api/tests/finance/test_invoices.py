"""k5 — hoá đơn điện tử: soạn cho đơn đã thanh toán → control.propose (ask/auto) → phát hành qua driver mock."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from app import control
from app.core.db import SessionLocal
from app.integrations import IntegrationError, get_driver
from app.modules.control.models import ApprovalItem
from app.modules.finance.models import Invoice, InvoiceStatus, LedgerEntry
from tests.finance.factory import make_order, pay

ITEMS = (("Bình giữ nhiệt 480 ml", 2, 245_000, 160_000), ("Khăn lau bếp", 1, 39_000, None))


async def _paid_order(**kw):
    async with SessionLocal() as db:
        order = await make_order(db, items=kw.pop("items", ITEMS), **kw)
        if order.payment_state == "paid":
            await pay(db, order)
        await db.commit()
        return order


async def test_invoice_goes_through_approval_then_issues(owner_client: httpx.AsyncClient) -> None:
    order = await _paid_order(discount=9_000)
    cands = (await owner_client.get("/api/desk/finance/invoices/candidates")).json()
    assert [c["code"] for c in cands] == [order.code]

    r = await owner_client.post("/api/desk/finance/invoices", json={"order_id": str(order.id)})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["outcome"] == "pending" and body["invoice"]["status"] == "draft"
    assert body["invoice"]["approval_status"] == "pending"
    lines = body["invoice"]["lines"]
    assert sum(ln["quantity"] * ln["unit_price_vnd"] for ln in lines) == order.total_vnd == 550_000
    assert lines[-1]["name"] == "Chiết khấu" and lines[-1]["unit_price_vnd"] == -9_000

    item = (await owner_client.get(f"/api/desk/control/approvals/{body['approval_item_id']}")).json()
    assert item["action_label"] == "Phát hành hoá đơn điện tử" and item["preview"]["total_vnd"] == 550_000
    assert item["locked"] is False and item["action_group"] == "Sổ sách"

    r = await owner_client.post(
        f"/api/desk/control/approvals/{item['id']}/approve", json={"payload": {"buyer_tax_code": "0101234567"}}
    )
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    inv = (await owner_client.get(f"/api/desk/finance/invoices/{body['invoice']['id']}")).json()
    assert inv["status"] == "issued" and inv["number"] == "00000001" and inv["buyer_tax_code"] == "0101234567"
    assert inv["raw"]["pdf_url"].endswith(".pdf")
    async with SessionLocal() as s:
        entry = (await s.execute(select(LedgerEntry).where(LedgerEntry.order_id == order.id))).scalar_one()
        assert str(entry.invoice_id) == inv["id"]
    assert (await owner_client.get("/api/desk/finance/invoices/candidates")).json() == []
    again = await owner_client.post("/api/desk/finance/invoices", json={"order_id": str(order.id)})
    assert again.status_code == 409 and again.json()["code"] == "invoice_exists"
    listed = (await owner_client.get("/api/desk/finance/invoices?status=issued")).json()
    assert listed["total"] == 1 and listed["items"][0]["approval_status"] == "approved"

    # hoàn tác từ nhật ký → huỷ hoá đơn
    act = (await owner_client.get("/api/desk/control/activity?action=finance.issue_invoice")).json()["items"][0]
    assert act["undoable"]
    assert (await owner_client.post(f"/api/desk/control/activity/{act['id']}/undo")).status_code == 200
    inv = (await owner_client.get(f"/api/desk/finance/invoices/{inv['id']}")).json()
    assert inv["status"] == "cancelled"
    assert get_driver("einvoice").cancelled


async def test_auto_level_issues_immediately(owner_client: httpx.AsyncClient) -> None:
    order = await _paid_order()
    await owner_client.patch("/api/desk/control/autonomy/finance.issue_invoice", json={"level": "auto"})
    body = (await owner_client.post("/api/desk/finance/invoices", json={"order_id": str(order.id)})).json()
    assert body["outcome"] == "applied" and body["invoice"]["status"] == "issued"


async def test_off_level_blocks(owner_client: httpx.AsyncClient) -> None:
    order = await _paid_order()
    await owner_client.patch("/api/desk/control/autonomy/finance.issue_invoice", json={"level": "off"})
    body = (await owner_client.post("/api/desk/finance/invoices", json={"order_id": str(order.id)})).json()
    assert body["outcome"] == "blocked" and body["invoice"]["status"] == "draft"


async def test_unpaid_order_and_permissions(owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient) -> None:
    order = await _paid_order(paid=False)
    r = await owner_client.post("/api/desk/finance/invoices", json={"order_id": str(order.id)})
    assert r.status_code == 400 and r.json()["code"] == "order_not_paid"
    missing = await owner_client.post(
        "/api/desk/finance/invoices", json={"order_id": "7f1c4c39-1e8a-4d9b-9a49-8d3c1b2a0f11"}
    )
    assert missing.status_code == 404
    paid = await _paid_order()
    assert (await helper_client.post("/api/desk/finance/invoices", json={"order_id": str(paid.id)})).status_code == 403
    assert (await helper_client.get("/api/desk/finance/invoices")).status_code == 200


async def test_return_then_redo_and_provider_error(
    owner_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    order = await _paid_order()
    body = (await owner_client.post("/api/desk/finance/invoices", json={"order_id": str(order.id)})).json()
    r = await owner_client.post(
        f"/api/desk/control/approvals/{body['approval_item_id']}/return", json={"note": "Sai tên"}
    )
    assert r.status_code == 200
    async with SessionLocal() as s:
        inv = await s.get(Invoice, body["invoice"]["id"])
        assert inv.status == InvoiceStatus.DRAFT and inv.raw["returned_note"] == "Sai tên"

    # soạn lại với tên mới → việc chờ mới; nhà cung cấp lỗi → việc chờ «failed», hoá đơn vẫn nháp
    body = (
        await owner_client.post("/api/desk/finance/invoices", json={"order_id": str(order.id), "buyer_name": "Cty Thử"})
    ).json()
    assert body["invoice"]["buyer_name"] == "Cty Thử"

    async def boom(_req):
        raise IntegrationError("Nhà cung cấp hoá đơn đang bảo trì.")

    monkeypatch.setattr(get_driver("einvoice"), "issue", boom)
    r = await owner_client.post(f"/api/desk/control/approvals/{body['approval_item_id']}/approve", json={})
    assert r.json()["status"] == "failed" and "bảo trì" in r.json()["error"]
    inv = (await owner_client.get(f"/api/desk/finance/invoices/{body['invoice']['id']}")).json()
    assert inv["status"] == "draft" and inv["approval_status"] == "failed"


async def test_auto_invoice_setting_prepares_on_paid(owner_client: httpx.AsyncClient) -> None:
    r = await owner_client.patch("/api/desk/control/settings/finance.auto_invoice", json={"value": True})
    assert r.status_code == 200
    await _paid_order()
    async with SessionLocal() as s:
        items = list(
            (await s.execute(select(ApprovalItem).where(ApprovalItem.action == "finance.issue_invoice"))).scalars()
        )
    assert len(items) == 1 and items[0].status == control.ApprovalStatus.PENDING
