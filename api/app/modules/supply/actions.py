"""Khai báo với control: hành động AI của nguồn cung, cài đặt giá vốn, số liệu «Hôm nay»."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.errors import NotFound
from app.modules.supply import service
from app.modules.supply.models import (
    InboundShipment,
    InboundStatus,
    POStatus,
    PriceProposal,
    ProposalStatus,
    PurchaseOrder,
    Supplier,
    SupplierMessage,
    SupplierMessageStatus,
)

GROUP = "Nguồn cung"

control.register_action(
    "supply.set_price",
    "Đặt giá bán theo đề xuất của AI",
    GROUP,
    default="ask",
    customer_facing=True,
    description="AI đề xuất giá theo giá vốn về tay, giá thị trường và biên lợi nhuận chị đặt.",
)
control.register_action(
    "supply.place_order",
    "Đặt mẫu, đặt lô với nhà cung cấp",
    GROUP,
    locked=True,
    description="AI soạn đơn cho bên mua hộ hoặc nhà cung cấp. Đặt hàng và trả tiền luôn chờ chị duyệt.",
)
control.register_action(
    "supply.send_supplier_message",
    "Gửi tin hỏi nhà cung cấp",
    GROUP,
    default="ask",
    description="AI soạn tin tiếng Trung, tiếng Nhật hỏi giá, số lượng tối thiểu, thời gian; chị duyệt rồi gửi.",
)
control.register_action(
    "supply.read_supplier_reply",
    "Dịch và rút thông tin từ tin của nhà cung cấp",
    GROUP,
    default="auto",
    description="AI dịch câu trả lời và ghi lại giá, số lượng tối thiểu, thời gian chuẩn bị hàng.",
)

control.register_action(
    service.ACTION_RECALC,
    "Tính lại giá vốn khi tỷ giá, cước đổi",
    GROUP,
    default="auto",
    description="Mỗi sáng và khi chị đổi tham số, AI tính lại giá vốn về tay. Đổi từ 2% trở lên thì ghi nhật ký; "
    "hoàn tác = khôi phục số cũ.",
)
control.register_action(
    service.ACTION_TRACK,
    "Cập nhật mốc lô hàng về từ hãng vận chuyển",
    GROUP,
    default="auto",
    description="AI tự dò vận đơn mỗi 30 phút, có mốc mới thì ghi vào lô. Chỉ ghi nhật ký khi có mốc mới.",
)
control.register_action(
    service.ACTION_TRUST,
    "Đổi bậc uy tín nhà cung cấp",
    GROUP,
    default="auto",
    description="Điểm uy tín tính từ lịch sử đúng hẹn và hàng lỗi. Ghi nhật ký khi nhà cung cấp đổi bậc "
    "(Tin được / Tạm ổn / Cần dè chừng).",
)
control.register_action(
    service.ACTION_READ_DOC,
    "Đọc chứng từ nguồn gốc",
    GROUP,
    default="auto",
    description="AI đọc ảnh hoặc PDF hoá đơn, tờ khai, nhãn gốc: tên hàng, nhà sản xuất, xuất xứ, số lô, ngày, "
    "chứng nhận. Chị sửa được; hoàn tác = xoá phần AI đọc.",
)

control.register_setting(
    service.COST_PARAMS_KEY, "Tham số giá vốn về tay", service.DEFAULT_COST_PARAMS, group=GROUP,
    description="Tỷ giá, cước quốc tế theo kg, phí mua hộ, thuế, hao hụt, biên mục tiêu. Đổi thì tính lại giá vốn.",
)  # fmt: skip


@control.handler("supply.set_price")
async def _set_price(ctx: control.ActionContext) -> control.HandlerResult:
    p = await service.apply_price(ctx.db, uuid.UUID(ctx.payload["proposal_id"]), int(ctx.payload["price_vnd"]))
    return control.HandlerResult(
        result={"proposal_id": str(p.id), "price_vnd": p.approved_price_vnd},
        summary=f"Giá bán {service.format_vnd(p.approved_price_vnd, suffix='đ')}",
        ref_type="price_proposals",
        ref_id=p.id,
    )


@control.on_returned("supply.set_price")
async def _price_returned(ctx: control.ReturnContext) -> None:
    p = await ctx.db.get(PriceProposal, uuid.UUID(ctx.item.payload["proposal_id"]))
    if p is not None and p.status == ProposalStatus.PENDING_REVIEW:
        p.status = ProposalStatus.REJECTED
        p.decided_at = service.now_utc()
        p.rationale = (p.rationale or "") + f"\nChị trả lại: {ctx.note}"


@control.handler("supply.place_order")
async def _place_order(ctx: control.ActionContext) -> control.HandlerResult:
    po = await service.apply_place_order(ctx.db, ctx.payload)
    return control.HandlerResult(
        result={"purchase_order_id": str(po.id), "status": po.status.value},
        summary=f"Đơn {po.code} đã duyệt, chờ gửi",
        ref_type="purchase_orders",
        ref_id=po.id,
    )


@control.on_returned("supply.place_order")
async def _order_returned(ctx: control.ReturnContext) -> None:
    po = await ctx.db.get(PurchaseOrder, uuid.UUID(ctx.item.payload["purchase_order_id"]))
    if po is not None and po.status == POStatus.PENDING_APPROVAL:
        po.status = POStatus.DRAFT
        po.notes = (po.notes + "\n" if po.notes else "") + f"Chị trả lại: {ctx.note}"


@control.handler("supply.send_supplier_message")
async def _send_message(ctx: control.ActionContext) -> control.HandlerResult:
    msg = await service.apply_message_approval(ctx.db, ctx.payload)
    return control.HandlerResult(
        result={"message_id": str(msg.id)}, summary="Tin hỏi đã duyệt, chờ gửi",
        ref_type="supplier_messages", ref_id=msg.id,
    )  # fmt: skip


@control.on_returned("supply.send_supplier_message")
async def _message_returned(ctx: control.ReturnContext) -> None:
    msg = await ctx.db.get(SupplierMessage, uuid.UUID(ctx.item.payload["message_id"]))
    if msg is not None and msg.status == SupplierMessageStatus.PENDING_REVIEW:
        msg.status = SupplierMessageStatus.DRAFT


@control.handler("supply.read_supplier_reply")
async def _read_reply(ctx: control.ActionContext) -> control.HandlerResult:
    msg = await service.apply_reply(ctx.db, ctx.payload)
    return control.HandlerResult(
        result={"message_id": str(msg.id)}, summary=(msg.extracted or {}).get("summary") or "Đã dịch tin",
        ref_type="supplier_messages", ref_id=msg.id,
    )  # fmt: skip


@control.handler(service.ACTION_RECALC)
async def _recalc(ctx: control.ActionContext) -> control.HandlerResult:
    return await service.apply_recalc(ctx.db, ctx.payload)


@control.undoer(service.ACTION_RECALC)
async def _undo_recalc(ctx: control.UndoContext) -> None:
    await service.undo_recalc(ctx.db, ctx.undo)


@control.handler(service.ACTION_TRACK)
async def _track(ctx: control.ActionContext) -> control.HandlerResult:
    return await service.apply_track_action(ctx.db, ctx.payload)


@control.undoer(service.ACTION_TRACK)
async def _undo_track(ctx: control.UndoContext) -> None:
    await service.undo_track_action(ctx.db, ctx.undo)


@control.handler(service.ACTION_TRUST)
async def _trust(ctx: control.ActionContext) -> control.HandlerResult:
    s = await ctx.db.get(Supplier, uuid.UUID(ctx.payload["supplier_id"]))
    if s is None:
        raise NotFound("Không tìm thấy nhà cung cấp.")
    s.trust_score = ctx.payload["trust_score"]
    label, basis = service.trust_label(s)
    return control.HandlerResult(
        result={"supplier_id": str(s.id), "trust_score": s.trust_score}, summary=f"{s.name}: {label} ({basis})",
        ref_type="suppliers", ref_id=s.id,
    )  # fmt: skip


@control.handler(service.ACTION_READ_DOC)
async def _read_doc(ctx: control.ActionContext) -> control.HandlerResult:
    return await service.apply_document_read(ctx.db, ctx.payload)


@control.undoer(service.ACTION_READ_DOC)
async def _undo_read_doc(ctx: control.UndoContext) -> None:
    await service.undo_document_read(ctx.db, ctx.undo)


@control.stat_provider("supply.overview", order=50)
async def _stats(db: AsyncSession) -> list[control.Stat]:
    arriving = await db.scalar(
        select(func.count()).where(InboundShipment.status.not_in([InboundStatus.DELIVERED, InboundStatus.PROBLEM]))
    )
    missing = len(await service.document_warnings(db))
    out = [
        control.Stat(key="supply.arriving", label="Lô hàng đang về", value=int(arriving or 0),
                     href="/desk/nguon-cung?tab=lo-hang", order=40),
    ]  # fmt: skip
    if missing:
        out.append(
            control.Stat(key="supply.missing_docs", label="Lô thiếu chứng từ", value=missing,
                         href="/desk/nguon-cung?tab=chung-tu", order=41)
        )  # fmt: skip
    return out
