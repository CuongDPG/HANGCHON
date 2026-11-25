"""Khai báo của finance: hành động (hoá đơn điện tử k5, nhận xét báo cáo tuần i5), cài đặt, số liệu «Hôm nay»."""

from __future__ import annotations

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.errors import Forbidden
from app.core.timeutil import local_today
from app.modules.control.models import UserRole
from app.modules.finance import service
from app.modules.finance.models import (
    Backup,
    BackupStatus,
    Invoice,
    InvoiceStatus,
    LedgerEntry,
    LedgerKind,
    WeeklyReport,
)

# ---- k5: hoá đơn điện tử -----------------------------------------------------------------------------------------

control.register_action(
    "finance.issue_invoice",
    "Phát hành hoá đơn điện tử",
    "Sổ sách",
    default="ask",
    customer_facing=True,
    description="Gửi hoá đơn cho đơn đã thanh toán qua nhà cung cấp hoá đơn điện tử. Khách và cơ quan thuế nhận được.",
)


@control.handler("finance.issue_invoice")
async def _issue(ctx: control.ActionContext) -> control.HandlerResult:
    inv = await service.issue_invoice(ctx.db, uuid.UUID(ctx.payload["invoice_id"]), ctx.payload)
    return control.HandlerResult(
        result={"invoice_id": str(inv.id), "series": inv.series, "number": inv.number, "lookup_code": inv.lookup_code},
        undo={"invoice_id": str(inv.id)},
        summary=f"Đã phát hành hoá đơn {inv.series}-{inv.number} cho đơn {inv.reference}",
        ref_type="invoices",
        ref_id=inv.id,
    )


@control.undoer("finance.issue_invoice")
async def _cancel(ctx: control.UndoContext) -> None:
    await service.cancel_invoice(ctx.db, uuid.UUID(ctx.undo["invoice_id"]), "Huỷ từ nhật ký AI")


@control.on_returned("finance.issue_invoice")
async def _returned(ctx: control.ReturnContext) -> None:
    inv = await ctx.db.get(Invoice, uuid.UUID(ctx.item.payload["invoice_id"]))
    if inv is not None and inv.status == InvoiceStatus.DRAFT:
        inv.raw = {**inv.raw, "returned_note": ctx.note}


# ---- i5: nhận xét báo cáo tuần -----------------------------------------------------------------------------------

control.register_action(
    "finance.weekly_insights",
    "Viết nhận xét báo cáo tuần",
    "Báo cáo",
    default="auto",
    description="AI đọc số liệu tuần và viết 2–3 điều rút ra. Chỉ chị xem.",
)


@control.handler("finance.weekly_insights")
async def _insights(ctx: control.ActionContext) -> control.HandlerResult:
    report = await ctx.db.get(WeeklyReport, uuid.UUID(ctx.payload["report_id"]))
    if report is None:
        return control.HandlerResult(result={"skipped": True}, summary="Báo cáo đã bị xoá")
    report.summary = ctx.payload.get("summary")
    report.highlights = list(ctx.payload.get("highlights") or [])
    report.metrics = {k: v for k, v in report.metrics.items() if k not in ("insight_status", "insight_error")}
    return control.HandlerResult(
        result={"report_id": str(report.id)},
        summary=f"Viết {len(report.highlights)} nhận xét cho báo cáo tuần {report.week_start:%d/%m}",
        ref_type="weekly_reports",
        ref_id=report.id,
    )


# ---- cài đặt -----------------------------------------------------------------------------------------------------

control.register_setting(service.BACKUP_KEEP_KEY, "Số bản sao lưu giữ lại", 14, group="Sao lưu",
                         description="Bản cũ hơn tự xoá sau mỗi lần sao lưu thành công.")  # fmt: skip
control.register_setting("finance.auto_invoice", "Tự soạn hoá đơn khi đơn đã thanh toán", False, group="Hoá đơn",
                         description="Bật thì mỗi đơn đã thanh toán có sẵn hoá đơn nháp trong hàng chờ duyệt.")  # fmt: skip


# ---- số liệu «Hôm nay» -------------------------------------------------------------------------------------------


@control.stat_provider("finance.month", order=40)
async def _stats(db: AsyncSession) -> list[control.Stat]:
    period = local_today().strftime("%Y-%m")
    rev = func.coalesce(
        func.sum(
            case(
                (LedgerEntry.kind == LedgerKind.REVENUE, LedgerEntry.amount_vnd),
                (LedgerEntry.kind == LedgerKind.REFUND, -LedgerEntry.amount_vnd),
                else_=0,
            )
        ),
        0,
    )
    net = int(await db.scalar(select(rev).where(LedgerEntry.period == period)) or 0)
    return [
        control.Stat(
            key="finance.month_revenue", label="Doanh thu tháng này", value=net, format="vnd", href="/desk/so-sach",
            order=40,
        )
    ]  # fmt: skip


# ---- lệnh bằng lời (i6) ------------------------------------------------------------------------------------------


@control.intent(
    "finance.verify_backup",
    "Kiểm khôi phục bản sao lưu gần nhất",
    "Giải nén bản sao lưu thành công gần nhất, so checksum, đọc cấu trúc. Chỉ kiểm, không khôi phục đè dữ liệu.",
    examples=["kiểm bản sao lưu gần nhất", "bản sao lưu có dùng được không"],
)
async def _verify_backup_cmd(ctx: control.CommandContext, _: None) -> control.CommandResult:
    if ctx.user is None or ctx.user.role != UserRole.OWNER:  # cùng quyền với màn Sao lưu
        raise Forbidden("Chỉ chị (chủ cửa hàng) xem được phần sao lưu.")
    last = await ctx.db.scalar(
        select(Backup).where(Backup.status == BackupStatus.SUCCEEDED).order_by(Backup.started_at.desc()).limit(1)
    )
    if last is None:
        return control.CommandResult(
            message="Chưa có bản sao lưu thành công nào để kiểm.", href="/desk/cai-dat/sao-luu"
        )
    b = (await service.with_meta(ctx.db, [await service.verify_backup(ctx.db, last.id, ctx.user)]))[0]
    return control.CommandResult(
        message=b["verify_note"] or "", href="/desk/cai-dat/sao-luu", data={"ok": b["verify_ok"]}
    )
