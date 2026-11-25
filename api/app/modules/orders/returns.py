"""Đổi trả, hoàn tiền (g7): khách hoặc chị mở yêu cầu → AI kiểm điều kiện, soạn 1–2 phương án → việc khoá
«Luôn hỏi chị» (`orders.decide_return`). Hoàn tiền phát `order.refunded`."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core import events
from app.core.enums import Actor
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.timeutil import now_utc
from app.modules.orders import notify, service
from app.modules.orders.ai_tasks import AssessReturnIn, AssessReturnOut, ReturnLine, ReturnOption, _fake_assess
from app.modules.orders.models import (
    Order,
    OrderStatus,
    Payment,
    PaymentDirection,
    PaymentStatus,
    Return,
    ReturnKind,
    ReturnReason,
    ReturnStatus,
)
from app.modules.orders.notify import vnd
from app.modules.orders.util import RETURN_CODE_PREFIX, new_code

log = logging.getLogger("app.orders.returns")

DECIDE_ACTION = "orders.decide_return"

REASON_LABELS = {
    ReturnReason.DEFECT: "Hàng lỗi",
    ReturnReason.WRONG_ITEM: "Giao sai món",
    ReturnReason.DAMAGED_IN_SHIPPING: "Vỡ, hỏng khi giao",
    ReturnReason.NOT_AS_DESCRIBED: "Khác mô tả",
    ReturnReason.CHANGED_MIND: "Đổi ý",
    ReturnReason.OTHER: "Lý do khác",
}
KIND_LABELS = {
    ReturnKind.RETURN: "Trả hàng, hoàn tiền",
    ReturnKind.EXCHANGE: "Đổi món",
    ReturnKind.REFUND_ONLY: "Chỉ hoàn tiền",
}
OPEN_STATUSES = (
    ReturnStatus.REQUESTED,
    ReturnStatus.PENDING_DECISION,
    ReturnStatus.APPROVED,
    ReturnStatus.AWAITING_ITEM,
    ReturnStatus.RECEIVED,
)


def refundable(order: Order) -> int:
    return max(0, order.paid_vnd - order.refunded_vnd)


async def _unique_code(db: AsyncSession) -> str:
    for _ in range(30):
        code = new_code(RETURN_CODE_PREFIX)
        if not await db.scalar(select(func.count()).where(Return.code == code)):
            return code
    raise Conflict("Không tạo được mã đổi trả, thử lại.")


async def open_return(
    db: AsyncSession,
    order: Order,
    *,
    kind: str | ReturnKind,
    reason: str | ReturnReason,
    description: str | None,
    quantity: int = 1,
    order_item_id: uuid.UUID | None = None,
    actor: Actor = Actor.CUSTOMER,
    user: Any = None,
    refund_all: bool = False,
    refund_amount: int | None = None,
) -> Return:
    kind, reason = ReturnKind(kind), ReturnReason(reason)
    if order.status == OrderStatus.DRAFT:
        raise Conflict("Đơn nháp chưa đổi trả được.")
    if kind != ReturnKind.REFUND_ONLY and order.status not in (OrderStatus.DELIVERED, OrderStatus.COMPLETED):
        raise Conflict("Đơn chưa giao xong, chưa đổi trả được. Bạn hỏi mình về đơn này nhé.", code="not_delivered")
    open_count = await db.scalar(
        select(func.count()).where(Return.order_id == order.id, Return.status.in_(OPEN_STATUSES))
    )
    if open_count and actor == Actor.CUSTOMER:
        raise Conflict("Đơn này đang có một yêu cầu đổi trả, mình đang xem.", code="return_open")
    if order_item_id and not any(i.id == order_item_id for i in order.items):
        raise BadRequest("Dòng hàng không thuộc đơn này.")
    r = Return(
        code=await _unique_code(db), order_id=order.id, order_item_id=order_item_id, customer_id=order.customer_id,
        kind=kind, reason=reason, description=description, quantity=quantity, status=ReturnStatus.REQUESTED,
    )  # fmt: skip
    db.add(r)
    await db.flush()
    service.add_event(
        db, order, "return_requested", f"Đã nhận yêu cầu {KIND_LABELS[kind].lower()} {r.code}",
        detail=REASON_LABELS[reason], actor=actor, data={"return_id": str(r.id)},
    )  # fmt: skip
    forced = refundable(order) if refund_all else refund_amount
    await assess_and_propose(db, r, order, forced_amount=forced)
    return r


async def assess_and_propose(
    db: AsyncSession, r: Return, order: Order, *, note: str | None = None, forced_amount: int | None = None
) -> None:
    window = int(await control.get_setting(db, "orders.return_window_days") or 7)
    policy = str(await control.get_setting(db, "orders.return_policy") or "")
    item = next((i for i in order.items if i.id == r.order_item_id), None)
    days = (now_utc() - order.delivered_at).days if order.delivered_at else None
    desc = r.description or ""
    if note:
        desc += f"\n[Chị dặn khi trả lại phương án trước: {note}]"
    inp = AssessReturnIn(
        order_code=order.code, kind=r.kind.value, reason=r.reason.value, description=desc or None,
        items=[ReturnLine(name=i.name, quantity=i.quantity, unit_price_vnd=i.unit_price_vnd) for i in order.items],
        requested_item=item.name if item else None, quantity=r.quantity,
        delivered=order.delivered_at is not None, days_since_delivery=days, return_window_days=window, policy=policy,
        paid_vnd=order.paid_vnd, refunded_vnd=order.refunded_vnd, shipping_fee_vnd=order.shipping_fee_vnd,
        max_refund_vnd=refundable(order),
    )  # fmt: skip
    run_id = None
    try:
        res = await ai.run("orders.assess_return", inp, AssessReturnOut, tier="smart")
        out, run_id, by_ai = res.output, res.run_id, True
    except ai.AIError as e:  # chạm trần / mất mạng: vẫn có phương án theo quy tắc để chị quyết
        log.warning("AI kiểm đổi trả lỗi (%s), dùng quy tắc", e)
        out, by_ai = _fake_assess(inp), False
    cap = refundable(order)
    options = [o.model_copy(update={"refund_amount_vnd": min(o.refund_amount_vnd, cap)}) for o in out.options][:2]
    if forced_amount is not None:
        amt = min(forced_amount, cap)
        options = [
            ReturnOption(
                title=f"Hoàn {vnd(amt)} cho khách",
                kind="refund_only",
                refund_amount_vnd=amt,
                description=desc or "Hoàn tiền cho khách.",
            )
        ]
    first = options[0]
    r.eligibility = {
        "eligible": out.eligible, "checks": [c.model_dump() for c in out.checks],
        "options": [o.model_dump() for o in options], "summary": out.summary, "by_ai": by_ai,
        "customer_message": out.customer_message,
    }  # fmt: skip
    r.proposal = f"{first.title}. {first.description}"
    r.refund_amount_vnd = first.refund_amount_vnd
    r.status = ReturnStatus.PENDING_DECISION
    await db.flush()
    outcome = await control.propose(
        DECIDE_ACTION,
        f"{KIND_LABELS[r.kind]} {r.code} · đơn {order.code}",
        {"return_id": str(r.id), "option": 0, "decision": "reject" if first.kind == "reject" else "approve",
         "refund_amount_vnd": first.refund_amount_vnd, "customer_message": out.customer_message},
        {"order_code": order.code, "recipient": order.recipient_name, "reason": REASON_LABELS[r.reason],
         "description": r.description, "checks": r.eligibility["checks"], "options": r.eligibility["options"],
         "customer_message": out.customer_message, "refundable_vnd": cap},
        db=db, summary=out.summary, rationale="; ".join(f"{c.label}: {c.note}" for c in out.checks),
        ref_type="returns", ref_id=r.id, ai_run_id=run_id, dedupe_key=f"return:{r.id}", priority=8,
        ai_generated=by_ai,
    )  # fmt: skip
    r.approval_item_id = outcome.item_id


async def decide(db: AsyncSession, payload: dict[str, Any], *, user: Any = None) -> str:
    """Handler của orders.decide_return (chỉ chạy sau khi chị duyệt — hành động khoá)."""
    r = await db.get(Return, uuid.UUID(payload["return_id"]))
    if r is None:
        raise NotFound("Không thấy yêu cầu đổi trả.")
    if r.status != ReturnStatus.PENDING_DECISION:
        raise Conflict("Yêu cầu này đã được quyết rồi.")
    order = await service.get_order(db, r.order_id, lock=True)
    options = r.eligibility.get("options") or []
    idx = int(payload.get("option") or 0)
    option = (
        options[idx] if 0 <= idx < len(options) else (options[0] if options else {"kind": "reject", "title": "Từ chối"})
    )
    r.decided_at = now_utc()
    r.decided_by_id = getattr(user, "id", None)
    r.decision_note = payload.get("note") or payload.get("customer_message")
    message = payload.get("customer_message") or ""
    if payload.get("decision") == "reject" or option.get("kind") == "reject":
        r.status = ReturnStatus.REJECTED
        r.closed_at = now_utc()
        service.add_event(
            db, order, "return_rejected", f"Yêu cầu {r.code}: mình chưa nhận đổi trả", detail=message or None
        )
        await notify.notify_order(
            db,
            order,
            "return_update",
            {"ma_doi_tra": r.code, "ket_qua": message or "mình chưa nhận đổi trả lần này."},
            dedupe=f"{r.id}:rejected",
        )
        return f"Từ chối {r.code}"
    amount = min(int(payload.get("refund_amount_vnd", option.get("refund_amount_vnd", 0)) or 0), refundable(order))
    r.refund_amount_vnd = amount
    kind = option.get("kind") or r.kind.value
    if kind == "refund_only":
        await do_refund(db, r, order, amount, user=user)
        r.status = ReturnStatus.REFUNDED
        r.closed_at = now_utc()
        result = f"đã hoàn {vnd(amount)}."
    else:
        r.kind = ReturnKind(kind)
        r.status = ReturnStatus.AWAITING_ITEM
        result = option.get("title", "") + (". " + message if message else "")
    service.add_event(db, order, "return_approved", f"Yêu cầu {r.code}: {option.get('title', 'đã duyệt')}")
    await notify.notify_order(
        db, order, "return_update", {"ma_doi_tra": r.code, "ket_qua": result}, dedupe=f"{r.id}:approved"
    )
    return f"Duyệt {r.code}: {option.get('title', '')}"


async def do_refund(
    db: AsyncSession, r: Return | None, order: Order, amount: int, *, user: Any = None
) -> Payment | None:
    if amount <= 0:
        return None
    if amount > refundable(order):
        raise BadRequest(f"Chỉ còn hoàn được {vnd(refundable(order))}.")
    src = (
        await db.execute(
            select(Payment)
            .where(Payment.order_id == order.id, Payment.direction == PaymentDirection.IN)
            .order_by(Payment.received_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    p = Payment(
        order_id=order.id, direction=PaymentDirection.OUT, method=src.method if src else order.payment_method,
        provider="manual", status=PaymentStatus.REFUNDED, amount_vnd=amount, received_at=now_utc(),
        refund_of_id=src.id if src else None, return_id=r.id if r else None,
        note="Chị chuyển hoàn cho khách" + (f" ({r.code})" if r else ""),
    )  # fmt: skip
    db.add(p)
    order.refunded_vnd += amount
    service.recompute_payment_state(order)
    service.add_event(db, order, "refunded", f"Đã hoàn {vnd(amount)}", actor=Actor.OWNER if user else Actor.SYSTEM)
    await db.flush()
    await events.emit("order.refunded", {"order_id": str(order.id), "amount_vnd": amount}, db=db)
    return p


async def mark_received(db: AsyncSession, r: Return, *, user: Any = None) -> Return:
    if r.status != ReturnStatus.AWAITING_ITEM:
        raise Conflict("Yêu cầu này không ở bước chờ nhận hàng trả.")
    order = await service.get_order(db, r.order_id, lock=True)
    r.status = ReturnStatus.RECEIVED
    service.add_event(db, order, "return_received", f"Mình đã nhận lại hàng ({r.code})")
    if r.kind == ReturnKind.EXCHANGE:
        r.status = ReturnStatus.EXCHANGED
        result = "mình đã nhận lại món cũ và sẽ gửi món mới cho bạn."
    else:
        await do_refund(db, r, order, min(r.refund_amount_vnd, refundable(order)), user=user)
        r.status = ReturnStatus.REFUNDED
        result = f"mình đã nhận lại hàng và hoàn {vnd(r.refund_amount_vnd)}."
        if order.refunded_vnd >= order.paid_vnd and order.status in (OrderStatus.DELIVERED, OrderStatus.COMPLETED):
            service.set_status(db, order, OrderStatus.RETURNED, "Đơn đã trả lại và hoàn tiền")
    r.closed_at = now_utc()
    await notify.notify_order(
        db, order, "return_update", {"ma_doi_tra": r.code, "ket_qua": result}, dedupe=f"{r.id}:done"
    )
    await db.flush()
    return r


async def redo_after_return(db: AsyncSession, item_ref_id: uuid.UUID | None, note: str) -> None:
    """Chị trả lại phương án kèm lời nhắn → AI soạn lại theo lời nhắn."""
    if item_ref_id is None:
        return
    r = await db.get(Return, item_ref_id)
    if r is None or r.status != ReturnStatus.PENDING_DECISION:
        return
    order = await service.get_order(db, r.order_id)
    await assess_and_propose(db, r, order, note=note)
