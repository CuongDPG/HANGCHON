"""Nghiệp vụ finance: sổ doanh thu/chi phí (k1), chi phí nhập tay, bảng kê CSV, hoá đơn điện tử (k5),
báo cáo tuần (i5), sao lưu CSDL (k4).

Quy tắc ghi sổ (k1) — chốt ngày 25/11/2026:
- Doanh thu ghi **một lần mỗi đơn** khi nhận sự kiện `order.paid` (đơn chuyển khoản lúc khớp tiền, đơn COD lúc
  đối soát tiền thu hộ — bên orders quyết thời điểm phát). Số tiền = `orders.total_vnd` (gồm phí giao thu của khách),
  ngày = `orders.paid_at` theo giờ VN. Khoá chống trùng `order:<id>:revenue`.
- Hoàn tiền (`order.refunded`) ghi dòng giảm trừ doanh thu; khoá `order:<id>:refund:<payment_id|return_id|số tiền>`.
- Chi phí (`expense.recorded` hoặc chị nhập tay) ghi một dòng chi; khoá `expense:<id>`.
- Giá vốn KHÔNG ghi vào sổ (tiền mua hàng đã là chi phí «goods»); báo cáo tuần tự tính giá vốn từ `order_items`.
"""

from __future__ import annotations

import asyncio
import csv
import gzip
import hashlib
import io
import logging
import os
import shutil
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.storage import get_storage
from app.core.timeutil import VN_TZ, local_today, now_utc, to_local, week_start
from app.modules.control import service as control
from app.modules.control.models import AIRun, ApprovalItem, ApprovalStatus, User
from app.modules.finance.models import (
    Backup,
    BackupKind,
    BackupStatus,
    BackupTrigger,
    Expense,
    ExpenseCategory,
    Invoice,
    InvoiceStatus,
    LedgerDirection,
    LedgerEntry,
    LedgerKind,
    LedgerSource,
    ReportStatus,
    WeeklyReport,
)

log = logging.getLogger("app.finance")

KIND_LABELS = {
    LedgerKind.REVENUE: "Doanh thu bán hàng",
    LedgerKind.REFUND: "Giảm trừ (hoàn tiền)",
    LedgerKind.COST_OF_GOODS: "Giá vốn",
    LedgerKind.SHIPPING: "Phí vận chuyển",
    LedgerKind.PAYMENT_FEE: "Phí thanh toán",
    LedgerKind.MARKETPLACE_FEE: "Phí sàn",
    LedgerKind.EXPENSE: "Chi phí",
    LedgerKind.ADJUSTMENT: "Điều chỉnh",
}

CATEGORY_LABELS = {
    ExpenseCategory.GOODS: "Mua hàng",
    ExpenseCategory.SAMPLES: "Mua mẫu",
    ExpenseCategory.SHIPPING: "Vận chuyển",
    ExpenseCategory.PACKAGING: "Đóng gói",
    ExpenseCategory.ADS: "Quảng cáo",
    ExpenseCategory.AI: "Chi phí AI",
    ExpenseCategory.SOFTWARE: "Phần mềm",
    ExpenseCategory.FEES: "Phí, lệ phí",
    ExpenseCategory.TAX: "Thuế",
    ExpenseCategory.OTHER: "Khác",
}


def _period(d: date) -> str:
    return d.strftime("%Y-%m")


def _local_date(dt: datetime | None) -> date:
    return to_local(dt).date() if dt else local_today()


async def _insert_entry(db: AsyncSession, **values: Any) -> LedgerEntry | None:
    """Ghi một dòng sổ; trùng `source_key` thì bỏ qua (idempotent, an toàn cả khi hai tiến trình cùng ghi)."""
    values.setdefault("id", uuid.uuid4())
    values.setdefault("source", LedgerSource.AUTO)
    values["period"] = _period(values["entry_date"])
    stmt = pg_insert(LedgerEntry).values(**values).on_conflict_do_nothing(constraint="uq_ledger_entries_source_key")
    res = await db.execute(stmt.returning(LedgerEntry.id))
    new_id = res.scalar_one_or_none()
    if new_id is None:
        return None
    return await db.get(LedgerEntry, new_id)


# ---- ghi sổ từ sự kiện (k1) --------------------------------------------------------------------------------------


async def record_order_paid(
    db: AsyncSession, order_id: uuid.UUID, payment_id: uuid.UUID | None = None
) -> LedgerEntry | None:
    from app.modules.orders.models import Order

    order = await db.get(Order, order_id)
    if order is None:
        log.warning("order.paid: không thấy đơn %s", order_id)
        return None
    amount = order.total_vnd or order.paid_vnd
    if amount <= 0:
        return None
    return await _insert_entry(
        db,
        entry_date=_local_date(order.paid_at),
        kind=LedgerKind.REVENUE,
        direction=LedgerDirection.IN,
        amount_vnd=amount,
        description=f"Bán hàng theo đơn {order.code}",
        category=str(order.channel),
        document_no=order.code,
        source_key=f"order:{order.id}:revenue",
        order_id=order.id,
        payment_id=payment_id,
    )


async def record_order_refunded(db: AsyncSession, payload: dict[str, Any]) -> LedgerEntry | None:
    from app.modules.orders.models import Order

    order = await db.get(Order, uuid.UUID(str(payload["order_id"])))
    amount = int(payload.get("amount_vnd") or 0)
    if order is None or amount <= 0:
        return None
    ref = payload.get("payment_id") or payload.get("return_id") or amount
    return await _insert_entry(
        db,
        entry_date=local_today(),
        kind=LedgerKind.REFUND,
        direction=LedgerDirection.OUT,
        amount_vnd=amount,
        description=f"Hoàn tiền đơn {order.code}",
        document_no=order.code,
        source_key=f"order:{order.id}:refund:{ref}",
        order_id=order.id,
        payment_id=uuid.UUID(str(payload["payment_id"])) if payload.get("payment_id") else None,
    )


def _expense_kind(category: ExpenseCategory) -> LedgerKind:
    return LedgerKind.SHIPPING if category == ExpenseCategory.SHIPPING else LedgerKind.EXPENSE


async def record_expense(db: AsyncSession, expense_id: uuid.UUID, *, manual: bool = False) -> LedgerEntry | None:
    exp = await db.get(Expense, expense_id)
    if exp is None:
        log.warning("expense.recorded: không thấy chi phí %s", expense_id)
        return None
    return await _insert_entry(
        db,
        entry_date=exp.incurred_on,
        kind=_expense_kind(exp.category),
        direction=LedgerDirection.OUT,
        amount_vnd=exp.amount_vnd,
        description=exp.description + (f" — {exp.vendor}" if exp.vendor else ""),
        category=str(exp.category),
        source=LedgerSource.MANUAL if manual else LedgerSource.AUTO,
        source_key=f"expense:{exp.id}",
        expense_id=exp.id,
        purchase_order_id=exp.purchase_order_id,
        created_by_id=exp.created_by_id,
    )


# ---- chi phí nhập tay --------------------------------------------------------------------------------------------

RECEIPT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "application/pdf": "pdf",
}
MAX_RECEIPT_BYTES = 10 * 1024 * 1024


async def save_receipt(data: bytes, content_type: str | None) -> str:
    ext = RECEIPT_TYPES.get((content_type or "").lower())
    if ext is None:
        raise BadRequest("Chứng từ phải là ảnh (JPG, PNG, WEBP, HEIC) hoặc PDF.", code="receipt_type")
    if len(data) > MAX_RECEIPT_BYTES:
        raise BadRequest("Ảnh chứng từ quá lớn (tối đa 10 MB).", code="receipt_too_large")
    from app.core.storage import new_key

    stored = await get_storage().put(new_key("private/receipts", ext), data, content_type or "application/octet-stream")
    return stored.key


async def create_expense(db: AsyncSession, user: User, **fields: Any) -> Expense:
    exp = Expense(created_by_id=user.id, **fields)
    db.add(exp)
    await db.flush()
    await record_expense(db, exp.id, manual=True)
    await control.audit(db, "finance.expense_created", user=user, entity_type="expense", entity_id=exp.id,
                        summary=f"Ghi chi phí {exp.amount_vnd:,}đ: {exp.description}".replace(",", "."))  # fmt: skip
    return exp


async def update_expense(db: AsyncSession, exp: Expense, user: User, changes: dict[str, Any]) -> Expense:
    for k, v in changes.items():
        setattr(exp, k, v)
    entry = (await db.execute(select(LedgerEntry).where(LedgerEntry.expense_id == exp.id))).scalar_one_or_none()
    if entry is not None:
        entry.entry_date = exp.incurred_on
        entry.period = _period(exp.incurred_on)
        entry.amount_vnd = exp.amount_vnd
        entry.kind = _expense_kind(exp.category)
        entry.category = str(exp.category)
        entry.description = exp.description + (f" — {exp.vendor}" if exp.vendor else "")
    else:
        await db.flush()
        await record_expense(db, exp.id, manual=True)
    await control.audit(db, "finance.expense_updated", user=user, entity_type="expense", entity_id=exp.id,
                        data={k: str(v) for k, v in changes.items()})  # fmt: skip
    await db.flush()
    return exp


async def delete_expense(db: AsyncSession, exp: Expense, user: User) -> None:
    await db.execute(delete(LedgerEntry).where(LedgerEntry.expense_id == exp.id))
    if exp.receipt_storage_key:
        try:
            await get_storage().delete(exp.receipt_storage_key)
        except Exception:
            log.warning("Không xoá được chứng từ %s", exp.receipt_storage_key)
    await control.audit(db, "finance.expense_deleted", user=user, entity_type="expense", entity_id=exp.id,
                        summary=f"Xoá chi phí: {exp.description}")  # fmt: skip
    await db.delete(exp)
    await db.flush()


# ---- kỳ báo cáo, tổng hợp, bảng kê -------------------------------------------------------------------------------


def parse_period(period: str | None) -> tuple[str, str, date, date]:
    """`2026-11` (tháng) · `2026-Q4` (quý) · `2026` (năm) → (khoá, nhãn, từ ngày, tới ngày). Bỏ trống = tháng này."""
    p = (period or local_today().strftime("%Y-%m")).strip().upper()
    try:
        if len(p) == 4:
            y = int(p)
            return p, f"Năm {y}", date(y, 1, 1), date(y, 12, 31)
        if "-Q" in p:
            y, q = int(p[:4]), int(p[-1])
            if not 1 <= q <= 4:
                raise ValueError
            start = date(y, 3 * q - 2, 1)
            end = (date(y + 1, 1, 1) if q == 4 else date(y, 3 * q + 1, 1)) - timedelta(days=1)
            return f"{y}-Q{q}", f"Quý {q}/{y}", start, end
        y, m = int(p[:4]), int(p[5:7])
        start = date(y, m, 1)
        end = (date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)) - timedelta(days=1)
        return f"{y}-{m:02d}", f"Tháng {m}/{y}", start, end
    except (ValueError, IndexError) as e:
        raise BadRequest("Kỳ không hợp lệ: dùng dạng 2026-11 (tháng), 2026-Q4 (quý) hoặc 2026 (năm).") from e


def _totals_cols() -> list[Any]:
    rev = func.coalesce(func.sum(case((LedgerEntry.kind == LedgerKind.REVENUE, LedgerEntry.amount_vnd), else_=0)), 0)
    ref = func.coalesce(func.sum(case((LedgerEntry.kind == LedgerKind.REFUND, LedgerEntry.amount_vnd), else_=0)), 0)
    exp = func.coalesce(
        func.sum(
            case(
                (
                    and_(LedgerEntry.direction == LedgerDirection.OUT, LedgerEntry.kind != LedgerKind.REFUND),
                    LedgerEntry.amount_vnd,
                ),
                else_=0,
            )
        ),
        0,
    )
    return [rev, ref, exp, func.count()]


def _totals(rev: int, ref: int, exp: int, n: int) -> dict[str, int]:
    rev, ref, exp = int(rev), int(ref), int(exp)
    return {"revenue_vnd": rev, "refund_vnd": ref, "net_revenue_vnd": rev - ref, "expense_vnd": exp, "entry_count": n}


async def ledger_summary(db: AsyncSession, period: str | None) -> dict[str, Any]:
    key, label, start, end = parse_period(period)
    in_range = (LedgerEntry.entry_date >= start, LedgerEntry.entry_date <= end)
    tot = (await db.execute(select(*_totals_cols()).where(*in_range))).one()
    months = (
        await db.execute(
            select(LedgerEntry.period, *_totals_cols())
            .where(*in_range)
            .group_by(LedgerEntry.period)
            .order_by(LedgerEntry.period)
        )
    ).all()
    cats = (
        await db.execute(
            select(LedgerEntry.category, func.sum(LedgerEntry.amount_vnd), func.count())
            .where(*in_range, LedgerEntry.direction == LedgerDirection.OUT, LedgerEntry.kind != LedgerKind.REFUND)
            .group_by(LedgerEntry.category)
            .order_by(func.sum(LedgerEntry.amount_vnd).desc())
        )
    ).all()
    return {
        "period": key,
        "label": label,
        "date_from": start,
        "date_to": end,
        "totals": _totals(*tot),
        "by_month": [{"period": p, **_totals(r, f, e, n)} for p, r, f, e, n in months],
        "expenses_by_category": [{"category": c or "other", "amount_vnd": int(a), "count": int(n)} for c, a, n in cats],
    }


def ledger_query(period: str | None, kind: LedgerKind | None = None, direction: LedgerDirection | None = None) -> Any:
    _, _, start, end = parse_period(period)
    q = select(LedgerEntry).where(LedgerEntry.entry_date >= start, LedgerEntry.entry_date <= end)
    if kind is not None:
        q = q.where(LedgerEntry.kind == kind)
    if direction is not None:
        q = q.where(LedgerEntry.direction == direction)
    return q


async def export_csv(db: AsyncSession, period: str | None) -> tuple[str, bytes]:
    """Bảng kê doanh thu, chi phí theo kỳ (UTF-8 có BOM để Excel đọc đúng tiếng Việt)."""
    key, label, start, end = parse_period(period)
    rows = list(
        (await db.execute(ledger_query(key).order_by(LedgerEntry.entry_date, LedgerEntry.created_at))).scalars()
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"BẢNG KÊ DOANH THU, CHI PHÍ — {label.upper()}"])
    w.writerow([f"Từ {start:%d/%m/%Y} đến {end:%d/%m/%Y}. Đơn vị tính: đồng."])
    w.writerow([])
    w.writerow(
        ["STT", "Ngày", "Số chứng từ", "Diễn giải", "Loại", "Nhóm", "Doanh thu", "Giảm trừ", "Chi phí", "Nguồn ghi"]
    )
    rev = ref = exp = 0
    for i, e in enumerate(rows, 1):
        r = e.amount_vnd if e.kind == LedgerKind.REVENUE else 0
        f = e.amount_vnd if e.kind == LedgerKind.REFUND else 0
        x = e.amount_vnd if e.direction == LedgerDirection.OUT and e.kind != LedgerKind.REFUND else 0
        rev, ref, exp = rev + r, ref + f, exp + x
        cat = CATEGORY_LABELS.get(e.category or "", e.category or "")  # type: ignore[call-overload]
        w.writerow([
            i, f"{e.entry_date:%d/%m/%Y}", e.document_no or "", e.description, KIND_LABELS.get(e.kind, str(e.kind)),
            cat if e.direction == LedgerDirection.OUT else "", r or "", f or "", x or "",
            "Tự động" if e.source == LedgerSource.AUTO else "Nhập tay",
        ])  # fmt: skip
    w.writerow([])
    w.writerow(["", "", "", "Tổng cộng", "", "", rev, ref, exp, ""])
    w.writerow(["", "", "", "Doanh thu thuần (doanh thu − giảm trừ)", "", "", rev - ref, "", "", ""])
    return f"so-doanh-thu-chi-phi-{key.lower()}.csv", "﻿".encode() + buf.getvalue().encode("utf-8")


# ---- hoá đơn điện tử (k5) ----------------------------------------------------------------------------------------


def invoice_lines(order: Any) -> list[dict[str, Any]]:
    """Dòng hàng hoá đơn từ đơn: từng món + phí giao + chiết khấu (dòng âm). Tổng các dòng = tổng đơn."""
    lines: list[dict[str, Any]] = []
    for it in order.items:
        name = it.name + (f" ({it.variant_name})" if it.variant_name else "")
        unit = it.line_total_vnd // it.quantity if it.quantity and it.line_total_vnd % it.quantity == 0 else None
        if unit is None:  # dòng có chiết khấu lẻ: gộp thành 1 dòng để tổng khớp
            lines.append({"name": f"{name} × {it.quantity}", "quantity": 1, "unit_price_vnd": it.line_total_vnd})
        else:
            lines.append({"name": name, "quantity": it.quantity, "unit_price_vnd": unit})
    if order.shipping_fee_vnd:
        lines.append({"name": "Phí giao hàng", "unit": "lần", "quantity": 1, "unit_price_vnd": order.shipping_fee_vnd})
    diff = order.total_vnd - sum(ln["quantity"] * ln["unit_price_vnd"] for ln in lines)
    if diff:
        lines.append({"name": "Chiết khấu" if diff < 0 else "Điều chỉnh", "unit": "lần", "quantity": 1,
                      "unit_price_vnd": diff})  # fmt: skip
    return lines


async def latest_approvals(db: AsyncSession, invoice_ids: list[uuid.UUID]) -> dict[uuid.UUID, ApprovalItem]:
    if not invoice_ids:
        return {}
    rows = (
        await db.execute(
            select(ApprovalItem)
            .where(
                ApprovalItem.action == "finance.issue_invoice",
                ApprovalItem.ref_type == "invoices",
                ApprovalItem.ref_id.in_(invoice_ids),
            )
            .order_by(ApprovalItem.created_at)
        )
    ).scalars()
    return {r.ref_id: r for r in rows if r.ref_id}  # bản mới nhất ghi đè


async def prepare_invoice(
    db: AsyncSession,
    order_id: uuid.UUID,
    *,
    user: User | None = None,
    buyer: dict[str, Any] | None = None,
) -> tuple[Invoice, control.ProposeOutcome]:
    """Soạn hoá đơn nháp cho một đơn đã thanh toán rồi đưa qua `control.propose` (mặc định chờ chị duyệt)."""
    from app.modules.orders.models import Order, OrderStatus, PaymentState

    order = await db.get(Order, order_id)
    if order is None:
        raise NotFound("Không tìm thấy đơn.")
    if order.payment_state not in (PaymentState.PAID, PaymentState.PARTIALLY_REFUNDED) or order.status in (
        OrderStatus.CANCELLED,
        OrderStatus.DRAFT,
    ):
        raise BadRequest("Chỉ phát hành hoá đơn cho đơn đã thanh toán.", code="order_not_paid")
    inv = (await db.execute(select(Invoice).where(Invoice.reference == order.code))).scalar_one_or_none()
    if inv is not None and inv.status in (InvoiceStatus.ISSUED, InvoiceStatus.ISSUING):
        raise Conflict("Đơn này đã có hoá đơn.", code="invoice_exists")
    buyer = {k: v for k, v in (buyer or {}).items() if v not in (None, "")}
    lines = invoice_lines(order)
    if inv is None:
        inv = Invoice(reference=order.code, order_id=order.id, provider="", buyer_name="")
        db.add(inv)
    inv.provider = settings.einvoice_driver
    inv.status = InvoiceStatus.DRAFT
    inv.buyer_name = buyer.get("buyer_name") or order.recipient_name
    inv.buyer_tax_code = buyer.get("buyer_tax_code")
    inv.buyer_address = buyer.get("buyer_address") or ", ".join(
        x for x in (order.address_line, order.ward, order.district, order.province) if x
    )
    inv.buyer_email = buyer.get("buyer_email")
    inv.lines = lines
    inv.total_vnd = order.total_vnd
    inv.error = None
    await db.flush()
    payload = {
        "invoice_id": str(inv.id),
        "buyer_name": inv.buyer_name,
        "buyer_tax_code": inv.buyer_tax_code or "",
        "buyer_address": inv.buyer_address or "",
        "buyer_email": inv.buyer_email or "",
    }
    preview = {
        "kind": "invoice",
        "fields": [
            {"label": "Đơn", "value": order.code},
            {"label": "Người mua", "value": inv.buyer_name},
            {"label": "Mã số thuế", "value": inv.buyer_tax_code or "Không có (khách lẻ)"},
            {"label": "Địa chỉ", "value": inv.buyer_address or "—"},
        ],
        "lines": lines,
        "total_vnd": inv.total_vnd,
    }
    outcome = await control.propose(
        "finance.issue_invoice",
        f"Phát hành hoá đơn điện tử cho đơn {order.code}",
        payload,
        preview,
        db=db,
        summary=f"{len(lines)} dòng · tổng {inv.total_vnd:,}đ".replace(",", "."),
        rationale="Đơn đã thanh toán đủ; dòng hàng lấy từ đơn, tổng khớp số tiền khách trả.",
        ref_type="invoices",
        ref_id=inv.id,
        dedupe_key=f"invoice:{inv.id}",
        ai_generated=False,
    )
    if user is not None:
        await control.audit(db, "finance.invoice_prepared", user=user, entity_type="invoice", entity_id=inv.id,
                            summary=f"Soạn hoá đơn cho đơn {order.code}")  # fmt: skip
    return inv, outcome


async def issue_invoice(db: AsyncSession, invoice_id: uuid.UUID, payload: dict[str, Any]) -> Invoice:
    """Gọi nhà cung cấp hoá đơn (driver `einvoice`). Lỗi thì raise để hàng chờ ghi `failed` (duyệt lại được)."""
    from app.integrations import get_driver
    from app.integrations.einvoice import InvoiceLine, InvoiceRequest

    inv = await db.get(Invoice, invoice_id)
    if inv is None:
        raise NotFound("Không tìm thấy hoá đơn.")
    if inv.status == InvoiceStatus.ISSUED:
        return inv
    for f in ("buyer_name", "buyer_tax_code", "buyer_address", "buyer_email"):
        if f in payload:
            setattr(inv, f, (payload[f] or None) if f != "buyer_name" else (payload[f] or inv.buyer_name))
    driver = get_driver("einvoice")
    issued = await driver.issue(
        InvoiceRequest(
            reference=inv.reference,
            buyer_name=inv.buyer_name,
            buyer_tax_code=inv.buyer_tax_code,
            buyer_address=inv.buyer_address,
            buyer_email=inv.buyer_email,
            lines=[InvoiceLine(**ln) for ln in inv.lines],
            total_vnd=inv.total_vnd,
        )
    )
    inv.status = InvoiceStatus.ISSUED
    inv.provider = driver.name
    inv.external_id = issued.external_id
    inv.series = issued.series
    inv.number = issued.number
    inv.lookup_code = issued.lookup_code
    inv.issued_at = issued.issued_at
    inv.raw = {"pdf_url": issued.pdf_url, "xml_url": issued.xml_url}
    inv.error = None
    if inv.order_id:
        entry = (
            await db.execute(
                select(LedgerEntry).where(LedgerEntry.order_id == inv.order_id, LedgerEntry.kind == LedgerKind.REVENUE)
            )
        ).scalar_one_or_none()
        if entry is not None:
            entry.invoice_id = inv.id
            entry.notes = f"Hoá đơn {inv.series}-{inv.number}"
    await db.flush()
    return inv


async def cancel_invoice(db: AsyncSession, invoice_id: uuid.UUID, reason: str) -> None:
    from app.integrations import get_driver

    inv = await db.get(Invoice, invoice_id)
    if inv is None or inv.status != InvoiceStatus.ISSUED:
        raise BadRequest("Hoá đơn này không ở trạng thái đã phát hành.")
    await get_driver("einvoice", inv.provider or None).cancel(inv.external_id or "", reason)
    inv.status = InvoiceStatus.CANCELLED
    await db.execute(
        LedgerEntry.__table__.update().where(LedgerEntry.invoice_id == inv.id).values(invoice_id=None, notes=None)
    )
    await db.flush()


async def invoice_candidates(db: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    from app.modules.orders.models import Order, OrderStatus, PaymentState

    rows = (
        await db.execute(
            select(Order, Invoice.status)
            .outerjoin(Invoice, Invoice.reference == Order.code)
            .where(
                Order.payment_state.in_([PaymentState.PAID, PaymentState.PARTIALLY_REFUNDED]),
                Order.status.not_in([OrderStatus.CANCELLED, OrderStatus.DRAFT]),
                or_(
                    Invoice.id.is_(None),
                    Invoice.status.in_([InvoiceStatus.DRAFT, InvoiceStatus.FAILED, InvoiceStatus.CANCELLED]),
                ),
            )
            .order_by(Order.paid_at.desc().nulls_last())
            .limit(limit)
        )
    ).all()
    return [
        {
            "order_id": o.id,
            "code": o.code,
            "recipient_name": o.recipient_name,
            "total_vnd": o.total_vnd,
            "paid_at": o.paid_at,
            "invoice_status": st,
        }
        for o, st in rows
    ]


# ---- báo cáo tuần (i5) -------------------------------------------------------------------------------------------

# Thời gian chị bỏ ra cho mỗi lần quyết ở hàng chờ duyệt (ước lượng, giây)
REVIEW_SECONDS = {"approved": 40, "edited": 120, "returned": 60}


def week_bounds(ws: date) -> tuple[datetime, datetime]:
    start = datetime.combine(ws, time.min, tzinfo=VN_TZ)
    return start, start + timedelta(days=7)


async def compute_week(db: AsyncSession, ws: date) -> dict[str, Any]:
    """Số liệu một tuần (Thứ Hai → Chủ nhật, giờ VN). Bảng trống → toàn số 0, không lỗi."""
    from app.modules.catalog.models import Product
    from app.modules.content.models import ContentDraft, PostMetric, ScheduledPost
    from app.modules.orders.models import Order, OrderStatus

    we = ws + timedelta(days=6)
    start, end = week_bounds(ws)
    in_week = (LedgerEntry.entry_date >= ws, LedgerEntry.entry_date <= we)
    rev, ref, exp, _ = (await db.execute(select(*_totals_cols()).where(*in_week))).one()
    order_ids = [
        r
        for r in (
            await db.execute(
                select(LedgerEntry.order_id).where(
                    *in_week, LedgerEntry.kind == LedgerKind.REVENUE, LedgerEntry.order_id.is_not(None)
                )
            )
        ).scalars()
    ]
    orders = list((await db.execute(select(Order).where(Order.id.in_(order_ids)))).scalars()) if order_ids else []

    # món: số đơn, số lượng, doanh thu, giá vốn, biên
    by_product: dict[str, dict[str, Any]] = {}
    cogs = 0
    missing_cost = 0
    names: dict[uuid.UUID, str] = {}
    pids = {it.product_id for o in orders for it in o.items if it.product_id}
    if pids:
        names = dict((await db.execute(select(Product.id, Product.name).where(Product.id.in_(pids)))).all())
    for o in orders:
        for it in o.items:
            k = str(it.product_id or it.name)
            p = by_product.setdefault(
                k,
                {"product_id": str(it.product_id) if it.product_id else None,
                 "name": names.get(it.product_id, it.name) if it.product_id else it.name,
                 "orders": set(), "qty": 0, "revenue_vnd": 0, "cost_vnd": 0, "cost_known": True},
            )  # fmt: skip
            p["orders"].add(o.id)
            p["qty"] += it.quantity
            p["revenue_vnd"] += it.line_total_vnd
            if it.unit_cost_vnd is None:
                p["cost_known"] = False
                missing_cost += 1
            else:
                p["cost_vnd"] += it.unit_cost_vnd * it.quantity
                cogs += it.unit_cost_vnd * it.quantity
    margins = []
    for p in by_product.values():
        rv = p["revenue_vnd"]
        margin = round((rv - p["cost_vnd"]) * 100 / rv, 1) if p["cost_known"] and rv > 0 else None
        margins.append({"product_id": p["product_id"], "name": p["name"], "orders": len(p["orders"]), "qty": p["qty"],
                        "revenue_vnd": rv, "cost_vnd": p["cost_vnd"] if p["cost_known"] else None,
                        "margin_pct": margin})  # fmt: skip
    margins.sort(key=lambda m: (-m["orders"], -m["revenue_vnd"]))

    # khách cũ: khách đã có đơn (không nháp, không huỷ) trước đơn trong tuần
    customers = {o.customer_id for o in orders if o.customer_id}
    returning_orders = 0
    returning_customers: set[uuid.UUID] = set()
    for o in orders:
        if not o.customer_id:
            continue
        earlier = await db.scalar(
            select(func.count()).where(
                Order.customer_id == o.customer_id,
                Order.id != o.id,
                Order.placed_at < o.placed_at,
                Order.status.not_in([OrderStatus.DRAFT, OrderStatus.CANCELLED]),
            )
        )
        if earlier:
            returning_orders += 1
            returning_customers.add(o.customer_id)

    # bài kéo đơn: ảnh chụp số liệu mới nhất (trước cuối tuần) của từng bài
    latest = (
        select(PostMetric.scheduled_post_id, func.max(PostMetric.captured_at).label("at"))
        .where(PostMetric.captured_at < end)
        .group_by(PostMetric.scheduled_post_id)
        .subquery()
    )
    post_rows = (
        await db.execute(
            select(ScheduledPost, PostMetric, ContentDraft.title)
            .join(latest, latest.c.scheduled_post_id == ScheduledPost.id)
            .join(
                PostMetric,
                and_(PostMetric.scheduled_post_id == ScheduledPost.id, PostMetric.captured_at == latest.c.at),
            )
            .outerjoin(ContentDraft, ContentDraft.id == ScheduledPost.draft_id)
            .where(
                PostMetric.orders_attributed > 0,
                ScheduledPost.published_at < end,
                ScheduledPost.published_at >= start - timedelta(days=21),
            )
            .order_by(PostMetric.orders_attributed.desc(), PostMetric.revenue_attributed_vnd.desc())
            .limit(3)
        )
    ).all()
    top_posts = [
        {"scheduled_post_id": str(sp.id), "title": title or "Bài không tên", "channel": str(sp.channel),
         "orders": m.orders_attributed, "revenue_vnd": m.revenue_attributed_vnd, "url": sp.external_url}
        for sp, m, title in post_rows
    ]  # fmt: skip

    ai_cost = int(
        await db.scalar(
            select(func.coalesce(func.sum(AIRun.cost_vnd), 0)).where(AIRun.created_at >= start, AIRun.created_at < end)
        )
        or 0
    )

    decided = (
        await db.execute(
            select(ApprovalItem.status, ApprovalItem.edited_payload).where(
                ApprovalItem.decided_at >= start,
                ApprovalItem.decided_at < end,
                ApprovalItem.decided_by_id.is_not(None),
                ApprovalItem.status.in_([ApprovalStatus.APPROVED, ApprovalStatus.RETURNED, ApprovalStatus.FAILED]),
            )
        )
    ).all()
    seconds = sum(
        REVIEW_SECONDS["returned"]
        if st == ApprovalStatus.RETURNED
        else REVIEW_SECONDS["edited" if edited else "approved"]
        for st, edited in decided
    )

    net = int(rev) - int(ref)
    items_revenue = sum(m["revenue_vnd"] for m in margins)
    return {
        "week_start": ws,
        "week_end": we,
        "revenue_vnd": net,
        "cogs_vnd": cogs,
        "gross_profit_vnd": net - cogs,
        "expenses_vnd": int(exp),
        "order_count": len(orders),
        "customer_count": len(customers),
        "returning_customer_count": len(returning_customers),
        "ai_cost_vnd": ai_cost,
        "product_margins": margins[:10],
        "top_posts": top_posts,
        "metrics": {
            "gross_revenue_vnd": int(rev),
            "refund_vnd": int(ref),
            "items_revenue_vnd": items_revenue,
            "gross_margin_pct": round((net - cogs) * 100 / net, 1) if net > 0 and not missing_cost else None,
            "cogs_missing_items": missing_cost,
            "returning_order_count": returning_orders,
            "returning_order_pct": round(returning_orders * 100 / len(orders), 1) if orders else None,
            "review_decisions": len(decided),
            "review_minutes": round(seconds / 60),
            "iso_week": ws.isocalendar().week,
        },
    }


async def generate_report(db: AsyncSession, ws: date | None = None, *, user: User | None = None) -> WeeklyReport:
    """Tính số liệu tuần, lưu `weekly_reports`, rồi nhờ AI viết 2–3 nhận xét (qua control.propose)."""
    from app import ai
    from app.modules.finance.ai_tasks import WeeklyInsightsIn, WeeklyInsightsOut

    ws = week_start(ws or local_today())
    data = await compute_week(db, ws)
    report = (await db.execute(select(WeeklyReport).where(WeeklyReport.week_start == ws))).scalar_one_or_none()
    if report is None:
        report = WeeklyReport(week_start=ws, week_end=data["week_end"])
        db.add(report)
    for k, v in data.items():
        setattr(report, k, v)
    report.status = ReportStatus.READY
    report.generated_at = now_utc()
    report.highlights = []
    report.summary = None
    await db.flush()

    prev = (
        await db.execute(select(WeeklyReport).where(WeeklyReport.week_start == ws - timedelta(days=7)))
    ).scalar_one_or_none()
    inp = WeeklyInsightsIn(
        week=f"Tuần {data['metrics']['iso_week']} ({ws:%d/%m}–{data['week_end']:%d/%m})",
        revenue_vnd=report.revenue_vnd,
        gross_profit_vnd=report.gross_profit_vnd,
        gross_margin_pct=data["metrics"]["gross_margin_pct"],
        order_count=report.order_count,
        returning_order_pct=data["metrics"]["returning_order_pct"],
        ai_cost_vnd=report.ai_cost_vnd,
        review_minutes=data["metrics"]["review_minutes"],
        top_products=[{"name": m["name"], "orders": m["orders"], "margin_pct": m["margin_pct"]} for m in report.product_margins[:5]],
        top_posts=[{"title": p["title"], "channel": p["channel"], "orders": p["orders"]} for p in report.top_posts],
        previous_week_revenue_vnd=prev.revenue_vnd if prev else None,
        previous_week_order_count=prev.order_count if prev else None,
    )  # fmt: skip
    try:
        res = await ai.run("finance.weekly_insights", inp, WeeklyInsightsOut, tier="fast")
    except ai.AIError as e:
        report.metrics = {**report.metrics, "insight_error": e.message}
        await db.flush()
        return report
    out = res.output
    report.ai_run_id = res.run_id
    outcome = await control.propose(
        "finance.weekly_insights",
        f"Nhận xét báo cáo {inp.week}",
        {"report_id": str(report.id), "summary": out.summary, "highlights": out.highlights},
        {"kind": "insights", "text": out.summary, "list": out.highlights},
        db=db,
        summary=out.summary,
        rationale="Rút từ số liệu tuần (doanh thu, món, khách cũ, bài đăng, chi phí AI); không dùng số ngoài báo cáo.",
        ref_type="weekly_reports",
        ref_id=report.id,
        ai_run_id=res.run_id,
        dedupe_key=f"weekly:{ws.isoformat()}",
    )
    if outcome.status != "applied":
        report.metrics = {**report.metrics, "insight_status": outcome.status}
    if user is not None:
        await control.audit(db, "finance.report_generated", user=user, entity_type="weekly_report",
                            entity_id=report.id, summary=f"Lập lại báo cáo {inp.week}")  # fmt: skip
    await db.flush()
    return report


# ---- sao lưu (k4) ------------------------------------------------------------------------------------------------

BACKUP_KEEP_KEY = "finance.backup_keep"
PG_DUMP_MISSING = (
    "Máy chủ chưa có lệnh pg_dump nên chưa sao lưu được. Cài gói postgresql-client (cùng bản với Postgres, "
    "vd postgresql-client-17) vào máy chạy API, hoặc đặt PG_DUMP_PATH trỏ tới pg_dump."
)


def pg_dump_path() -> str | None:
    custom = os.environ.get("PG_DUMP_PATH")
    if custom:
        return custom if os.path.isfile(custom) and os.access(custom, os.X_OK) else None
    return shutil.which("pg_dump")


async def run_backup(db: AsyncSession, trigger: BackupTrigger, user: User | None = None) -> Backup:
    """pg_dump → gzip → storage (`private/backups/...`), ghi `backups`, chỉ giữ N bản gần nhất.
    Lỗi (thiếu pg_dump, sai bản, mất kết nối) → bản ghi `failed` kèm lời giải thích, không raise."""
    started = now_utc()
    b = Backup(kind=BackupKind.DATABASE, status=BackupStatus.RUNNING, trigger=trigger, started_at=started,
               triggered_by_id=user.id if user else None)  # fmt: skip
    db.add(b)
    await db.flush()
    exe = pg_dump_path()
    if exe is None:
        return await _backup_failed(db, b, PG_DUMP_MISSING)
    url = make_url(settings.database_url)
    args = [exe, "--no-owner", "--no-privileges", "--format=plain", "--host", url.host or "localhost",
            "--port", str(url.port or 5432), "--username", url.username or "postgres", url.database or ""]  # fmt: skip
    env = {**os.environ, "PGPASSWORD": url.password or "", "PGCONNECT_TIMEOUT": "10"}
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=900)
    except (OSError, TimeoutError) as e:
        return await _backup_failed(db, b, f"Không chạy được pg_dump: {e}")
    if proc.returncode != 0:
        msg = err.decode("utf-8", "replace").strip()[-800:] or f"pg_dump thoát với mã {proc.returncode}"
        if "server version mismatch" in msg:
            msg = (
                "Bản pg_dump trên máy cũ hơn bản Postgres. Cài postgresql-client cùng bản với máy chủ. Chi tiết: " + msg
            )
        return await _backup_failed(db, b, msg)
    data = gzip.compress(out, compresslevel=6)
    ts = to_local(started)
    key = f"private/backups/{ts:%Y/%m}/hangchon-{ts:%Y%m%d-%H%M%S}-{b.id.hex[:6]}.sql.gz"
    await get_storage().put(key, data, "application/gzip")
    b.storage_key = key
    b.size_bytes = len(data)
    b.checksum = "sha256:" + hashlib.sha256(data).hexdigest()
    b.status = BackupStatus.SUCCEEDED
    b.finished_at = now_utc()
    await db.flush()
    await prune_backups(db)
    await control.audit(db, "finance.backup_created", user=user, entity_type="backup", entity_id=b.id,
                        summary=f"Sao lưu CSDL ({len(data) // 1024} KB)")  # fmt: skip
    return b


async def _backup_failed(db: AsyncSession, b: Backup, message: str) -> Backup:
    b.status = BackupStatus.FAILED
    b.error = message
    b.finished_at = now_utc()
    await db.flush()
    log.warning("Sao lưu lỗi: %s", message)
    return b


async def backup_keep(db: AsyncSession) -> int:
    try:
        return max(1, int(await control.get_setting(db, BACKUP_KEEP_KEY) or 14))
    except (TypeError, ValueError):
        return 14


async def prune_backups(db: AsyncSession) -> int:
    keep = await backup_keep(db)
    old = list(
        (
            await db.execute(
                select(Backup)
                .where(Backup.status == BackupStatus.SUCCEEDED)
                .order_by(Backup.started_at.desc())
                .offset(keep)
            )
        ).scalars()
    )
    storage = get_storage()
    for b in old:
        if b.storage_key:
            try:
                await storage.delete(b.storage_key)
            except Exception:
                log.warning("Không xoá được bản sao lưu cũ %s", b.storage_key)
        await db.delete(b)
    await db.flush()
    return len(old)
