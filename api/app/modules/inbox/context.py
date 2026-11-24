"""Gom dữ liệu thật cho AI soạn trả lời (h2). Chỉ ĐỌC bảng của module khác: catalog (sản phẩm, đợt, tồn kho),
orders (đơn, vận đơn), content (giọng của chị, bài đăng có bình luận)."""

from __future__ import annotations

import re
import uuid

from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.timeutil import to_local
from app.modules.catalog.models import Drop, DropItem, DropStatus, InventoryItem, Product, ProductStatus
from app.modules.content.models import ScheduledPost, VoiceProfile
from app.modules.inbox.ai_tasks import DraftReplyIn, HistoryLine, OrderFact, ProductFact
from app.modules.inbox.models import Direction, Message, Thread, ThreadKind
from app.modules.inbox.textsearch import fold
from app.modules.orders.models import Customer, Order, OrderStatus, Shipment

ORDER_STATUS_LABELS = {
    OrderStatus.DRAFT: "đơn nháp",
    OrderStatus.PENDING_PAYMENT: "chờ thanh toán",
    OrderStatus.CONFIRMED: "đã nhận đơn",
    OrderStatus.AWAITING_STOCK: "chờ hàng về",
    OrderStatus.READY_TO_SHIP: "đang đóng gói",
    OrderStatus.SHIPPING: "đang giao",
    OrderStatus.DELIVERED: "đã giao",
    OrderStatus.COMPLETED: "hoàn tất",
    OrderStatus.CANCELLED: "đã huỷ",
    OrderStatus.RETURNED: "đã hoàn",
}

SHIPPING_POLICY_KEY = "inbox.shipping_policy"


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", fold(s)) if len(w) > 2]


async def _product_facts(db: AsyncSession, products: list[Product]) -> list[ProductFact]:
    if not products:
        return []
    ids = [p.id for p in products]
    stock = dict(
        (
            await db.execute(
                select(InventoryItem.product_id, func.sum(InventoryItem.on_hand - InventoryItem.reserved))
                .where(InventoryItem.product_id.in_(ids))
                .group_by(InventoryItem.product_id)
            )
        ).all()
    )
    drops = (
        await db.execute(
            select(DropItem, Drop)
            .join(Drop, Drop.id == DropItem.drop_id)
            .where(DropItem.product_id.in_(ids), Drop.status == DropStatus.OPEN)
            .order_by(Drop.closes_at)
        )
    ).all()
    drop_by_product: dict[uuid.UUID, dict] = {}
    for di, d in drops:
        if di.product_id in drop_by_product:
            continue
        drop_by_product[di.product_id] = {
            "title": d.title,
            "closes_at": to_local(d.closes_at).date().isoformat() if d.closes_at else None,
            "expected_arrival": d.expected_arrival_date.isoformat() if d.expected_arrival_date else None,
            "price_vnd": di.price_vnd or None,
            "slots_left": (di.slots_total - di.slots_reserved) if di.slots_total is not None else None,
        }
    out = []
    for p in products:
        s = stock.get(p.id)
        out.append(
            ProductFact(
                id=str(p.id),
                name=p.name,
                price_vnd=p.price_vnd,
                compare_at_price_vnd=p.compare_at_price_vnd,
                short_description=p.short_description,
                specs=[x for x in p.specs[:8] if isinstance(x, dict)],
                faq=[x for x in p.faq[:6] if isinstance(x, dict)],
                not_satisfied=p.not_satisfied,
                shipping_notes=[str(x) for x in p.shipping_notes[:5]],
                sale_mode=str(p.sale_mode),
                in_stock=int(s) if s is not None else None,
                drop=drop_by_product.get(p.id),
                url=f"/san-pham/{p.slug}",
            )
        )
    return out


async def related_products(db: AsyncSession, thread: Thread, text: str, limit: int = 3) -> list[Product]:
    """Món khách đang hỏi: món gắn với hội thoại / bài đăng có bình luận, cộng các món có tên khớp với tin."""
    picked: list[Product] = []
    if thread.product_id:
        p = await db.get(Product, thread.product_id)
        if p:
            picked.append(p)
    if thread.external_post_id or thread.scheduled_post_id:
        q = select(ScheduledPost.product_id).where(ScheduledPost.product_id.is_not(None))
        q = (
            q.where(ScheduledPost.id == thread.scheduled_post_id)
            if thread.scheduled_post_id
            else q.where(ScheduledPost.external_post_id == thread.external_post_id)
        )
        pid = (await db.execute(q.limit(1))).scalar_one_or_none()
        if pid and all(p.id != pid for p in picked):
            p = await db.get(Product, pid)
            if p:
                picked.append(p)
    rows = list(
        (
            await db.execute(
                select(Product).where(Product.status == ProductStatus.PUBLISHED).order_by(Product.published_at.desc())
            )
        ).scalars()
    )
    t = fold(text)
    scored = []
    for p in rows:
        if any(x.id == p.id for x in picked):
            continue
        words = _words(p.name)
        hits = sum(1 for w in words if w in t)
        score = hits * 30 + fuzz.partial_ratio(fold(p.name), t) / 10
        if hits:
            scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    picked += [p for _, p in scored[: max(0, limit - len(picked))]]
    return picked[:limit]


async def customer_orders(db: AsyncSession, customer_id: uuid.UUID | None, limit: int = 5) -> list[OrderFact]:
    if not customer_id:
        return []
    orders = list(
        (
            await db.execute(
                select(Order).where(Order.customer_id == customer_id).order_by(Order.placed_at.desc()).limit(limit)
            )
        ).scalars()
    )
    out = []
    for o in orders:
        ship = (
            await db.execute(
                select(Shipment).where(Shipment.order_id == o.id).order_by(Shipment.created_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        arrival = None
        if o.drop_id:
            d = await db.get(Drop, o.drop_id)
            arrival = d.expected_arrival_date.isoformat() if d and d.expected_arrival_date else None
        out.append(
            OrderFact(
                code=o.code,
                status=str(o.status),
                status_label=ORDER_STATUS_LABELS.get(o.status, str(o.status)),
                placed_at=to_local(o.placed_at).date().isoformat(),
                total_vnd=o.total_vnd,
                items=[f"{i.name} × {i.quantity}" for i in o.items],
                expected_arrival=arrival,
                shipping_status=str(ship.status) if ship else None,
                tracking_code=ship.tracking_code if ship else None,
            )
        )
    return out


async def voice(db: AsyncSession) -> dict:
    v = (
        await db.execute(
            select(VoiceProfile).where(VoiceProfile.is_active.is_(True)).order_by(VoiceProfile.updated_at.desc())
        )
    ).scalar_one_or_none()
    if not v:
        return {}
    return {"style_summary": v.style_summary, "rules": v.rules[:10], "vocabulary": v.vocabulary[:20]}


async def build(db: AsyncSession, thread: Thread, message: Message, *, owner_note: str | None = None) -> DraftReplyIn:
    hist = list(
        (
            await db.execute(
                select(Message)
                .where(Message.thread_id == thread.id, Message.id != message.id)
                .order_by(Message.sent_at.desc())
                .limit(8)
            )
        ).scalars()
    )
    history = [
        HistoryLine(
            who="khach" if m.direction == Direction.INBOUND else ("ai" if m.ai_generated else "chi"), text=m.body[:500]
        )
        for m in reversed(hist)
    ]
    context_text = " ".join([*(h.text for h in history[-3:] if h.who == "khach"), message.body])
    products = await related_products(db, thread, context_text)
    customer = await db.get(Customer, thread.customer_id) if thread.customer_id else None
    return DraftReplyIn(
        channel=str(thread.channel),
        kind=str(thread.kind),
        customer_name=(customer.name if customer and customer.name else thread.participant_name),
        message=message.body,
        history=history,
        products=await _product_facts(db, products),
        # bình luận là công khai: không đưa đơn của khách vào để AI không lỡ nhắc tới
        orders=[] if thread.kind == ThreadKind.COMMENT else await customer_orders(db, thread.customer_id),
        shipping_policy=await control.get_setting(db, SHIPPING_POLICY_KEY) or None,
        voice=await voice(db),
        owner_note=owner_note,
    )
