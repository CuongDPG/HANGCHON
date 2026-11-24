"""k1 — sổ doanh thu, chi phí: ghi tự động từ sự kiện (idempotent), chi phí nhập tay kèm chứng từ, tổng hợp, CSV."""

from __future__ import annotations

import csv
import io
from datetime import date

import httpx
from sqlalchemy import func, select

from app.core import events
from app.core.db import SessionLocal
from app.core.storage import get_storage
from app.core.timeutil import local_today
from app.modules.finance.models import Expense, ExpenseCategory, LedgerDirection, LedgerEntry, LedgerKind
from tests.finance.factory import make_order, pay

TODAY = local_today().strftime("%Y-%m")


async def _entries() -> list[LedgerEntry]:
    async with SessionLocal() as s:
        return list((await s.execute(select(LedgerEntry).order_by(LedgerEntry.created_at))).scalars())


async def test_order_paid_records_revenue_once() -> None:
    async with SessionLocal() as db:
        order = await make_order(db)
        await pay(db, order)
        await pay(db, order)  # sự kiện lặp lại → không ghi trùng
        await db.commit()
    rows = await _entries()
    assert len(rows) == 1
    e = rows[0]
    assert e.kind == LedgerKind.REVENUE and e.direction == LedgerDirection.IN
    assert e.amount_vnd == 275_000 and e.document_no == order.code and e.order_id == order.id
    assert e.source_key == f"order:{order.id}:revenue" and len(e.period) == 7


async def test_order_paid_for_missing_order_is_ignored() -> None:
    async with SessionLocal() as db:
        n = await events.emit("order.paid", {"order_id": "7f1c4c39-1e8a-4d9b-9a49-8d3c1b2a0f11"}, db=db)
        await db.commit()
    # các module khác cũng nghe order.paid, nên chỉ cần không ai lỗi và sổ không bị ghi
    assert n >= 1 and await _entries() == []


async def test_refund_reduces_revenue_and_is_idempotent(owner_client: httpx.AsyncClient) -> None:
    async with SessionLocal() as db:
        order = await make_order(db)
        await pay(db, order)
        for _ in range(2):
            await events.emit("order.refunded", {"order_id": str(order.id), "amount_vnd": 50_000}, db=db)
        await db.commit()
    rows = await _entries()
    assert [r.kind for r in rows] == [LedgerKind.REVENUE, LedgerKind.REFUND]
    s = (await owner_client.get(f"/api/desk/finance/ledger/summary?period={TODAY}")).json()
    assert s["totals"] == {
        "revenue_vnd": 275_000,
        "refund_vnd": 50_000,
        "net_revenue_vnd": 225_000,
        "expense_vnd": 0,
        "entry_count": 2,
    }


async def test_expense_recorded_event_writes_ledger_once() -> None:
    async with SessionLocal() as db:
        exp = Expense(incurred_on=date(2026, 11, 3), category=ExpenseCategory.PACKAGING, amount_vnd=120_000,
                      description="Hộp giấy carton", vendor="Bao bì Thử")  # fmt: skip
        db.add(exp)
        await db.flush()
        for _ in range(2):
            await events.emit("expense.recorded", {"expense_id": str(exp.id)}, db=db)
        await events.emit("expense.recorded", {"expense_id": "7f1c4c39-1e8a-4d9b-9a49-8d3c1b2a0f11"}, db=db)
        await db.commit()
    rows = await _entries()
    assert len(rows) == 1 and rows[0].kind == LedgerKind.EXPENSE and rows[0].period == "2026-11"
    assert rows[0].description == "Hộp giấy carton — Bao bì Thử" and rows[0].category == "packaging"


async def test_manual_expense_with_receipt_flow(
    owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient
) -> None:
    form = {"incurred_on": "2026-11-20", "category": "shipping", "amount_vnd": "45000", "description": "Cước gửi mẫu"}
    r = await helper_client.post(
        "/api/desk/finance/expenses", data=form, files={"receipt": ("bien-lai.jpg", b"\xff\xd8anh", "image/jpeg")}
    )
    assert r.status_code == 201, r.text
    exp = r.json()
    assert exp["receipt_storage_key"].startswith("private/receipts/")
    assert await get_storage().get(exp["receipt_storage_key"]) == b"\xff\xd8anh"
    rows = await _entries()
    assert len(rows) == 1 and rows[0].kind == LedgerKind.SHIPPING and rows[0].source == "manual"

    bad = await owner_client.post(
        "/api/desk/finance/expenses", data=form, files={"receipt": ("x.exe", b"MZ", "application/octet-stream")}
    )
    assert bad.status_code == 400 and bad.json()["code"] == "receipt_type"
    assert (await owner_client.post("/api/desk/finance/expenses", data={**form, "amount_vnd": "0"})).status_code == 422

    r = await owner_client.patch(
        f"/api/desk/finance/expenses/{exp['id']}", json={"amount_vnd": 50_000, "category": "ads"}
    )
    assert r.status_code == 200 and r.json()["amount_vnd"] == 50_000
    rows = await _entries()
    assert rows[0].amount_vnd == 50_000 and rows[0].kind == LedgerKind.EXPENSE and rows[0].category == "ads"

    listed = (await owner_client.get("/api/desk/finance/expenses?period=2026-11")).json()
    assert listed["total"] == 1 and listed["pages"] == 1

    assert (await helper_client.delete(f"/api/desk/finance/expenses/{exp['id']}")).status_code == 403
    assert (await owner_client.delete(f"/api/desk/finance/expenses/{exp['id']}")).status_code == 204
    assert await _entries() == []
    assert not await get_storage().exists(exp["receipt_storage_key"])
    async with SessionLocal() as s:
        assert await s.scalar(select(func.count()).select_from(Expense)) == 0


async def test_ledger_list_summary_quarter_and_bad_period(owner_client: httpx.AsyncClient) -> None:
    async with SessionLocal() as db:
        for d, amt in ((date(2026, 10, 5), 100_000), (date(2026, 11, 5), 200_000), (date(2026, 12, 31), 300_000)):
            db.add(Expense(incurred_on=d, category=ExpenseCategory.GOODS, amount_vnd=amt, description="Nhập hàng"))
        await db.flush()
        for exp in (await db.execute(select(Expense))).scalars():
            await events.emit("expense.recorded", {"expense_id": str(exp.id)}, db=db)
        await db.commit()
    q = (await owner_client.get("/api/desk/finance/ledger/summary?period=2026-Q4")).json()
    assert q["label"] == "Quý 4/2026" and q["date_from"] == "2026-10-01" and q["date_to"] == "2026-12-31"
    assert q["totals"]["expense_vnd"] == 600_000 and [m["period"] for m in q["by_month"]] == [
        "2026-10",
        "2026-11",
        "2026-12",
    ]
    assert q["expenses_by_category"] == [{"category": "goods", "amount_vnd": 600_000, "count": 3}]
    page = (await owner_client.get("/api/desk/finance/ledger?period=2026-11")).json()
    assert page["total"] == 1 and page["items"][0]["amount_vnd"] == 200_000
    year = (await owner_client.get("/api/desk/finance/ledger?period=2026&size=2")).json()
    assert year["total"] == 3 and year["pages"] == 2 and year["items"][0]["entry_date"] == "2026-12-31"
    bad = await owner_client.get("/api/desk/finance/ledger?period=2026-Q7")
    assert bad.status_code == 400


async def test_export_csv_has_bom_rows_and_totals(
    owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient
) -> None:
    async with SessionLocal() as db:
        order = await make_order(db)
        await pay(db, order)
        db.add(
            Expense(incurred_on=local_today(), category=ExpenseCategory.ADS, amount_vnd=80_000, description="Quảng cáo")
        )
        await db.flush()
        exp = (await db.execute(select(Expense))).scalar_one()
        await events.emit("expense.recorded", {"expense_id": str(exp.id)}, db=db)
        await db.commit()
    r = await owner_client.get(f"/api/desk/finance/ledger/export.csv?period={TODAY}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert f"so-doanh-thu-chi-phi-{TODAY}.csv" in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][0].startswith("BẢNG KÊ DOANH THU, CHI PHÍ")
    header = rows[3]
    assert header[:4] == ["STT", "Ngày", "Số chứng từ", "Diễn giải"]
    body = [row for row in rows[4:] if row and row[0].isdigit()]
    assert len(body) == 2
    total = next(row for row in rows if len(row) > 3 and row[3] == "Tổng cộng")
    assert total[6] == "275000" and total[8] == "80000"
    assert (await helper_client.get("/api/desk/finance/ledger/export.csv")).status_code == 403


async def test_finance_requires_login(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/desk/finance/ledger")).status_code == 401


async def test_month_revenue_stat_on_today(owner_client: httpx.AsyncClient) -> None:
    async with SessionLocal() as db:
        await pay(db, await make_order(db))
        await db.commit()
    stats = {s["key"]: s for s in (await owner_client.get("/api/desk/control/today")).json()["stats"]}
    assert stats["finance.month_revenue"]["value"] == 275_000 and stats["finance.month_revenue"]["format"] == "vnd"
