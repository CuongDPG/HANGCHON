"""Khai báo của orders với control: hành động (mức tự chủ), hàm thực thi, cài đặt, số liệu «Hôm nay»."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from unidecode import unidecode

from app import control
from app.core.config import settings
from app.core.enums import Channel
from app.core.timeutil import local_day_bounds_utc
from app.modules.orders import drafts, notify, payments, returns, service, shipping
from app.modules.orders.models import Order, OrderStatus, Payment, PaymentDirection, PaymentStatus

GROUP = "Đơn hàng"

# ---- hành động ---------------------------------------------------------------------------------------------------

control.register_action(
    shipping.SHIP_ACTION, "Tạo vận đơn (chọn hãng theo phí và thời gian)", GROUP, default="auto",
    description="AI so phí và số ngày giao của các hãng đã bật, chọn hãng hợp lý nhất rồi tạo vận đơn.",
)  # fmt: skip
control.register_action(
    drafts.CONFIRM_ACTION, "Chốt đơn nháp từ tin nhắn", GROUP, default="ask", customer_facing=True,
    description="AI nhận ra khách muốn mua trong tin nhắn và soạn đơn nháp. Chốt đơn thì khách nhận tin xác nhận.",
)  # fmt: skip
control.register_action(
    payments.REVIEW_ACTION, "Xử lý khoản tiền lệch hoặc chưa khớp đơn", GROUP, default="ask",
    description="Chuyển thiếu, thừa, sai nội dung, tiền vào đơn đã huỷ: AI đề xuất cách xử lý, chị quyết.",
)  # fmt: skip
control.register_action(
    returns.DECIDE_ACTION, "Đổi trả, hoàn tiền", GROUP, locked=True, customer_facing=True,
    description="AI kiểm điều kiện và soạn phương án; luôn cần chị quyết.",
)  # fmt: skip
control.register_action(
    "orders.customer_question", "Khách hỏi về đơn", GROUP, default="ask", customer_facing=True,
    description="Khách bấm «Hỏi về đơn này». Chị ghi câu trả lời rồi duyệt để gửi khách.",
)  # fmt: skip
control.register_action(
    "orders.restock_alert", "Báo món giữ sẵn sắp hết", GROUP, default="ask",
    description="Tồn còn bằng hoặc dưới ngưỡng. Chị xem để đặt thêm; duyệt = đã biết.",
)  # fmt: skip
control.register_action(
    shipping.PROBLEM_ACTION, "Giao hàng trục trặc", GROUP, default="ask",
    description="Hãng báo giao không thành công / hoàn hàng. Chị gọi khách hoặc hẹn giao lại; duyệt = đã xử lý.",
)  # fmt: skip


@control.handler(shipping.SHIP_ACTION)
async def _ship(ctx: control.ActionContext) -> control.HandlerResult:
    order = await service.get_order(ctx.db, uuid.UUID(ctx.payload["order_id"]), lock=True)
    sh = await shipping.create_shipment(
        ctx.db, order, ctx.payload["driver"], ctx.payload["service"], reason=ctx.payload.get("reason"),
        quotes=ctx.payload.get("quotes") or [],
    )  # fmt: skip
    return control.HandlerResult(
        result={"shipment_id": str(sh.id), "tracking_code": sh.tracking_code, "fee_vnd": sh.fee_vnd},
        summary=f"Vận đơn {sh.tracking_code} cho đơn {order.code} ({notify.vnd(sh.fee_vnd)})",
        ref_type="orders", ref_id=order.id,
    )  # fmt: skip


@control.handler(drafts.CONFIRM_ACTION)
async def _confirm_draft(ctx: control.ActionContext) -> control.HandlerResult:
    order = await service.get_order(ctx.db, uuid.UUID(ctx.payload["order_id"]), lock=True)
    patch = {k: v for k, v in ctx.payload.items() if k != "order_id"}
    await drafts.confirm(ctx.db, order, patch or None, user=ctx.user)
    return control.HandlerResult(
        result={"order_id": str(order.id), "code": order.code, "status": order.status.value},
        summary=f"Chốt đơn {order.code} · {notify.vnd(order.total_vnd)}", ref_type="orders", ref_id=order.id,
    )  # fmt: skip


@control.handler(payments.REVIEW_ACTION)
async def _review_payment(ctx: control.ActionContext) -> control.HandlerResult:
    summary = await payments.resolve_review(ctx.db, ctx.payload, user=ctx.user)
    return control.HandlerResult(result={"summary": summary}, summary=summary)


@control.handler(returns.DECIDE_ACTION)
async def _decide_return(ctx: control.ActionContext) -> control.HandlerResult:
    summary = await returns.decide(ctx.db, ctx.payload, user=ctx.user)
    return control.HandlerResult(result={"summary": summary}, summary=summary)


@control.on_returned(returns.DECIDE_ACTION)
async def _return_redo(ctx: control.ReturnContext) -> None:
    await returns.redo_after_return(ctx.db, ctx.item.ref_id, ctx.note)


@control.handler("orders.customer_question")
async def _answer_question(ctx: control.ActionContext) -> control.HandlerResult:
    order = await service.get_order(ctx.db, uuid.UUID(ctx.payload["order_id"]))
    reply = (ctx.payload.get("reply") or "").strip()
    if reply:
        await notify.notify_order(
            ctx.db, order, "owner_reply", {"noi_dung": reply}, dedupe=ctx.payload.get("question_id")
        )
        service.add_event(ctx.db, order, "owner_reply", "Mình đã trả lời câu hỏi của bạn", detail=reply)
    return control.HandlerResult(
        result={"replied": bool(reply)}, summary=f"Trả lời khách đơn {order.code}" if reply else f"Đã xem câu hỏi đơn {order.code}",
        ref_type="orders", ref_id=order.id,
    )  # fmt: skip


@control.handler("orders.restock_alert")
async def _ack_restock(ctx: control.ActionContext) -> control.HandlerResult:
    return control.HandlerResult(result={"acknowledged": True}, summary="Chị đã biết món sắp hết")


@control.handler(shipping.PROBLEM_ACTION)
async def _ack_problem(ctx: control.ActionContext) -> control.HandlerResult:
    order = await service.get_order(ctx.db, uuid.UUID(ctx.payload["order_id"]))
    note = (ctx.payload.get("note") or "").strip()
    if note:
        order.internal_note = ((order.internal_note or "") + f"\n{note}").strip()
    return control.HandlerResult(result={"acknowledged": True}, summary=f"Đã xử lý trục trặc giao đơn {order.code}")


# ---- cài đặt -----------------------------------------------------------------------------------------------------

control.register_setting(
    "orders.payment_window_hours",
    "Giữ suất chờ chuyển khoản (giờ)",
    24,
    group=GROUP,
    description="Quá giờ này chưa nhận tiền thì đơn tự huỷ và trả suất (nếu bật tự huỷ).",
)
control.register_setting("orders.payment_reminder_hours", "Nhắc khách chuyển khoản sau (giờ)", 6, group=GROUP)
control.register_setting("orders.auto_cancel_unpaid", "Tự huỷ đơn quá hạn chuyển khoản", True, group=GROUP)
control.register_setting("orders.return_window_days", "Hạn đổi trả (ngày kể từ khi nhận)", 7, group=GROUP)
control.register_setting(
    "orders.return_policy", "Chính sách đổi trả", group=GROUP,
    default=(
        "Đổi trả trong 7 ngày kể từ khi nhận. Hàng lỗi, giao sai, vỡ khi giao, khác mô tả: shop chịu phí hai chiều, "
        "hoàn đủ tiền món hoặc đổi món mới. Đổi ý: món còn nguyên, khách chịu phí gửi trả, hoàn tiền món trừ phí giao lượt đi."
    ),
)  # fmt: skip
control.register_setting("orders.notify_enabled", "Tự báo tin mốc đơn cho khách", True, group=GROUP)
control.register_setting(
    "orders.notify_channel",
    "Kênh báo tin cho khách",
    Channel.ZALO_OA.value,
    group=GROUP,
    description="zalo_oa (Zalo theo số điện thoại) · sms · email",
)
control.register_setting(
    "orders.notify_fallback_channels",
    "Kênh dự phòng khi báo tin không được",
    [],
    group=GROUP,
    description='Thử lần lượt khi kênh chính gửi lỗi, vd ["email"] (chỉ khi khách có email).',
)
control.register_setting(
    "orders.notify_templates",
    "Mẫu tin báo khách",
    {},
    group=GROUP,
    description="Chỉ lưu mẫu chị đã sửa; mẫu để trống dùng câu mặc định.",
)
control.register_setting(
    "orders.shipping_carriers",
    "Hãng giao đang bật",
    None,
    group=GROUP,
    description=f'Danh sách driver, vd ["ghn", "ghtk"]. Bỏ trống = {settings.shipping_driver}.',
)
control.register_setting(
    "orders.shipping_day_value_vnd",
    "Một ngày giao nhanh hơn đáng bao nhiêu (VND)",
    5000,
    group=GROUP,
    description="Dùng khi so hãng: điểm = phí + số ngày giao × giá trị này.",
)
control.register_setting("orders.default_weight_grams", "Cân nặng mặc định mỗi món (gram)", 500, group=GROUP)
control.register_setting("orders.low_stock_default_threshold", "Ngưỡng báo sắp hết (cái)", 3, group=GROUP)


# ---- «Hôm nay» -----------------------------------------------------------------------------------------------------


@control.stat_provider("orders.today", order=10)
async def _stats(db: AsyncSession) -> list[control.Stat]:
    start, end = local_day_bounds_utc()
    new = await db.scalar(
        select(func.count()).where(
            Order.placed_at >= start,
            Order.placed_at < end,
            Order.status.not_in((OrderStatus.DRAFT, OrderStatus.CANCELLED)),
        )
    )
    cash = await db.scalar(
        select(func.coalesce(func.sum(Payment.amount_vnd), 0)).where(
            Payment.direction == PaymentDirection.IN, Payment.status == PaymentStatus.MATCHED,
            Payment.received_at >= start, Payment.received_at < end,
        )
    )  # fmt: skip
    waiting = await db.scalar(select(func.count()).where(Order.status == OrderStatus.PENDING_PAYMENT))
    to_ship = await db.scalar(select(func.count()).where(Order.status == OrderStatus.READY_TO_SHIP))
    return [
        control.Stat(key="orders.new_today", label="Đơn mới hôm nay", value=int(new or 0), href="/desk/don-hang", order=11),
        control.Stat(key="orders.cash_today", label="Tiền về hôm nay", value=int(cash or 0), format="vnd", href="/desk/don-hang/van-hanh", order=12),
        control.Stat(key="orders.waiting_payment", label="Đơn chờ chuyển khoản", value=int(waiting or 0), href="/desk/don-hang?nhom=cho_thanh_toan", order=13),
        control.Stat(key="orders.to_ship", label="Đơn chờ giao", value=int(to_ship or 0), href="/desk/don-hang?nhom=cho_giao", order=14),
    ]  # fmt: skip


# ---- lệnh bằng lời (i6) --------------------------------------------------------------------------------------------


class OrdersSummaryParams(BaseModel):
    scope: Literal["today", "to_ship", "waiting_payment"] | None = Field(
        default=None,
        description="today = đơn mới hôm nay · to_ship = đơn chờ giao · waiting_payment = đơn chờ chuyển khoản",
    )


_SCOPES = {
    "today": ("Đơn mới hôm nay", "/desk/don-hang?nhom=tat_ca"),
    "to_ship": ("Đơn chờ giao", "/desk/don-hang?nhom=cho_giao"),
    "waiting_payment": ("Đơn chờ chuyển khoản", "/desk/don-hang?nhom=cho_thanh_toan"),
}


def _scope_from_text(text: str) -> str:
    t = unidecode(text).lower()
    if "giao" in t or "gui di" in t or "ship" in t:
        return "to_ship"
    if "chuyen khoan" in t or "chua tra" in t or "thanh toan" in t:
        return "waiting_payment"
    return "today"


@control.intent(
    "orders.summary",
    "Tóm tắt đơn hàng",
    "Đọc nhanh đơn mới hôm nay, đơn chờ giao hoặc đơn chờ chuyển khoản: số đơn, tổng tiền, vài đơn đầu.",
    params=OrdersSummaryParams,
    examples=["tóm tắt đơn hôm nay", "còn bao nhiêu đơn chờ giao", "đơn nào chưa chuyển khoản"],
)
async def _orders_summary(ctx: control.CommandContext, params: OrdersSummaryParams | None) -> control.CommandResult:
    scope = (params.scope if params else None) or _scope_from_text(ctx.text)
    q = select(Order).where(Order.status.not_in((OrderStatus.DRAFT, OrderStatus.CANCELLED)))
    if scope == "today":
        start, end = local_day_bounds_utc()
        q = q.where(Order.placed_at >= start, Order.placed_at < end)
    elif scope == "to_ship":
        q = q.where(Order.status == OrderStatus.READY_TO_SHIP)
    else:
        q = q.where(Order.status == OrderStatus.PENDING_PAYMENT)
    rows = list((await ctx.db.execute(q.order_by(Order.placed_at.desc()))).scalars())
    label, href = _SCOPES[scope]
    if not rows:
        return control.CommandResult(message=f"{label}: chưa có đơn nào.", href=href, data={"scope": scope, "count": 0})
    total = sum(o.total_vnd for o in rows)
    head = "; ".join(f"{o.code} {o.recipient_name} {notify.vnd(o.total_vnd)}" for o in rows[:5])
    more = f" và {len(rows) - 5} đơn nữa" if len(rows) > 5 else ""
    return control.CommandResult(
        message=f"{label}: {len(rows)} đơn, tổng {notify.vnd(total)}. {head}{more}.",
        href=href,
        data={"scope": scope, "count": len(rows), "total_vnd": total, "codes": [o.code for o in rows[:5]]},
    )
