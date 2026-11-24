"""Chốt đơn từ tin nhắn (g6): nghe `message.received` (đọc bảng inbox, chỉ đọc) → AI nhận ra ý định mua, rút món,
số lượng, người nhận, địa chỉ → tạo/cập nhật **đơn nháp** của hội thoại → đề xuất `orders.confirm_draft`
(mặc định hỏi chị). Thiếu thông tin thì ghi rõ thiếu gì; chị điền nốt rồi duyệt."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core.enums import Actor, Channel
from app.core.errors import BadRequest
from app.core.timeutil import now_utc
from app.modules.catalog.models import Drop, DropItem, DropStatus, Product, ProductStatus, SaleMode
from app.modules.inbox.models import Direction, Message, Thread
from app.modules.orders import refs, service
from app.modules.orders.ai_tasks import CatalogEntry, ExtractPurchaseIn, ExtractPurchaseOut
from app.modules.orders.models import (
    CustomerIdentity,
    FulfillmentSource,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
)
from app.modules.orders.schemas import CartLineIn, DraftConfirmIn
from app.modules.orders.util import try_normalize_phone

log = logging.getLogger("app.orders.drafts")

CONFIRM_ACTION = "orders.confirm_draft"
MIN_CONFIDENCE = 0.5


async def catalog_for_ai(db: AsyncSession, limit: int = 60) -> list[CatalogEntry]:
    now = now_utc()
    out: list[CatalogEntry] = []
    drops = list((await db.execute(select(Drop).where(Drop.status == DropStatus.OPEN))).scalars())
    for d in drops:
        if d.closes_at and d.closes_at <= now:
            continue
        products = await refs.products_by_id(db, [di.product_id for di in d.items])
        for di in d.items:
            p = products.get(di.product_id)
            if p and p.status == ProductStatus.PUBLISHED:
                out.append(
                    CatalogEntry(
                        product_id=str(p.id),
                        name=p.name,
                        price_vnd=di.price_vnd or p.price_vnd,
                        drop_id=str(d.id),
                        drop_code=d.code,
                        variants=[v.name for v in p.variants if v.is_active],
                    )
                )
    seen = {e.product_id for e in out}
    stock = (
        await db.execute(
            select(Product).where(
                Product.status == ProductStatus.PUBLISHED, Product.sale_mode.in_((SaleMode.IN_STOCK, SaleMode.BOTH))
            )
        )
    ).scalars()
    for p in stock:
        if str(p.id) not in seen:
            out.append(
                CatalogEntry(
                    product_id=str(p.id),
                    name=p.name,
                    price_vnd=p.price_vnd,
                    variants=[v.name for v in p.variants if v.is_active],
                )
            )
    return out[:limit]


async def on_message(db: AsyncSession, thread_id: uuid.UUID, message_id: uuid.UUID) -> Order | None:
    msg = await db.get(Message, message_id)
    thread = await db.get(Thread, thread_id)
    if msg is None or thread is None or msg.thread_id != thread.id:
        return None
    if msg.direction != Direction.INBOUND or msg.sender != Actor.CUSTOMER or not (msg.body or "").strip():
        return None
    already = await db.scalar(
        select(Order.id).where(Order.thread_id == thread.id, Order.raw["source_message_ids"].contains([str(msg.id)]))
    )
    if already:
        return None  # sự kiện tới lặp
    draft = (
        await db.execute(
            select(Order)
            .where(Order.thread_id == thread.id, Order.status == OrderStatus.DRAFT)
            .order_by(Order.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    history_rows = list(
        (
            await db.execute(
                select(Message)
                .where(Message.thread_id == thread.id, Message.id != msg.id, Message.sent_at <= msg.sent_at)
                .order_by(Message.sent_at.desc())
                .limit(6)
            )
        ).scalars()
    )
    history = [f"{'Khách' if m.direction == Direction.INBOUND else 'Chị'}: {m.body}" for m in reversed(history_rows)]
    catalog = await catalog_for_ai(db)
    current = _draft_snapshot(draft) if draft else None
    try:
        res = await ai.run(
            "orders.extract_purchase",
            ExtractPurchaseIn(
                message=msg.body,
                history=history,
                customer_display_name=thread.participant_name,
                catalog=catalog,
                current_draft=current,
            ),
            ExtractPurchaseOut,
            tier="fast",
        )
    except ai.AIError as e:
        log.warning("AI rút đơn từ tin nhắn lỗi: %s", e)
        return None
    out = res.output
    has_info = any([out.phone, out.address_line, out.province, out.items])
    if draft is None and (not out.wants_to_buy or out.confidence < MIN_CONFIDENCE):
        return None
    if draft is not None and not out.wants_to_buy and not has_info:
        return None

    phone = try_normalize_phone(out.phone)
    if draft is None:
        draft = await service.new_draft(
            db, channel=thread.channel, recipient_name=out.recipient_name or thread.participant_name,
            recipient_phone=phone, payment_method=PaymentMethod(out.payment_method or "bank_transfer"),
            customer_note=out.note, ai_generated=True, thread_id=thread.id, raw={"source_message_ids": []},
        )  # fmt: skip
    else:
        draft.recipient_name = (out.recipient_name or draft.recipient_name)[:120]
        draft.recipient_phone = phone or draft.recipient_phone
        if out.payment_method:
            draft.payment_method = PaymentMethod(out.payment_method)
        if out.note:
            draft.customer_note = out.note
    for f in ("address_line", "ward", "district", "province"):
        if getattr(out, f):
            setattr(draft, f, getattr(out, f))
    by_id = {c.product_id: c for c in catalog}
    if out.items:
        draft.items.clear()
        await db.flush()
        for i, it in enumerate(out.items):
            entry = by_id.get(it.product_id or "")
            di_id = None
            if entry and entry.drop_id:
                di_id = await db.scalar(
                    select(DropItem.id).where(
                        DropItem.drop_id == uuid.UUID(entry.drop_id),
                        DropItem.product_id == uuid.UUID(entry.product_id),
                        DropItem.variant_id.is_(None),
                    )
                )
            draft.items.append(
                OrderItem(
                    position=i,
                    product_id=uuid.UUID(entry.product_id) if entry else None,
                    drop_item_id=di_id,
                    fulfillment_source=FulfillmentSource.DROP if di_id else FulfillmentSource.STOCK,
                    name=(entry.name if entry else it.name)[:300],
                    quantity=it.quantity,
                    unit_price_vnd=entry.price_vnd if entry else 0,
                    line_total_vnd=(entry.price_vnd if entry else 0) * it.quantity,
                )
            )
        draft.drop_id = next(
            (
                uuid.UUID(by_id[i.product_id].drop_id)
                for i in out.items
                if i.product_id in by_id and by_id[i.product_id].drop_id
            ),
            None,
        )  # type: ignore[arg-type]
    draft.subtotal_vnd = sum(i.line_total_vnd for i in draft.items)
    draft.total_vnd = draft.subtotal_vnd
    draft.raw = {
        **draft.raw,
        "source_message_ids": [*draft.raw.get("source_message_ids", []), str(msg.id)],
        "ai_run_id": str(res.run_id),
        "ai_missing": out.missing,
        "confidence": out.confidence,
    }
    await db.flush()
    if phone and thread.participant_external_id:
        await _link_identity(db, phone, draft, thread)
    await propose_confirm(db, draft, message=msg.body, ai_run_id=res.run_id)
    return draft


async def _link_identity(db: AsyncSession, phone: str, draft: Order, thread: Thread) -> None:
    customer = await service.upsert_customer(
        db, phone, draft.recipient_name if draft.recipient_name != "Chưa rõ" else None, thread.channel
    )
    draft.customer_id = customer.id
    exists = await db.scalar(
        select(CustomerIdentity.id).where(
            CustomerIdentity.channel == thread.channel, CustomerIdentity.external_id == thread.participant_external_id
        )
    )
    if not exists:
        db.add(
            CustomerIdentity(
                customer_id=customer.id,
                channel=thread.channel,
                external_id=thread.participant_external_id,
                display_name=thread.participant_name,
            )
        )
    await db.flush()


def _draft_snapshot(o: Order) -> dict[str, Any]:
    return {
        "recipient_name": o.recipient_name if o.recipient_name != "Chưa rõ" else None,
        "phone": o.recipient_phone or None,
        "address_line": o.address_line,
        "province": o.province,
        "payment_method": o.payment_method.value,
        "items": [{"name": i.name, "quantity": i.quantity} for i in o.items],
    }


def draft_missing(o: Order) -> list[str]:
    return service.missing_info(o)


async def propose_confirm(
    db: AsyncSession, draft: Order, *, message: str | None = None, ai_run_id: uuid.UUID | None = None
) -> None:
    missing = draft_missing(draft)
    channel_names = {
        Channel.FACEBOOK: "Facebook",
        Channel.INSTAGRAM: "Instagram",
        Channel.ZALO_OA: "Zalo",
        Channel.ZALO: "Zalo",
        Channel.ZALO_GROUP: "nhóm Zalo",
        Channel.TIKTOK: "TikTok",
        Channel.WEB: "web",
    }
    items = ", ".join(f"{i.name} x{i.quantity}" for i in draft.items) or "chưa rõ món"
    out = await control.propose(
        CONFIRM_ACTION,
        f"Chốt đơn từ tin nhắn {channel_names.get(draft.channel, draft.channel.value)}: {draft.recipient_name} · {items}"[:200],
        {"order_id": str(draft.id)},
        {"order_code": draft.code, "recipient_name": draft.recipient_name, "phone": draft.recipient_phone,
         "address": ", ".join(x for x in (draft.address_line, draft.ward, draft.district, draft.province) if x),
         "items": [{"name": i.name, "quantity": i.quantity, "unit_price_vnd": i.unit_price_vnd, "matched": i.product_id is not None} for i in draft.items],
         "payment_method": draft.payment_method.value, "missing": missing, "message": message},
        db=db,
        summary=("Còn thiếu: " + ", ".join(missing) + ". Chị điền nốt rồi duyệt.") if missing else "Đủ thông tin, chị duyệt để chốt đơn và báo khách.",
        rationale=f"Khách nhắn: «{(message or '')[:300]}»",
        ref_type="orders", ref_id=draft.id, ai_run_id=ai_run_id, dedupe_key=f"draft:{draft.id}", priority=6,
    )  # fmt: skip
    draft.approval_item_id = out.item_id
    draft.internal_note = ("Thiếu: " + ", ".join(missing)) if missing else None
    await db.flush()


async def apply_patch(
    db: AsyncSession, order: Order, patch: DraftConfirmIn | dict[str, Any]
) -> list[CartLineIn] | None:
    data = (
        patch.model_dump(exclude_unset=True)
        if isinstance(patch, DraftConfirmIn)
        else {k: v for k, v in patch.items() if v is not None}
    )
    for f in ("recipient_name", "address_line", "ward", "district", "province", "customer_note", "internal_note"):
        if data.get(f):
            setattr(order, f, data[f])
    if data.get("recipient_phone"):
        order.recipient_phone = data["recipient_phone"]
    if data.get("payment_method"):
        order.payment_method = PaymentMethod(data["payment_method"])
    if data.get("items"):
        return [CartLineIn.model_validate(x) for x in data["items"]]
    return None


async def confirm(
    db: AsyncSession, order: Order, patch: DraftConfirmIn | dict[str, Any] | None = None, *, user: Any = None
) -> Order:
    """Chốt đơn nháp (sau khi chị duyệt hoặc chị bấm chốt ở màn hình đơn)."""
    if order.status != OrderStatus.DRAFT:
        raise BadRequest("Đơn này không còn là đơn nháp.", code="not_draft")
    lines = await apply_patch(db, order, patch or {}) if patch else None
    if lines is None:
        if any(i.product_id is None for i in order.items) or not order.items:
            raise BadRequest(
                "Đơn nháp còn món chưa khớp sản phẩm. Chị chọn lại món giúp em.",
                code="missing_info",
                data={"missing": ["món cụ thể"]},
            )
        lines = await service.lines_of(db, order)
    await service.finalize(
        db, order, lines, opts=service.ResolveOptions(store=False), actor=Actor.OWNER if user else Actor.AI, user=user
    )
    return order
