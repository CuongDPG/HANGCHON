"""Khớp thanh toán (g2): nhận khoản chuyển tới từ tích hợp `payments` → khớp theo mã đơn trong nội dung + số tiền.
Chuyển thiếu / thừa / sai nội dung / vào đơn đã huỷ → khoản tiền `needs_review` + việc chờ chị.
Đơn chờ quá hạn: nhắc khách rồi tự huỷ (trả suất) theo cài đặt."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.enums import Actor
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.timeutil import now_utc
from app.integrations.payments import IncomingTransfer
from app.modules.orders import notify, service
from app.modules.orders.models import (
    MatchMethod,
    Order,
    OrderStatus,
    Payment,
    PaymentDirection,
    PaymentMethod,
    PaymentStatus,
)
from app.modules.orders.notify import vnd
from app.modules.orders.util import find_codes_in_transfer, normalize_order_code

log = logging.getLogger("app.orders.payments")

REVIEW_ACTION = "orders.review_payment"


async def ingest_transfers(db: AsyncSession, provider: str, transfers: list[IncomingTransfer]) -> list[Payment]:
    """Lưu từng khoản chuyển tới (không trùng theo mã giao dịch) rồi khớp đơn. Gọi lặp an toàn."""
    out: list[Payment] = []
    for t in transfers:
        if t.amount_vnd <= 0:
            continue
        exists = await db.scalar(
            select(func.count()).where(Payment.provider == provider, Payment.external_id == t.external_id)
        )
        if exists:
            continue
        p = Payment(
            direction=PaymentDirection.IN,
            method=PaymentMethod.BANK_TRANSFER,
            provider=provider,
            external_id=t.external_id,
            amount_vnd=t.amount_vnd,
            content=t.content,
            payer_name=t.payer_name,
            payer_account=t.payer_account,
            received_at=t.received_at,
            raw=t.raw or {},
        )
        try:
            async with db.begin_nested():
                db.add(p)
                await db.flush()
        except IntegrityError:  # webhook và đối soát tới cùng lúc
            continue
        await match_payment(db, p)
        out.append(p)
    return out


async def match_payment(db: AsyncSession, p: Payment) -> None:
    codes = find_codes_in_transfer(p.content)
    orders = [o for o in [await service.get_by_code(db, c, lock=True) for c in codes] if o is not None]
    if len(orders) == 1:
        await apply_to_order(db, orders[0], p, method=MatchMethod.AUTO_CODE, confidence=Decimal("0.99"))
        return
    p.status = PaymentStatus.NEEDS_REVIEW
    await db.flush()
    if len(orders) > 1:
        await propose_review(
            db, p, "ambiguous", f"Nội dung chuyển khoản có nhiều mã đơn: {', '.join(o.code for o in orders)}.",
            decision="match", order=orders[0],
        )  # fmt: skip
        return
    # sai nội dung: gợi ý đơn đang chờ đúng số tiền (gần đây), chị xác nhận
    since = now_utc() - timedelta(days=7)
    waiting = list(
        (
            await db.execute(
                select(Order).where(
                    Order.status == OrderStatus.PENDING_PAYMENT,
                    Order.payment_method == PaymentMethod.BANK_TRANSFER,
                    Order.placed_at >= since,
                )
            )
        ).scalars()
    )
    same = [o for o in waiting if service.amount_due(o) == p.amount_vnd]
    if len(same) == 1:
        o = same[0]
        await propose_review(
            db, p, "unmatched",
            f"Nội dung «{p.content or ''}» không có mã đơn. Đúng số tiền của đơn {o.code} ({o.recipient_name}) — "
            "chị xác nhận đây là tiền của đơn này?",
            decision="match", order=o,
        )  # fmt: skip
    else:
        hint = f" Có {len(same)} đơn cùng số tiền." if same else ""
        await propose_review(
            db, p, "unmatched", f"Nội dung «{p.content or ''}» không có mã đơn nào.{hint} Chị ghi mã đơn để khớp, hoặc bỏ qua.",
            decision="ignore",
        )  # fmt: skip


async def apply_to_order(
    db: AsyncSession,
    order: Order,
    p: Payment,
    *,
    method: MatchMethod,
    confidence: Decimal | None = None,
    actor: Actor = Actor.SYSTEM,
    accept_underpaid: bool = False,
) -> None:
    p.order_id = order.id
    p.matched_at = now_utc()
    p.match_method = method
    p.match_confidence = confidence
    if order.status == OrderStatus.CANCELLED:
        p.status = PaymentStatus.NEEDS_REVIEW
        await db.flush()
        await propose_review(
            db, p, "cancelled_order",
            f"Khách chuyển {vnd(p.amount_vnd)} cho đơn {order.code} nhưng đơn đã huỷ ({order.cancel_reason or 'không rõ lý do'}). "
            "Mở lại đơn nếu còn suất, hoặc hoàn tiền.",
            decision="reopen", order=order,
        )  # fmt: skip
        return
    if order.status == OrderStatus.DRAFT:
        p.status = PaymentStatus.NEEDS_REVIEW
        await db.flush()
        await propose_review(db, p, "unmatched", f"Đơn {order.code} còn là đơn nháp.", decision="ignore", order=order)
        return
    order.paid_vnd += p.amount_vnd
    service.recompute_payment_state(order)
    service.add_event(
        db, order, "payment_received", f"Đã nhận {vnd(p.amount_vnd)}",
        detail=f"Nội dung: {p.content}" if p.content else None, actor=actor, data={"payment_id": str(p.id)},
    )  # fmt: skip
    await db.flush()
    full = order.paid_vnd >= order.total_vnd
    deposit_ok = bool(order.deposit_required_vnd) and order.paid_vnd >= order.deposit_required_vnd
    if full or deposit_ok or accept_underpaid:
        p.status = PaymentStatus.MATCHED
        if not full and order.payment_method == PaymentMethod.BANK_TRANSFER:
            # cọc đủ / chị nhận thiếu: phần còn lại thu khi giao
            order.cod_amount_vnd = max(0, order.total_vnd - order.paid_vnd) if deposit_ok else 0
        elif full:
            order.cod_amount_vnd = 0
        await service.mark_paid(db, order, p, actor=actor)
        await notify.notify_order(
            db, order, "payment_confirmed", {"so_tien": vnd(p.amount_vnd)}, dedupe=str(p.id),
            drop_arrival=await service.arrival_text(db, order),
        )  # fmt: skip
        if order.paid_vnd > order.total_vnd:
            await propose_review(
                db, p, "overpaid",
                f"Đơn {order.code} tổng {vnd(order.total_vnd)}, khách đã chuyển {vnd(order.paid_vnd)} "
                f"(thừa {vnd(order.paid_vnd - order.total_vnd)}). Chị chọn hoàn phần thừa hay giữ lại trừ đơn sau.",
                decision="keep", order=order, status=PaymentStatus.MATCHED,
            )  # fmt: skip
    else:
        p.status = PaymentStatus.NEEDS_REVIEW
        await db.flush()
        need = service.amount_due(order)
        await propose_review(
            db, p, "underpaid",
            f"Đơn {order.code} còn thiếu {vnd(need)} (khách chuyển {vnd(p.amount_vnd)}). "
            "Chờ khách chuyển thêm, hoặc chị nhận đủ luôn.",
            decision="wait", order=order,
        )  # fmt: skip
    await db.flush()


async def propose_review(
    db: AsyncSession,
    p: Payment,
    kind: str,
    summary: str,
    *,
    decision: str,
    order: Order | None = None,
    status: PaymentStatus | None = None,
) -> None:
    if status is not None:
        p.status = status
    titles = {
        "unmatched": "Khoản tiền chưa khớp đơn",
        "ambiguous": "Khoản tiền có nhiều mã đơn",
        "underpaid": "Khách chuyển thiếu",
        "overpaid": "Khách chuyển thừa",
        "cancelled_order": "Tiền vào đơn đã huỷ",
        "overdue_partial": "Đơn quá hạn nhưng đã chuyển một phần",
    }
    await control.propose(
        REVIEW_ACTION,
        f"{titles.get(kind, 'Khoản tiền cần xem')}: {vnd(p.amount_vnd)}" + (f" · {order.code}" if order else ""),
        {"payment_id": str(p.id), "kind": kind, "decision": decision, "order_code": order.code if order else None},
        {
            "amount_vnd": p.amount_vnd,
            "content": p.content,
            "payer_name": p.payer_name,
            "received_at": p.received_at.isoformat(),
            "order_code": order.code if order else None,
            "order_total_vnd": order.total_vnd if order else None,
            "order_paid_vnd": order.paid_vnd if order else None,
            "decisions": DECISIONS[kind],
        },
        db=db,
        summary=summary,
        ref_type="payments",
        ref_id=p.id,
        dedupe_key=f"payment:{p.id}",
        priority=5,
        ai_generated=False,
    )


DECISIONS: dict[str, dict[str, str]] = {
    "unmatched": {"match": "Khớp vào đơn (ghi mã đơn)", "ignore": "Không phải tiền đơn hàng"},
    "ambiguous": {"match": "Khớp vào đơn (ghi mã đơn)", "ignore": "Không phải tiền đơn hàng"},
    "underpaid": {"wait": "Chờ khách chuyển thêm", "accept": "Nhận đủ luôn, xác nhận đơn"},
    "overpaid": {"keep": "Giữ lại, ghi chú cho đơn sau", "refund": "Hoàn phần thừa cho khách"},
    "cancelled_order": {"reopen": "Mở lại đơn (nếu còn suất)", "refund": "Hoàn tiền cho khách"},
    "overdue_partial": {"wait": "Gia hạn thêm, chờ khách", "accept": "Nhận đủ luôn, xác nhận đơn"},
}


async def resolve_review(db: AsyncSession, payload: dict[str, Any], *, user: Any = None) -> str:
    """Thực thi quyết định của chị cho một khoản tiền (handler của orders.review_payment). Trả câu tóm tắt."""
    p = await db.get(Payment, uuid.UUID(payload["payment_id"]))
    if p is None:
        raise NotFound("Không thấy khoản tiền.")
    decision = payload.get("decision")
    kind = payload.get("kind")
    order = None
    if payload.get("order_code"):
        order = await service.get_by_code(db, normalize_order_code(payload["order_code"]), lock=True)
    actor = Actor.OWNER if user else Actor.AI
    if decision == "ignore":
        p.status = PaymentStatus.IGNORED
        p.note = "Chị xác nhận không phải tiền đơn hàng"
        return f"Bỏ qua khoản {vnd(p.amount_vnd)}"
    if decision == "match":
        if order is None:
            raise BadRequest("Chị ghi mã đơn cần khớp (vd HC-48213).")
        if p.order_id and p.order_id != order.id:
            raise Conflict("Khoản tiền này đã khớp đơn khác.")
        await apply_to_order(db, order, p, method=MatchMethod.MANUAL, confidence=Decimal("1"), actor=actor)
        return f"Khớp {vnd(p.amount_vnd)} vào đơn {order.code}"
    if order is None:
        order = await db.get(Order, p.order_id) if p.order_id else None
    if order is None:
        raise BadRequest("Khoản tiền chưa gắn đơn nào.")
    if decision == "wait":
        p.status = PaymentStatus.MATCHED
        if kind == "overdue_partial" and order.payment_due_at:
            order.payment_due_at = now_utc() + timedelta(hours=24)
        return f"Chờ khách chuyển thêm cho đơn {order.code}"
    if decision == "accept":
        p.status = PaymentStatus.MATCHED
        order.raw = {**order.raw, "accepted_underpaid_by_owner": True}
        await service.mark_paid(db, order, p, actor=actor)
        return f"Nhận đủ, xác nhận đơn {order.code}"
    if decision == "keep":
        p.status = PaymentStatus.MATCHED
        order.internal_note = (
            (order.internal_note or "") + f"\nKhách chuyển thừa {vnd(order.paid_vnd - order.total_vnd)}."
        ).strip()
        return f"Giữ phần thừa của đơn {order.code}"
    if decision == "refund":
        from app.modules.orders import returns as ret_svc

        amount = order.paid_vnd - order.total_vnd if kind == "overpaid" else p.amount_vnd
        p.status = PaymentStatus.MATCHED
        await ret_svc.open_return(
            db, order, kind="refund_only", reason="other", description=f"Hoàn tiền {DECISIONS[kind]['refund'].lower()}",
            quantity=1, actor=actor, user=user, refund_amount=amount,
        )  # fmt: skip
        return f"Mở yêu cầu hoàn {vnd(amount)} cho đơn {order.code}"
    if decision == "reopen":
        if order.status != OrderStatus.CANCELLED:
            raise Conflict("Đơn không ở trạng thái huỷ.")
        lines = await service.lines_of(db, order)
        resolved = await service.resolve_lines(
            db, lines, service.ResolveOptions(store=False, lock=True, exclude_order_id=order.id)
        )
        problems = [f"{r.name}: {r.problem}" for r in resolved if r.problem]
        if problems:
            raise Conflict("Không mở lại được: " + " ".join(problems) + " Chị chọn hoàn tiền.", code="unavailable")
        order.cancelled_at = None
        order.cancel_reason = None
        service.set_status(db, order, OrderStatus.PENDING_PAYMENT, "Đơn được mở lại", actor=actor)
        await apply_to_order(
            db, order, p, method=p.match_method or MatchMethod.MANUAL, actor=actor, accept_underpaid=True
        )
        return f"Mở lại đơn {order.code}"
    raise BadRequest(f"Không hiểu quyết định «{decision}».")


async def record_manual(
    db: AsyncSession, order: Order, amount_vnd: int, method: PaymentMethod, *, note: str | None = None, user: Any = None
) -> Payment:
    if order.status in (OrderStatus.CANCELLED, OrderStatus.DRAFT):
        raise Conflict("Đơn đã huỷ hoặc còn là nháp, không ghi nhận tiền được.")
    p = Payment(
        direction=PaymentDirection.IN, method=method, provider="manual", amount_vnd=amount_vnd,
        received_at=now_utc(), note=note,
    )  # fmt: skip
    db.add(p)
    await db.flush()
    await apply_to_order(
        db, order, p, method=MatchMethod.MANUAL, confidence=Decimal("1"), actor=Actor.OWNER if user else Actor.SYSTEM
    )
    return p


async def record_cod(db: AsyncSession, order: Order) -> Payment | None:
    """Hãng giao đã thu tiền khi giao (COD): ghi khoản đối soát và coi đơn đã trả."""
    if order.cod_amount_vnd <= 0:
        return None
    ext = f"cod:{order.id}"
    if await db.scalar(select(func.count()).where(Payment.provider == "cod", Payment.external_id == ext)):
        return None
    p = Payment(
        direction=PaymentDirection.IN, method=PaymentMethod.COD, provider="cod", external_id=ext,
        status=PaymentStatus.MATCHED, amount_vnd=order.cod_amount_vnd, received_at=now_utc(), order_id=order.id,
        matched_at=now_utc(), match_method=MatchMethod.COD_SETTLEMENT, match_confidence=Decimal("1"),
    )  # fmt: skip
    db.add(p)
    order.paid_vnd += p.amount_vnd
    service.recompute_payment_state(order)
    service.add_event(db, order, "payment_received", f"Đã thu {vnd(p.amount_vnd)} khi giao", visible=False)
    await db.flush()
    await service.mark_paid(db, order, p)
    return p


async def expire_unpaid(db: AsyncSession) -> dict[str, int]:
    """Đơn chuyển khoản quá giờ chưa trả: nhắc một lần, quá hạn thì huỷ (trả suất) hoặc hỏi chị nếu đã trả một phần."""
    reminder_h = float(await control.get_setting(db, "orders.payment_reminder_hours") or 6)
    auto_cancel = await control.get_setting(db, "orders.auto_cancel_unpaid")
    now = now_utc()
    stats = {"reminded": 0, "cancelled": 0, "review": 0}
    rows = list(
        (
            await db.execute(
                select(Order).where(
                    Order.status == OrderStatus.PENDING_PAYMENT, Order.payment_method == PaymentMethod.BANK_TRANSFER
                )
            )
        ).scalars()
    )
    for o in rows:
        due = o.payment_due_at
        if due and now >= due:
            if o.paid_vnd > 0:
                last = (
                    await db.execute(
                        select(Payment).where(Payment.order_id == o.id).order_by(Payment.received_at.desc()).limit(1)
                    )
                ).scalar_one()
                await propose_review(
                    db, last, "overdue_partial",
                    f"Đơn {o.code} quá hạn, khách mới chuyển {vnd(o.paid_vnd)}/{vnd(o.total_vnd)}.",
                    decision="wait", order=o, status=last.status,
                )  # fmt: skip
                stats["review"] += 1
            elif auto_cancel is not False:
                await service.cancel_order(db, o, "Quá hạn chuyển khoản, suất đã được trả lại", actor=Actor.SYSTEM)
                stats["cancelled"] += 1
        elif o.paid_vnd == 0 and now >= o.placed_at + timedelta(hours=reminder_h):
            if not await notify.already_sent(db, o, "payment_reminder"):
                await notify.notify_order(db, o, "payment_reminder")
                stats["reminded"] += 1
    await db.flush()
    return stats
