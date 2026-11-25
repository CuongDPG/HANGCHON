"""Production còn driver `mock`: hoá đơn điện tử giả bị từ chối (báo lỗi dễ hiểu), không chặn khởi động."""

from __future__ import annotations

import httpx
import pytest

from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.control.models import ApprovalItem
from tests.finance.factory import make_order


@pytest.fixture
def prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "prod")


async def test_mock_einvoice_refused_in_prod(prod, db, owner_client: httpx.AsyncClient) -> None:
    order = await make_order(db)
    await db.commit()
    r = await owner_client.post("/api/desk/finance/invoices", json={"order_id": str(order.id)})
    assert r.status_code == 400 and r.json()["code"] == "einvoice_mock_in_prod"
    assert "giả lập" in r.json()["detail"] and "EINVOICE_DRIVER" in r.json()["detail"]


async def test_queued_mock_invoice_fails_on_approve_in_prod(
    db, owner_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hoá đơn soạn từ trước (khi còn ở dev) mà duyệt ở prod: thực thi lỗi, không phát số giả."""
    order = await make_order(db)
    await db.commit()
    created = (await owner_client.post("/api/desk/finance/invoices", json={"order_id": str(order.id)})).json()
    monkeypatch.setattr(settings, "app_env", "prod")
    r = await owner_client.post(f"/api/desk/control/approvals/{created['approval_item_id']}/approve", json={})
    assert r.json()["status"] == "failed" and "giả lập" in r.json()["error"]
    async with SessionLocal() as s:
        assert (await s.get(ApprovalItem, created["approval_item_id"])).error


async def test_mock_einvoice_still_works_in_dev(db, owner_client: httpx.AsyncClient) -> None:
    order = await make_order(db)
    await db.commit()
    r = await owner_client.post("/api/desk/finance/invoices", json={"order_id": str(order.id)})
    assert r.status_code == 201, r.text
