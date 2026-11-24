"""Route của finance: /api/desk/finance/* — sổ sách (k1), hoá đơn (k5), báo cáo tuần (i5), sao lưu (k4)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select

from app.core.db import DbSession
from app.core.deps import CurrentUser, OwnerUser
from app.core.errors import BadRequest, NotFound
from app.core.pagination import Page, Paginated, paginate
from app.core.storage import get_storage
from app.modules.finance import service
from app.modules.finance.models import (
    Backup,
    BackupStatus,
    BackupTrigger,
    Expense,
    ExpenseCategory,
    Invoice,
    InvoiceStatus,
    LedgerDirection,
    LedgerEntry,
    LedgerKind,
    WeeklyReport,
)
from app.modules.finance.schemas import (
    BackupConfigOut,
    BackupOut,
    ExpenseOut,
    ExpenseUpdate,
    InvoiceCandidateOut,
    InvoiceCreate,
    InvoiceListOut,
    InvoiceProposeOut,
    LedgerEntryOut,
    LedgerSummaryOut,
    ReportGenerateIn,
    WeeklyReportOut,
)

router = APIRouter(prefix="/api/desk/finance", tags=["finance"])

Period = Annotated[str | None, Query(description="2026-11 (tháng) · 2026-Q4 (quý) · 2026 (năm); trống = tháng này")]


# ---- sổ doanh thu, chi phí (k1) ----------------------------------------------------------------------------------


@router.get("/ledger/summary", response_model=LedgerSummaryOut, summary="Tổng hợp sổ theo kỳ")
async def ledger_summary(_: CurrentUser, db: DbSession, period: Period = None) -> dict:
    return await service.ledger_summary(db, period)


@router.get("/ledger/export.csv", summary="Bảng kê CSV (UTF-8 BOM) phục vụ khai thuế")
async def ledger_export(_: OwnerUser, db: DbSession, period: Period = None) -> Response:
    filename, data = await service.export_csv(db, period)
    return Response(
        data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ledger", response_model=Paginated[LedgerEntryOut], summary="Sổ doanh thu, chi phí (k1)")
async def list_ledger(
    _: CurrentUser,
    db: DbSession,
    page: Page,
    period: Period = None,
    kind: LedgerKind | None = None,
    direction: LedgerDirection | None = None,
) -> Paginated[LedgerEntryOut]:
    q = service.ledger_query(period, kind, direction).order_by(
        LedgerEntry.entry_date.desc(), LedgerEntry.created_at.desc()
    )
    return await paginate(db, q, page, LedgerEntryOut)


# ---- chi phí -----------------------------------------------------------------------------------------------------


@router.get("/expenses", response_model=Paginated[ExpenseOut])
async def list_expenses(
    _: CurrentUser, db: DbSession, page: Page, period: Period = None, category: ExpenseCategory | None = None
) -> Paginated[ExpenseOut]:
    _, _, start, end = service.parse_period(period)
    q = select(Expense).where(Expense.incurred_on >= start, Expense.incurred_on <= end)
    if category is not None:
        q = q.where(Expense.category == category)
    return await paginate(db, q.order_by(Expense.incurred_on.desc(), Expense.created_at.desc()), page, ExpenseOut)


@router.post("/expenses", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED, summary="Nhập chi phí tay")
async def create_expense(
    user: CurrentUser,
    db: DbSession,
    incurred_on: Annotated[date, Form()],
    category: Annotated[ExpenseCategory, Form()],
    amount_vnd: Annotated[int, Form(gt=0)],
    description: Annotated[str, Form(min_length=1, max_length=2000)],
    vendor: Annotated[str | None, Form(max_length=200)] = None,
    payment_method: Annotated[str | None, Form(max_length=30)] = None,
    is_deductible: Annotated[bool, Form()] = True,
    receipt: Annotated[UploadFile | None, File(description="Ảnh hoặc PDF chứng từ")] = None,
) -> Expense:
    key = None
    if receipt is not None and receipt.filename:
        key = await service.save_receipt(await receipt.read(), receipt.content_type)
    return await service.create_expense(
        db, user, incurred_on=incurred_on, category=category, amount_vnd=amount_vnd, description=description.strip(),
        vendor=(vendor or "").strip() or None, payment_method=payment_method or None, is_deductible=is_deductible,
        receipt_storage_key=key,
    )  # fmt: skip


async def _expense(db: DbSession, expense_id: uuid.UUID) -> Expense:
    exp = await db.get(Expense, expense_id)
    if exp is None:
        raise NotFound("Không tìm thấy khoản chi.")
    return exp


@router.patch("/expenses/{expense_id}", response_model=ExpenseOut)
async def update_expense(expense_id: uuid.UUID, body: ExpenseUpdate, user: OwnerUser, db: DbSession) -> Expense:
    exp = await _expense(db, expense_id)
    return await service.update_expense(db, exp, user, body.model_dump(exclude_unset=True, exclude_none=True))


@router.post("/expenses/{expense_id}/receipt", response_model=ExpenseOut, summary="Thay ảnh chứng từ")
async def upload_receipt(
    expense_id: uuid.UUID, user: CurrentUser, db: DbSession, receipt: Annotated[UploadFile, File()]
) -> Expense:
    exp = await _expense(db, expense_id)
    old = exp.receipt_storage_key
    exp.receipt_storage_key = await service.save_receipt(await receipt.read(), receipt.content_type)
    if old:
        try:
            await get_storage().delete(old)
        except Exception:
            service.log.warning("Không xoá được chứng từ cũ %s", old)
    await db.flush()
    return exp


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(expense_id: uuid.UUID, user: OwnerUser, db: DbSession) -> None:
    await service.delete_expense(db, await _expense(db, expense_id), user)


# ---- hoá đơn điện tử (k5) ----------------------------------------------------------------------------------------


async def _with_approvals(db: DbSession, invoices: list[Invoice]) -> list[InvoiceListOut]:
    approvals = await service.latest_approvals(db, [i.id for i in invoices])
    out = []
    for inv in invoices:
        row = InvoiceListOut.model_validate(inv)
        a = approvals.get(inv.id)
        if a is not None:
            row.approval_item_id, row.approval_status, row.approval_error = a.id, str(a.status), a.error
        out.append(row)
    return out


@router.get(
    "/invoices/candidates", response_model=list[InvoiceCandidateOut], summary="Đơn đã thanh toán chưa có hoá đơn"
)
async def invoice_candidates(_: CurrentUser, db: DbSession) -> list[dict]:
    return await service.invoice_candidates(db)


@router.get("/invoices", response_model=Paginated[InvoiceListOut], summary="Hoá đơn điện tử (k5)")
async def list_invoices(
    _: CurrentUser, db: DbSession, page: Page, status_: Annotated[InvoiceStatus | None, Query(alias="status")] = None
) -> Paginated[InvoiceListOut]:
    q = select(Invoice)
    if status_ is not None:
        q = q.where(Invoice.status == status_)
    res = await paginate(db, q.order_by(Invoice.updated_at.desc()), page)
    res.items = await _with_approvals(db, list(res.items))
    return res  # type: ignore[return-value]


@router.post("/invoices", response_model=InvoiceProposeOut, status_code=status.HTTP_201_CREATED,
             summary="Soạn hoá đơn cho đơn đã thanh toán (đi qua hàng chờ duyệt)")  # fmt: skip
async def create_invoice(body: InvoiceCreate, user: OwnerUser, db: DbSession) -> dict:
    inv, outcome = await service.prepare_invoice(
        db, body.order_id, user=user, buyer=body.model_dump(exclude={"order_id"}, exclude_none=True)
    )
    await db.refresh(inv)
    return {
        "invoice": (await _with_approvals(db, [inv]))[0],
        "outcome": outcome.status,
        "approval_item_id": outcome.item_id,
        "error": outcome.error,
    }


@router.get("/invoices/{invoice_id}", response_model=InvoiceListOut)
async def get_invoice(invoice_id: uuid.UUID, _: CurrentUser, db: DbSession) -> InvoiceListOut:
    inv = await db.get(Invoice, invoice_id)
    if inv is None:
        raise NotFound("Không tìm thấy hoá đơn.")
    return (await _with_approvals(db, [inv]))[0]


# ---- báo cáo tuần (i5) -------------------------------------------------------------------------------------------


@router.get("/reports", response_model=Paginated[WeeklyReportOut], summary="Báo cáo tuần (i5)")
async def list_reports(_: CurrentUser, db: DbSession, page: Page) -> Paginated[WeeklyReportOut]:
    return await paginate(db, select(WeeklyReport).order_by(WeeklyReport.week_start.desc()), page, WeeklyReportOut)


@router.post("/reports/generate", response_model=WeeklyReportOut, summary="Lập (lại) báo cáo một tuần")
async def generate_report(body: ReportGenerateIn, user: OwnerUser, db: DbSession) -> WeeklyReport:
    report = await service.generate_report(db, body.week_start, user=user)
    await db.refresh(report)
    return report


@router.get("/reports/{report_id}", response_model=WeeklyReportOut)
async def get_report(report_id: uuid.UUID, _: CurrentUser, db: DbSession) -> WeeklyReport:
    r = await db.get(WeeklyReport, report_id)
    if r is None:
        raise NotFound("Không tìm thấy báo cáo.")
    return r


# ---- sao lưu (k4) ------------------------------------------------------------------------------------------------


@router.get("/backups/config", response_model=BackupConfigOut)
async def backup_config(_: OwnerUser, db: DbSession) -> dict:
    last = await db.scalar(
        select(Backup.finished_at)
        .where(Backup.status == BackupStatus.SUCCEEDED)
        .order_by(Backup.started_at.desc())
        .limit(1)
    )
    return {
        "pg_dump": service.pg_dump_path(),
        "keep": await service.backup_keep(db),
        "schedule": "Hằng ngày lúc 3:15 sáng",
        "last_success_at": last,
    }


@router.get("/backups", response_model=Paginated[BackupOut], summary="Các bản sao lưu (k4)")
async def list_backups(_: OwnerUser, db: DbSession, page: Page) -> Paginated[BackupOut]:
    return await paginate(db, select(Backup).order_by(Backup.started_at.desc()), page, BackupOut)


@router.post("/backups", response_model=BackupOut, status_code=status.HTTP_201_CREATED, summary="Sao lưu ngay")
async def create_backup(user: OwnerUser, db: DbSession) -> Backup:
    return await service.run_backup(db, BackupTrigger.MANUAL, user)


@router.get("/backups/{backup_id}/download", summary="Tải bản sao lưu (.sql.gz)")
async def download_backup(backup_id: uuid.UUID, _: OwnerUser, db: DbSession) -> Response:
    b = await db.get(Backup, backup_id)
    if b is None or b.status != BackupStatus.SUCCEEDED or not b.storage_key:
        raise NotFound("Không có tệp sao lưu này.")
    try:
        data = await get_storage().get(b.storage_key)
    except (FileNotFoundError, ValueError) as e:
        raise BadRequest("Tệp sao lưu không còn trong kho lưu trữ.") from e
    name = b.storage_key.rsplit("/", 1)[-1]
    return Response(
        data,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store"},
    )
