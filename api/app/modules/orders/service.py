"""Lõi nghiệp vụ orders: tạo đơn (giữ suất/tồn ngay trong giao dịch), trạng thái + hành trình, khách, huỷ,
danh sách cho chị (g1), trang theo dõi cho khách (e5).

Chống đặt vượt: khoá dòng `drop_items` / `inventory_items` (SELECT … FOR UPDATE, chỉ đọc) rồi tính
`còn lại = tổng − phần catalog đã trừ − phần các đơn chưa thanh toán đang giữ`. Catalog trừ suất/tồn khi nghe
`order.paid` (ARCHITECTURE mục 10), nên đơn đã phát `order.paid` (có `paid_at`) không bị tính lần hai."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core import events
from app.core.config import settings
from app.core.enums import Actor, Channel, ShippingStatus
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.money import round_vnd
from app.core.pagination import PageParams, Paginated, paginate
from app.core.timeutil import now_utc
from app.integrations import get_driver
from app.modules.catalog.models import Drop, DropItem, DropStatus, Product, ProductStatus, ProductVariant, SaleMode
from app.modules.orders import notify, refs
from app.modules.orders.models import (
    Customer,
    FulfillmentSource,
    Order,
    OrderEvent,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentState,
    PaymentStatus,
    Return,
    ReturnStatus,
    Shipment,
)
from app.modules.orders.schemas import CartLineIn, OrderListItem, QuoteLineOut
from app.modules.orders.util import (
    code_suffix,
    new_code,
    normalize_phone,
    unaccent,
    unaccent_sql,
)

log = logging.getLogger("app.orders")

STATUS_LABELS: dict[OrderStatus, str] = {
    OrderStatus.DRAFT: "Đơn nháp",
    OrderStatus.PENDING_PAYMENT: "Chờ chuyển khoản",
    OrderStatus.CONFIRMED: "Đã xác nhận",
    OrderStatus.AWAITING_STOCK: "Chờ hàng về",
    OrderStatus.READY_TO_SHIP: "Chờ giao",
    OrderStatus.SHIPPING: "Đang giao",
    OrderStatus.DELIVERED: "Đã giao",
    OrderStatus.COMPLETED: "Hoàn tất",
    OrderStatus.CANCELLED: "Đã huỷ",
    OrderStatus.RETURNED: "Đã hoàn về",
}

GROUPS: dict[str, tuple[OrderStatus, ...]] = {
    "nhap": (OrderStatus.DRAFT,),
    "cho_thanh_toan": (OrderStatus.PENDING_PAYMENT,),
    "cho_hang": (OrderStatus.CONFIRMED, OrderStatus.AWAITING_STOCK),
    "cho_giao": (OrderStatus.READY_TO_SHIP,),
    "dang_giao": (OrderStatus.SHIPPING,),
    "xong": (OrderStatus.DELIVERED, OrderStatus.COMPLETED),
    "huy": (OrderStatus.CANCELLED, OrderStatus.RETURNED),
}

NOT_HOLDING = (OrderStatus.DRAFT, OrderStatus.CANCELLED, OrderStatus.RETURNED)
CANCELLABLE = (
    OrderStatus.DRAFT,
    OrderStatus.PENDING_PAYMENT,
    OrderStatus.CONFIRMED,
    OrderStatus.AWAITING_STOCK,
    OrderStatus.READY_TO_SHIP,
)
ADDRESS_EDITABLE = (
    OrderStatus.DRAFT,
    OrderStatus.PENDING_PAYMENT,
    OrderStatus.CONFIRMED,
    OrderStatus.AWAITING_STOCK,
    OrderStatus.READY_TO_SHIP,
)
ACTIVE_SHIPMENT = (
    ShippingStatus.CREATED,
    ShippingStatus.PICKED_UP,
    ShippingStatus.IN_TRANSIT,
    ShippingStatus.OUT_FOR_DELIVERY,
    ShippingStatus.FAILED_DELIVERY,
    ShippingStatus.RETURNING,
)


# ---- hành trình đơn ----------------------------------------------------------------------------------------------


def add_event(
    db: AsyncSession,
    order: Order,
    kind: str,
    title: str,
    *,
    status: OrderStatus | None = None,
    detail: str | None = None,
    visible: bool = True,
    actor: Actor = Actor.SYSTEM,
    data: dict[str, Any] | None = None,
) -> OrderEvent:
    ev = OrderEvent(
        order_id=order.id,
        kind=kind,
        status=status,
        title=title[:200],
        detail=detail,
        visible_to_customer=visible,
        actor=actor,
        occurred_at=now_utc(),
        data=data or {},
    )
    db.add(ev)
    return ev


def set_status(
    db: AsyncSession,
    order: Order,
    new: OrderStatus,
    title: str,
    *,
    actor: Actor = Actor.SYSTEM,
    detail: str | None = None,
    visible: bool = True,
    data: dict[str, Any] | None = None,
) -> bool:
    """Đổi trạng thái + ghi `order_events`. Trả False nếu đã ở trạng thái đó (gọi lặp không ghi trùng)."""
    if order.status == new:
        return False
    old = order.status
    order.status = new
    add_event(
        db, order, "status_changed", title, status=new, detail=detail, visible=visible, actor=actor,
        data={"from": old.value if old else None, "to": new.value, **(data or {})},
    )  # fmt: skip
    return True


async def get_order(db: AsyncSession, order_id: uuid.UUID, *, lock: bool = False) -> Order:
    q = select(Order).where(Order.id == order_id)
    if lock:
        q = q.with_for_update()
    order = (await db.execute(q)).scalar_one_or_none()
    if order is None:
        raise NotFound("Không tìm thấy đơn.")
    return order


async def get_by_code(db: AsyncSession, code: str, *, lock: bool = False) -> Order | None:
    q = select(Order).where(Order.code == code)
    if lock:
        q = q.with_for_update()
    return (await db.execute(q)).scalar_one_or_none()


# ---- giải các dòng hàng: giá, suất, tồn --------------------------------------------------------------------------


@dataclass
class Resolved:
    line: CartLineIn
    product: Product | None = None
    variant: ProductVariant | None = None
    drop: Drop | None = None
    drop_item: DropItem | None = None
    unit_price_vnd: int = 0
    available: int | None = None
    problem: str | None = None
    source: FulfillmentSource = FulfillmentSource.DROP
    image_url: str | None = None

    @property
    def name(self) -> str:
        return self.product.name if self.product else "Món không còn bán"


@dataclass
class ResolveOptions:
    store: bool = True  # khách đặt: chỉ món đã đăng + đợt đang mở
    lock: bool = False
    exclude_order_id: uuid.UUID | None = None
    price_overrides: dict[int, int] = field(default_factory=dict)


async def pending_drop_qty(db: AsyncSession, drop_item_id: uuid.UUID, exclude: uuid.UUID | None = None) -> int:
    q = (
        select(func.coalesce(func.sum(OrderItem.quantity), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .where(OrderItem.drop_item_id == drop_item_id, Order.status.not_in(NOT_HOLDING), Order.paid_at.is_(None))
    )
    if exclude:
        q = q.where(Order.id != exclude)
    return int((await db.execute(q)).scalar_one())


async def pending_stock_qty(
    db: AsyncSession, product_id: uuid.UUID, variant_id: uuid.UUID | None, exclude: uuid.UUID | None = None
) -> int:
    q = (
        select(func.coalesce(func.sum(OrderItem.quantity), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            OrderItem.product_id == product_id,
            OrderItem.variant_id.is_(None) if variant_id is None else OrderItem.variant_id == variant_id,
            OrderItem.fulfillment_source == FulfillmentSource.STOCK,
            Order.status.not_in(NOT_HOLDING),
            Order.paid_at.is_(None),
        )
    )
    if exclude:
        q = q.where(Order.id != exclude)
    return int((await db.execute(q)).scalar_one())


async def resolve_lines(db: AsyncSession, lines: list[CartLineIn], opts: ResolveOptions) -> list[Resolved]:
    """Tra giá thật, kiểm đợt còn mở, kiểm suất/tồn còn lại. Có `lock` thì khoá dòng đợt/tồn theo thứ tự cố định."""
    products = await refs.products_by_id(db, [ln.product_id for ln in lines])
    images = await refs.primary_images(db, products.keys())
    out: list[Resolved] = []
    now = now_utc()
    for idx, ln in enumerate(lines):
        r = Resolved(line=ln)
        out.append(r)
        p = products.get(ln.product_id)
        if p is None or p.status == ProductStatus.ARCHIVED or (opts.store and p.status != ProductStatus.PUBLISHED):
            r.problem = "Món này hiện không bán."
            continue
        r.product = p
        r.image_url = images.get(p.id)
        if ln.variant_id:
            r.variant = next((v for v in p.variants if v.id == ln.variant_id and v.is_active), None)
            if r.variant is None:
                r.problem = "Phân loại này không còn."
                continue
        elif opts.store and any(v.is_active for v in p.variants):
            r.problem = "Bạn chọn phân loại (màu, cỡ) giúp mình."
            continue
        base_price = r.variant.price_vnd if r.variant and r.variant.price_vnd is not None else p.price_vnd
        if ln.drop_id:
            drop = await db.get(Drop, ln.drop_id)
            r.drop = drop
            ok_status = (DropStatus.OPEN,) if opts.store else (DropStatus.OPEN, DropStatus.SCHEDULED, DropStatus.CLOSED)
            if drop is None or drop.status not in ok_status:
                r.problem = "Đợt này đã đóng, không nhận thêm đơn."
                continue
            if opts.store and drop.closes_at and drop.closes_at <= now:
                r.problem = "Đợt này đã hết hạn đặt."
                continue
            if opts.store and drop.opens_at and drop.opens_at > now:
                r.problem = "Đợt này chưa mở."
                continue
            r.drop_item = next(
                (di for di in drop.items if di.product_id == p.id and di.variant_id == ln.variant_id), None
            )
            if r.drop_item is None:
                r.problem = "Món này không có trong đợt."
                continue
            r.source = FulfillmentSource.DROP
            r.unit_price_vnd = r.drop_item.price_vnd or base_price
            if r.drop_item.max_per_order and ln.quantity > r.drop_item.max_per_order:
                r.problem = f"Mỗi đơn đặt tối đa {r.drop_item.max_per_order} cái."
        else:
            if opts.store and p.sale_mode == SaleMode.DROP:
                r.problem = "Món này chỉ bán theo đợt."
                continue
            r.source = FulfillmentSource.STOCK
            r.unit_price_vnd = base_price
        if idx in opts.price_overrides:
            r.unit_price_vnd = opts.price_overrides[idx]

    # suất / tồn: khoá theo thứ tự cố định (tránh khoá chéo), cộng dồn các dòng cùng món
    drop_keys = sorted({r.drop_item.id for r in out if r.drop_item and not r.problem}, key=str)
    stock_keys = sorted(
        {(r.product.id, r.variant.id if r.variant else None) for r in out if r.product and r.source == FulfillmentSource.STOCK and not r.problem},
        key=str,
    )  # fmt: skip
    remaining: dict[Any, int | None] = {}
    for di_id in drop_keys:
        q = select(DropItem).where(DropItem.id == di_id)
        di = (await db.execute(q.with_for_update() if opts.lock else q)).scalar_one()
        if di.slots_total is None:
            remaining[di_id] = None
        else:
            held = await pending_drop_qty(db, di_id, opts.exclude_order_id)
            remaining[di_id] = max(0, di.slots_total - di.slots_reserved - held)
    for key in stock_keys:
        inv = await refs.inventory_for(db, key[0], key[1], lock=opts.lock)
        if inv is None:
            remaining[key] = 0
        else:
            held = await pending_stock_qty(db, key[0], key[1], opts.exclude_order_id)
            remaining[key] = max(0, inv.on_hand - inv.reserved - held)
    want: dict[Any, int] = {}
    for r in out:
        if r.problem:
            continue
        key = r.drop_item.id if r.drop_item else (r.product.id, r.variant.id if r.variant else None)  # type: ignore[union-attr]
        r.available = remaining.get(key)
        want[key] = want.get(key, 0) + r.line.quantity
        if r.available is not None and want[key] > r.available:
            if r.available <= 0:
                r.problem = "Hết suất rồi." if r.drop_item else "Hết hàng rồi."
            else:
                r.problem = f"Chỉ còn {r.available} {'suất' if r.drop_item else 'cái'}."
    return out


async def lines_of(db: AsyncSession, order: Order) -> list[CartLineIn]:
    """Dòng hàng của một đơn → dòng giỏ (để kiểm lại suất khi chốt nháp / mở lại đơn)."""
    di_ids = [i.drop_item_id for i in order.items if i.drop_item_id]
    drop_of = (
        dict((await db.execute(select(DropItem.id, DropItem.drop_id).where(DropItem.id.in_(di_ids)))).all())
        if di_ids
        else {}
    )
    return [
        CartLineIn(
            product_id=i.product_id, variant_id=i.variant_id, drop_id=drop_of.get(i.drop_item_id), quantity=i.quantity
        )
        for i in order.items
        if i.product_id
    ]


def quote_line(r: Resolved) -> QuoteLineOut:
    return QuoteLineOut(
        product_id=r.line.product_id,
        variant_id=r.line.variant_id,
        drop_id=r.line.drop_id,
        drop_item_id=r.drop_item.id if r.drop_item else None,
        fulfillment_source=r.source,
        name=r.name,
        variant_name=r.variant.name if r.variant else None,
        slug=r.product.slug if r.product else None,
        image_url=r.image_url,
        unit_price_vnd=r.unit_price_vnd,
        quantity=r.line.quantity,
        line_total_vnd=r.unit_price_vnd * r.line.quantity,
        available=r.available,
        ok=r.problem is None,
        problem=r.problem,
    )


def order_weight(resolved: list[Resolved]) -> int:
    default = 500
    return sum(
        (r.product.weight_grams if r.product and r.product.weight_grams else default) * r.line.quantity
        for r in resolved
    )


def single_drop(resolved: list[Resolved]) -> Drop | None:
    drops = {r.drop.id: r.drop for r in resolved if r.drop}
    if len(drops) > 1:
        raise Conflict("Mỗi đơn chỉ đặt trong một đợt. Bạn đặt riêng từng đợt giúp mình nhé.", code="mixed_drops")
    return next(iter(drops.values()), None)


def deposit_for(drop: Drop | None, total: int, method: PaymentMethod) -> int:
    if not drop or not drop.deposit_pct or method != PaymentMethod.BANK_TRANSFER:
        return 0
    return min(total, round_vnd(total * drop.deposit_pct / 100))


# ---- khách -------------------------------------------------------------------------------------------------------


async def upsert_customer(
    db: AsyncSession, phone: str, name: str | None, channel: Channel, address: dict[str, Any] | None = None
) -> Customer:
    c = (await db.execute(select(Customer).where(Customer.phone == phone).with_for_update())).scalar_one_or_none()
    if c is None:
        c = Customer(phone=phone, name=name, first_channel=channel, default_address=address or {})
        db.add(c)
        await db.flush()
        return c
    if c.merged_into_id:
        merged = await db.get(Customer, c.merged_into_id)
        if merged is not None:
            c = merged
    if name and not c.name:
        c.name = name
    if address and not c.default_address:
        c.default_address = address
    return c


def _address_dict(order: Order) -> dict[str, Any]:
    return {k: getattr(order, k) for k in ("address_line", "ward", "district", "province") if getattr(order, k)}


# ---- tạo / chốt đơn ----------------------------------------------------------------------------------------------


def missing_info(order: Order) -> list[str]:
    miss = []
    if not order.recipient_name or order.recipient_name == "Chưa rõ":
        miss.append("tên người nhận")
    if not order.recipient_phone:
        miss.append("số điện thoại")
    if not order.address_line or not order.province:
        miss.append("địa chỉ giao (số nhà, tỉnh/thành)")
    if not order.items:
        miss.append("món và số lượng")
    elif any(i.product_id is None for i in order.items):
        miss.append("món chưa khớp sản phẩm nào")
    return miss


async def _unique_code(db: AsyncSession) -> str:
    for _ in range(30):
        code = new_code()
        if not await db.scalar(select(func.count()).where(Order.code == code)):
            return code
    raise Conflict("Không tạo được mã đơn, bạn thử lại giúp mình.")


async def new_draft(
    db: AsyncSession,
    *,
    channel: Channel,
    recipient_name: str | None,
    recipient_phone: str | None,
    address: dict[str, Any] | None = None,
    payment_method: PaymentMethod = PaymentMethod.BANK_TRANSFER,
    customer_note: str | None = None,
    internal_note: str | None = None,
    ai_generated: bool = False,
    thread_id: uuid.UUID | None = None,
    external_id: str | None = None,
    raw: dict[str, Any] | None = None,
) -> Order:
    order = Order(
        code=await _unique_code(db),
        channel=channel,
        status=OrderStatus.DRAFT,
        payment_method=payment_method,
        recipient_name=(recipient_name or "Chưa rõ")[:120],
        recipient_phone=recipient_phone or "",
        customer_note=customer_note,
        internal_note=internal_note,
        ai_generated=ai_generated,
        thread_id=thread_id,
        external_id=external_id,
        placed_at=now_utc(),
        raw=raw or {},
        **{k: v for k, v in (address or {}).items() if k in ("address_line", "ward", "district", "province")},
    )
    order.items = []
    db.add(order)
    await db.flush()
    return order


@dataclass
class FinalizeResult:
    order: Order
    created: bool = True


async def finalize(
    db: AsyncSession,
    order: Order,
    lines: list[CartLineIn],
    *,
    opts: ResolveOptions,
    shipping_fee_vnd: int | None = None,
    discount_vnd: int = 0,
    actor: Actor = Actor.CUSTOMER,
    already_paid: bool = False,
    notify_customer: bool = True,
    user: Any = None,
) -> Order:
    """Đơn nháp → đơn thật: định giá, khoá + kiểm suất/tồn, phí giao, yêu cầu chuyển khoản, trạng thái, sự kiện, báo khách."""
    if order.status != OrderStatus.DRAFT:
        raise Conflict("Đơn này đã được chốt rồi.", code="already_final")
    miss = [m for m in missing_info(order) if m not in ("món và số lượng", "món chưa khớp sản phẩm nào")]
    if miss:
        raise BadRequest("Đơn còn thiếu: " + ", ".join(miss) + ".", code="missing_info", data={"missing": miss})
    phone = normalize_phone(order.recipient_phone)
    order.recipient_phone = phone or ""
    resolved = await resolve_lines(
        db, lines, ResolveOptions(**{**opts.__dict__, "lock": True, "exclude_order_id": order.id})
    )
    problems = [f"{r.name}: {r.problem}" for r in resolved if r.problem]
    if problems:
        raise Conflict(
            " ".join(problems),
            code="unavailable",
            data={"lines": [quote_line(r).model_dump(mode="json") for r in resolved]},
        )
    drop = single_drop(resolved)

    # dòng hàng (thay toàn bộ dòng nháp)
    order.items.clear()
    await db.flush()
    for i, r in enumerate(resolved):
        order.items.append(
            OrderItem(
                position=i,
                product_id=r.product.id if r.product else None,
                variant_id=r.variant.id if r.variant else None,
                drop_item_id=r.drop_item.id if r.drop_item else None,
                fulfillment_source=r.source,
                name=r.name[:300],
                variant_name=r.variant.name if r.variant else None,
                sku=(r.variant.sku if r.variant else None) or (r.product.sku if r.product else None),
                quantity=r.line.quantity,
                unit_price_vnd=r.unit_price_vnd,
                line_total_vnd=r.unit_price_vnd * r.line.quantity,
                unit_cost_vnd=r.product.landed_cost_vnd if r.product else None,
            )
        )
    order.drop_id = drop.id if drop else None
    order.subtotal_vnd = sum(i.line_total_vnd for i in order.items)
    if shipping_fee_vnd is None:
        from app.modules.orders import shipping as ship_svc

        opt = await ship_svc.checkout_fee(db, order_address(order), order_weight(resolved), order.subtotal_vnd)
        shipping_fee_vnd = opt.fee_vnd if opt else 0
    order.shipping_fee_vnd = shipping_fee_vnd
    order.discount_vnd = min(discount_vnd, order.subtotal_vnd + shipping_fee_vnd)
    order.total_vnd = order.subtotal_vnd + order.shipping_fee_vnd - order.discount_vnd
    order.deposit_required_vnd = deposit_for(drop, order.total_vnd, order.payment_method)
    order.placed_at = now_utc()

    customer = await upsert_customer(db, phone or "", order.recipient_name, order.channel, _address_dict(order))
    order.customer_id = customer.id
    customer.order_count += 1
    customer.last_order_at = order.placed_at
    customer.first_order_at = customer.first_order_at or order.placed_at

    add_event(db, order, "placed", "Đã nhận đơn", actor=actor)
    if order.payment_method == PaymentMethod.BANK_TRANSFER and not already_paid:
        due = order.deposit_required_vnd or order.total_vnd
        req = await get_driver("payments").create_request(code_suffix(order.code), due)
        order.transfer_content = req.transfer_content
        order.raw = {**order.raw, "payment_request": req.model_dump(mode="json")}
        hours = int(await control.get_setting(db, "orders.payment_window_hours") or 24)
        order.payment_due_at = order.placed_at + timedelta(hours=hours)
        order.status = OrderStatus.PENDING_PAYMENT
    else:
        order.status = OrderStatus.CONFIRMED
        order.confirmed_at = order.placed_at
        if order.payment_method == PaymentMethod.COD:
            order.cod_amount_vnd = order.total_vnd
    await db.flush()

    if already_paid:
        from app.modules.orders import payments as pay_svc

        await pay_svc.record_manual(
            db,
            order,
            order.total_vnd,
            PaymentMethod.CASH if order.payment_method != PaymentMethod.BANK_TRANSFER else PaymentMethod.BANK_TRANSFER,
            note="Chị ghi nhận đã nhận đủ tiền khi tạo đơn",
            user=user,
        )
    elif order.status == OrderStatus.CONFIRMED:
        await advance_after_confirm(db, order, actor=actor)

    await events.emit("order.created", {"order_id": str(order.id)}, db=db)
    if notify_customer:
        await notify.notify_order(db, order, "order_received", drop_arrival=await arrival_text(db, order))
    from app.modules.orders import drops as drop_svc

    await drop_svc.check_low_stock(db, [i for i in order.items if i.fulfillment_source == FulfillmentSource.STOCK])
    return order


def order_address(order: Order) -> dict[str, Any]:
    return {
        "name": order.recipient_name,
        "phone": order.recipient_phone,
        "address_line": order.address_line or "",
        "ward": order.ward,
        "district": order.district,
        "province": order.province or settings.shipping_from_province,
        "codes": order.address_codes or {},
    }


async def create_order(
    db: AsyncSession,
    *,
    lines: list[CartLineIn],
    name: str,
    phone: str,
    address: dict[str, Any],
    payment_method: PaymentMethod,
    channel: Channel = Channel.WEB,
    opts: ResolveOptions | None = None,
    shipping_fee_vnd: int | None = None,
    discount_vnd: int = 0,
    customer_note: str | None = None,
    internal_note: str | None = None,
    actor: Actor = Actor.CUSTOMER,
    client_ref: str | None = None,
    already_paid: bool = False,
    external_id: str | None = None,
    raw: dict[str, Any] | None = None,
    notify_customer: bool = True,
    user: Any = None,
) -> FinalizeResult:
    if client_ref:
        existing = (
            await db.execute(select(Order).where(Order.raw["client_ref"].astext == client_ref))
        ).scalar_one_or_none()
        if existing is not None:
            return FinalizeResult(existing, created=False)
    phone_n = normalize_phone(phone)
    if not (address.get("address_line") and address.get("province")):
        raise BadRequest("Bạn ghi giúp mình địa chỉ nhận hàng (số nhà, đường và tỉnh/thành).", code="address_required")
    order = await new_draft(
        db, channel=channel, recipient_name=name.strip(), recipient_phone=phone_n, address=address,
        payment_method=payment_method, customer_note=customer_note, internal_note=internal_note,
        external_id=external_id, raw={**(raw or {}), **({"client_ref": client_ref} if client_ref else {})},
    )  # fmt: skip
    await finalize(
        db, order, lines, opts=opts or ResolveOptions(), shipping_fee_vnd=shipping_fee_vnd, discount_vnd=discount_vnd,
        actor=actor, already_paid=already_paid, notify_customer=notify_customer, user=user,
    )  # fmt: skip
    return FinalizeResult(order)


async def arrival_text(db: AsyncSession, order: Order) -> str | None:
    if not order.drop_id:
        return None
    drop = await db.get(Drop, order.drop_id)
    eta = refs.eta_of(drop, await refs.inbound_for_drop(db, order.drop_id))
    return eta.strftime("%d/%m") if eta else None


async def advance_after_confirm(db: AsyncSession, order: Order, *, actor: Actor = Actor.SYSTEM) -> None:
    """Đơn đã xác nhận (đã trả / COD) → chờ hàng về (đơn trong đợt, hàng chưa về) hoặc chờ giao."""
    if order.status not in (OrderStatus.CONFIRMED, OrderStatus.PENDING_PAYMENT):
        return
    if order.drop_id:
        drop = await db.get(Drop, order.drop_id)
        if drop is not None and not await refs.drop_arrived(db, drop):
            set_status(
                db, order, OrderStatus.AWAITING_STOCK, f"Đã xác nhận, chờ hàng của đợt {drop.code} về", actor=actor
            )
            return
    set_status(db, order, OrderStatus.READY_TO_SHIP, "Đã xác nhận, chị đang chuẩn bị gói hàng", actor=actor)


async def mark_paid(db: AsyncSession, order: Order, payment: Payment | None, *, actor: Actor = Actor.SYSTEM) -> bool:
    """Đơn đủ điều kiện coi là đã trả (đủ tiền, hoặc đủ cọc, hoặc COD đã thu): phát `order.paid` đúng một lần."""
    if order.paid_at is not None:
        return False
    order.paid_at = now_utc()
    if order.status == OrderStatus.PENDING_PAYMENT:
        order.status = OrderStatus.CONFIRMED
        order.confirmed_at = order.paid_at
        add_event(db, order, "paid", "Đã nhận tiền, đơn được xác nhận", status=OrderStatus.CONFIRMED, actor=actor)
    if order.status == OrderStatus.CONFIRMED:
        await advance_after_confirm(db, order, actor=actor)
    if order.customer_id:
        c = await db.get(Customer, order.customer_id)
        if c is not None:
            c.total_spent_vnd += order.total_vnd
    await db.flush()
    await events.emit(
        "order.paid", {"order_id": str(order.id), "payment_id": str(payment.id) if payment else None}, db=db
    )
    from app.modules.orders import drops as drop_svc

    await drop_svc.check_low_stock(db, [i for i in order.items if i.fulfillment_source == FulfillmentSource.STOCK])
    return True


async def cancel_order(
    db: AsyncSession,
    order: Order,
    reason: str,
    *,
    actor: Actor = Actor.OWNER,
    notify_customer: bool = True,
    user: Any = None,
) -> Order:
    if order.status not in CANCELLABLE:
        raise Conflict("Đơn đã giao cho hãng vận chuyển, không huỷ được nữa.", code="not_cancellable")
    active = await db.scalar(
        select(func.count()).where(Shipment.order_id == order.id, Shipment.status.in_(ACTIVE_SHIPMENT))
    )
    if active:
        raise Conflict("Đơn đang có vận đơn, chị huỷ vận đơn trước.", code="has_shipment")
    was_paid = order.paid_vnd > 0
    order.cancelled_at = now_utc()
    order.cancel_reason = reason
    set_status(db, order, OrderStatus.CANCELLED, "Đơn đã huỷ", detail=reason, actor=actor)
    await control.cancel_pending(db, action="orders.confirm_draft", ref_type="orders", ref_id=order.id)
    await db.flush()
    await events.emit("order.cancelled", {"order_id": str(order.id), "was_paid": was_paid}, db=db)
    if was_paid:
        from app.modules.orders import returns as ret_svc

        await ret_svc.open_return(
            db, order, kind="refund_only", reason="other", description=f"Huỷ đơn đã trả tiền: {reason}",
            quantity=1, actor=actor, user=user, refund_all=True,
        )  # fmt: skip
    if notify_customer and order.recipient_phone:
        await notify.notify_order(db, order, "order_cancelled", {"ly_do": reason})
    return order


# ---- danh sách cho chị (g1) --------------------------------------------------------------------------------------


def _search_filter(q: str) -> Any:
    q = q.strip()
    digits = "".join(ch for ch in q if ch.isdigit())
    conds = [unaccent_sql(Order.recipient_name).contains(unaccent(q)), Order.code.ilike(f"%{q}%")]
    if len(digits) >= 3:
        conds += [Order.recipient_phone.contains(digits), Order.code.contains(digits)]
    if q:
        conds.append(Order.external_id.ilike(f"%{q}%"))
    return or_(*conds)


def list_query(group: str | None, q: str | None, channel: Channel | None, drop_id: uuid.UUID | None) -> Select[Any]:
    stmt = select(Order)
    if group and group in GROUPS:
        stmt = stmt.where(Order.status.in_(GROUPS[group]))
    if q and q.strip():
        stmt = stmt.where(_search_filter(q))
    if channel:
        stmt = stmt.where(Order.channel == channel)
    if drop_id:
        stmt = stmt.where(Order.drop_id == drop_id)
    order_col = Order.payment_due_at.asc().nulls_last() if group == "cho_thanh_toan" else Order.placed_at.desc()
    return stmt.order_by(order_col, Order.created_at.desc())


async def list_orders(
    db: AsyncSession,
    page: PageParams,
    *,
    group: str | None = None,
    q: str | None = None,
    channel: Channel | None = None,
    drop_id: uuid.UUID | None = None,
) -> Paginated[OrderListItem]:
    res = await paginate(db, list_query(group, q, channel, drop_id), page)
    orders: list[Order] = list(res.items)
    drop_ids = {o.drop_id for o in orders if o.drop_id}
    drops = (
        {d.id: d.code for d in (await db.execute(select(Drop).where(Drop.id.in_(drop_ids)))).scalars()}
        if drop_ids
        else {}
    )
    ids = [o.id for o in orders]
    tracking: dict[uuid.UUID, str] = {}
    if ids:
        for oid, code in (
            await db.execute(
                select(Shipment.order_id, Shipment.tracking_code)
                .where(Shipment.order_id.in_(ids), Shipment.status != ShippingStatus.CANCELLED)
                .order_by(Shipment.created_at)
            )
        ).all():
            if code:
                tracking[oid] = code
    items = [
        OrderListItem(
            id=o.id,
            code=o.code,
            channel=o.channel,
            status=o.status,
            status_label=STATUS_LABELS[o.status],
            payment_method=o.payment_method,
            payment_state=o.payment_state,
            recipient_name=o.recipient_name,
            recipient_phone=o.recipient_phone,
            province=o.province,
            total_vnd=o.total_vnd,
            paid_vnd=o.paid_vnd,
            items_summary=", ".join(f"{i.name} x{i.quantity}" for i in o.items)[:200],
            item_count=sum(i.quantity for i in o.items),
            placed_at=o.placed_at,
            payment_due_at=o.payment_due_at,
            drop_id=o.drop_id,
            drop_code=drops.get(o.drop_id) if o.drop_id else None,
            ai_generated=o.ai_generated,
            tracking_code=tracking.get(o.id),
            missing_info=missing_info(o) if o.status == OrderStatus.DRAFT else [],
        )
        for o in orders
    ]
    return Paginated[OrderListItem](items=items, total=res.total, page=res.page, size=res.size, pages=res.pages)


async def counts(db: AsyncSession) -> dict[str, int]:
    rows = dict((await db.execute(select(Order.status, func.count()).group_by(Order.status))).all())
    out = {g: sum(rows.get(s, 0) for s in sts) for g, sts in GROUPS.items()}
    out["tat_ca"] = sum(rows.values())
    from app.core.timeutil import local_day_bounds_utc

    start, end = local_day_bounds_utc()
    out["new_today"] = int(
        await db.scalar(
            select(func.count()).where(
                Order.placed_at >= start,
                Order.placed_at < end,
                Order.status.not_in((OrderStatus.DRAFT, OrderStatus.CANCELLED)),
            )
        )
        or 0
    )
    out["payments_to_review"] = int(
        await db.scalar(select(func.count()).where(Payment.status == PaymentStatus.NEEDS_REVIEW)) or 0
    )
    out["returns_open"] = int(
        await db.scalar(
            select(func.count()).where(
                Return.status.in_(
                    (
                        ReturnStatus.REQUESTED,
                        ReturnStatus.PENDING_DECISION,
                        ReturnStatus.AWAITING_ITEM,
                        ReturnStatus.APPROVED,
                    )
                )
            )
        )
        or 0
    )
    return out


def amount_due(order: Order) -> int:
    if order.payment_method != PaymentMethod.BANK_TRANSFER or order.status in NOT_HOLDING:
        return 0
    if order.payment_state == PaymentState.PAID:
        return 0
    if order.deposit_required_vnd and order.paid_vnd < order.deposit_required_vnd:
        return order.deposit_required_vnd - order.paid_vnd
    return max(0, order.total_vnd - order.paid_vnd)


def recompute_payment_state(order: Order) -> None:
    if order.refunded_vnd > 0:
        order.payment_state = (
            PaymentState.REFUNDED if order.refunded_vnd >= order.paid_vnd else PaymentState.PARTIALLY_REFUNDED
        )
    elif order.paid_vnd >= order.total_vnd and order.total_vnd > 0:
        order.payment_state = PaymentState.PAID
    elif order.paid_vnd > 0:
        order.payment_state = PaymentState.PARTIALLY_PAID
    else:
        order.payment_state = PaymentState.UNPAID
