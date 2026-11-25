"""Đường dẫn của orders: `/api/store/orders/**` (khách, công khai), `/api/desk/orders/**` (chị), `/api/hooks/**` (webhook)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import select

from app import control
from app.core import ratelimit
from app.core.config import settings
from app.core.db import DbSession
from app.core.deps import CurrentUser, OwnerUser
from app.core.enums import Actor, Channel
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.pagination import Page, Paginated, paginate
from app.core.timeutil import to_local
from app.integrations import get_driver
from app.integrations.base import IntegrationError
from app.modules.catalog.models import Drop, Product
from app.modules.orders import (
    drafts,
    drops,
    marketplace,
    notify,
    payments,
    public,
    refs,
    returns,
    service,
    shipping,
    views,
)
from app.modules.orders.models import (
    MarketplaceListing,
    Order,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Return,
    Shipment,
)
from app.modules.orders.schemas import (
    AddressChangeIn,
    CancelIn,
    CheckoutIn,
    CreateShipmentsIn,
    DeskReturnIn,
    DraftConfirmIn,
    DropOverview,
    InventoryRow,
    LabelOut,
    ListingRow,
    LookupIn,
    LookupOut,
    ManualOrderIn,
    ManualPaymentIn,
    MarketplaceListingOut,
    MarketplaceSyncOut,
    OrderCounts,
    OrderDetailOut,
    OrderListItem,
    OrderPatchIn,
    PaymentMatchIn,
    PaymentRowOut,
    ProvinceSuggestion,
    PublicOrderOut,
    PublicReturnIn,
    QuestionIn,
    QuoteIn,
    QuoteOut,
    ReturnOut,
    ReturnRowOut,
    SellableDrop,
    SellableProduct,
    ShipmentEventOut,
    ShipmentOut,
    ShipmentsResultOut,
    ShipmentWithEvents,
    ShippingOption,
    SimulateMarketplaceOrderIn,
    SimulateTransferIn,
    StatusGroup,
    TemplatesIn,
    TemplatesOut,
    WebhookAck,
)
from app.modules.orders.util import (
    check_access_token,
    normalize_order_code,
    normalize_phone,
    suggest_provinces,
)

store = APIRouter(prefix="/api/store/orders", tags=["orders · store"])
desk = APIRouter(prefix="/api/desk/orders", tags=["orders · desk"])
hooks = APIRouter(prefix="/api/hooks", tags=["orders · hooks"])
routers = [store, desk, hooks]


def _address(body: Any) -> dict[str, Any]:
    return {k: getattr(body, k) for k in ("address_line", "ward", "district", "province") if getattr(body, k, None)}


async def _public_order(db: DbSession, code: str, token: str | None, *, lock: bool = False) -> Order:
    order = await service.get_by_code(db, normalize_order_code(code), lock=lock)
    if order is None or order.status == OrderStatus.DRAFT or not check_access_token(order.id, token):
        raise NotFound("Không tìm thấy đơn. Bạn kiểm tra lại mã đơn và số điện thoại nhé.")
    return order


# ======================================================================================================================
# store — khách
# ======================================================================================================================


@store.post("/quote", response_model=QuoteOut)
async def quote(body: QuoteIn, request: Request, db: DbSession) -> QuoteOut:
    """Giỏ → giá thật, suất còn lại, phí giao (tính qua hãng), cọc, ngày hàng về. Không giữ suất."""
    await ratelimit.limit(f"orders:quote:{ratelimit.client_ip(request)}", 120, 600)
    resolved = await service.resolve_lines(db, body.items, service.ResolveOptions(store=True))
    problems = [f"{r.name}: {r.problem}" for r in resolved if r.problem]
    drops_map = {r.drop.id: r.drop for r in resolved if r.drop}
    if len(drops_map) > 1:
        problems.append("Mỗi đơn chỉ đặt trong một đợt. Bạn đặt riêng từng đợt giúp mình nhé.")
    subtotal = sum(r.unit_price_vnd * r.line.quantity for r in resolved if not r.problem)
    addr = {"name": "Khách", "phone": "", **_address(body)}
    estimated = not (body.province and body.address_line)
    opt = await shipping.checkout_fee(db, addr, service.order_weight(resolved), subtotal) if subtotal else None
    fee = opt.fee_vnd if opt else 0
    method = PaymentMethod(body.payment_method)
    drop = next(iter(drops_map.values()), None) if len(drops_map) == 1 else None
    total = subtotal + fee
    lots = await refs.inbound_for_drop(db, drop.id) if drop else []
    eta = refs.eta_of(drop, lots)
    hint = None
    if drop is not None:
        hint = f"Đợt {drop.code} chốt " + (
            to_local(drop.closes_at).strftime("%d/%m") if drop.closes_at else "khi đủ suất"
        )
        if eta:
            hint += f", hàng về dự kiến {eta:%d/%m}, giao cho bạn khoảng {eta + timedelta(days=1):%d/%m}–{eta + timedelta(days=3):%d/%m}."
        else:
            hint += "."
    elif resolved and not problems:
        hint = "Hàng có sẵn, chị gửi trong 1–2 ngày."
    return QuoteOut(
        lines=[service.quote_line(r) for r in resolved], subtotal_vnd=subtotal, shipping_fee_vnd=fee,
        shipping_estimated=estimated, total_vnd=total, deposit_required_vnd=service.deposit_for(drop, total, method),
        drops=[d for d in [refs.drop_brief(x) for x in drops_map.values()] if d], delivery_hint=hint,
        problems=problems, ok=not problems and bool(resolved),
    )  # fmt: skip


def _attribution(src: str | None) -> dict[str, str] | None:
    """f7: mã bài trong link (`?src=`) lưu ở `orders.raw["src"]` để content đếm đơn theo bài."""
    clean = "".join(ch for ch in (src or "").strip().lower() if ch.isalnum() or ch in "-_")[:40]
    return {"src": clean} if clean else None


@store.post("", response_model=PublicOrderOut, status_code=status.HTTP_201_CREATED)
async def checkout(body: CheckoutIn, request: Request, db: DbSession) -> PublicOrderOut:
    """e4: đặt hàng một trang, không cần tài khoản. Giữ suất/tồn ngay trong giao dịch; phát `order.created`."""
    # đơn giữ suất ngay → chặn một máy giữ hết suất của đợt bằng đơn rác (ngưỡng rộng vì nhà mạng dùng chung IP)
    await ratelimit.limit(f"orders:checkout:{ratelimit.client_ip(request)}", 20, 600)
    res = await service.create_order(
        db, lines=body.items, name=body.name, phone=body.phone, address=_address(body),
        payment_method=PaymentMethod(body.payment_method), channel=Channel.WEB, customer_note=body.note,
        client_ref=body.client_ref, actor=Actor.CUSTOMER, raw=_attribution(body.src),
        referral_code=(body.referral_code or "").strip().upper() or None,
    )  # fmt: skip
    if res.created and body.marketing_opt_in and res.order.customer_id:
        from app.modules.orders.models import Customer

        c = await db.get(Customer, res.order.customer_id)
        if c is not None:
            c.marketing_opt_in = True
    return await public.public_view(db, res.order)


@store.post("/lookup", response_model=LookupOut)
async def lookup(body: LookupIn, request: Request, db: DbSession) -> LookupOut:
    """e5: tra đơn bằng số điện thoại + mã đơn → mã xem đơn."""
    phone = normalize_phone(body.phone)
    # mã đơn chỉ 5 chữ số: biết số điện thoại thì dò được → giới hạn theo IP, và theo số điện thoại (chỉ đếm lần sai)
    await ratelimit.limit(f"orders:lookup:{ratelimit.client_ip(request)}", 30, 600)
    phone_key = f"orders:lookup:{phone}"
    if not await ratelimit.hit(phone_key, 10, 3600, record=False):
        raise ratelimit.RateLimited()
    order = await service.get_by_code(db, normalize_order_code(body.code))
    if order is None or order.status == OrderStatus.DRAFT or order.recipient_phone != phone:
        await ratelimit.hit(phone_key, 10, 3600)
        raise NotFound("Không thấy đơn khớp số điện thoại và mã này. Bạn kiểm tra lại giúp mình nhé.")
    from app.modules.orders.util import order_access_token

    return LookupOut(code=order.code, token=order_access_token(order.id))


@store.get("/address-suggestions", response_model=list[ProvinceSuggestion])
async def address_suggestions(
    q: str = "", level: str = "province", parent: str | None = None
) -> list[ProvinceSuggestion]:
    """Gợi ý tỉnh/quận/phường: dùng danh mục của hãng giao nếu driver có, không thì danh sách 34 tỉnh/thành."""
    driver = get_driver("shipping")
    fn = getattr(driver, "address_suggestions", None)
    if fn is not None:
        try:
            return [ProvinceSuggestion(**s) for s in await fn(level, q, parent)]
        except IntegrationError:
            pass
    if level != "province":
        return []
    return [ProvinceSuggestion(name=p) for p in suggest_provinces(q)]


@store.get("/{code}", response_model=PublicOrderOut)
async def get_public(code: str, db: DbSession, t: str = Query(min_length=8, max_length=64)) -> PublicOrderOut:
    return await public.public_view(db, await _public_order(db, code, t))


@store.get("/{code}/qr.svg")
async def qr_svg(code: str, db: DbSession, t: str = Query(min_length=8, max_length=64)) -> Response:
    """Mã VietQR (SVG) cho số tiền còn phải chuyển."""
    order = await _public_order(db, code, t)
    info = await public.payment_info(order)
    if not info or not info.qr_payload:
        raise NotFound("Đơn này không cần chuyển khoản nữa.")
    img = qrcode.make(info.qr_payload, image_factory=qrcode.image.svg.SvgPathImage, border=2)
    return Response(img.to_string(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@store.post("/{code}/questions", response_model=PublicOrderOut, status_code=status.HTTP_201_CREATED)
async def ask_question(code: str, body: QuestionIn, request: Request, db: DbSession) -> PublicOrderOut:
    """Khách bấm «Hỏi về đơn này» → việc chờ chị (chị ghi câu trả lời rồi duyệt để gửi khách)."""
    await ratelimit.limit(f"orders:question:{ratelimit.client_ip(request)}", 10, 600)
    order = await _public_order(db, code, body.t)
    ev = service.add_event(
        db, order, "customer_question", "Bạn đã hỏi chị về đơn này", detail=body.message, actor=Actor.CUSTOMER
    )
    await db.flush()
    await control.propose(
        "orders.customer_question", f"Khách hỏi về đơn {order.code}: {body.message[:80]}",
        {"order_id": str(order.id), "question_id": str(ev.id), "reply": ""},
        {"order_code": order.code, "recipient": order.recipient_name, "phone": order.recipient_phone,
         "status": service.STATUS_LABELS[order.status], "question": body.message},
        db=db, summary="Chị ghi câu trả lời vào ô «reply» rồi duyệt để gửi khách.", ref_type="orders", ref_id=order.id,
        dedupe_key=f"question:{ev.id}", priority=7, ai_generated=False,
    )  # fmt: skip
    return await public.public_view(db, order)


@store.post("/{code}/address", response_model=PublicOrderOut)
async def change_address(code: str, body: AddressChangeIn, db: DbSession) -> PublicOrderOut:
    """Khách đổi địa chỉ khi đơn chưa giao cho hãng vận chuyển."""
    order = await _public_order(db, code, body.t, lock=True)
    view = await public.public_view(db, order)
    if not view.can_change_address:
        raise Conflict("Đơn đã giao cho hãng vận chuyển, bạn nhắn chị để đổi địa chỉ nhé.", code="address_locked")
    addr = _address(body)
    if not (addr.get("address_line") and addr.get("province")):
        raise BadRequest("Bạn ghi đủ số nhà, đường và tỉnh/thành giúp mình.")
    old = ", ".join(x for x in (order.address_line, order.ward, order.district, order.province) if x)
    for k in ("address_line", "ward", "district", "province"):
        setattr(order, k, addr.get(k))
    order.address_codes = {}
    if body.recipient_name:
        order.recipient_name = body.recipient_name
    new = ", ".join(x for x in (order.address_line, order.ward, order.district, order.province) if x)
    service.add_event(
        db,
        order,
        "address_changed",
        "Bạn đã đổi địa chỉ nhận hàng",
        detail=new,
        actor=Actor.CUSTOMER,
        data={"from": old, "to": new},
    )
    await db.flush()
    return await public.public_view(db, order)


@store.post("/{code}/returns", response_model=PublicOrderOut, status_code=status.HTTP_201_CREATED)
async def request_return(code: str, body: PublicReturnIn, db: DbSession) -> PublicOrderOut:
    order = await _public_order(db, code, body.t, lock=True)
    item_id = None
    if body.order_item_index is not None:
        if body.order_item_index >= len(order.items):
            raise BadRequest("Dòng hàng không có trong đơn.")
        item_id = order.items[body.order_item_index].id
    await returns.open_return(
        db, order, kind=body.kind, reason=body.reason, description=body.description, quantity=body.quantity,
        order_item_id=item_id, actor=Actor.CUSTOMER,
    )  # fmt: skip
    return await public.public_view(db, order)


# ======================================================================================================================
# desk — chị
# ======================================================================================================================


@desk.get("", response_model=Paginated[OrderListItem])
async def list_orders(
    _: CurrentUser, db: DbSession, page: Page, nhom: StatusGroup | None = None, q: str | None = None,
    channel: Channel | None = None, drop_id: uuid.UUID | None = None,
) -> Paginated[OrderListItem]:  # fmt: skip
    """g1: đơn mọi kênh ở một chỗ, lọc theo nhóm trạng thái, tìm theo mã / tên / số điện thoại."""
    return await service.list_orders(
        db, page, group=None if nhom == "tat_ca" else nhom, q=q, channel=channel, drop_id=drop_id
    )


@desk.get("/counts", response_model=OrderCounts)
async def order_counts(_: CurrentUser, db: DbSession) -> OrderCounts:
    return OrderCounts(**await service.counts(db))


@desk.post("", response_model=OrderDetailOut, status_code=status.HTTP_201_CREATED)
async def create_manual(body: ManualOrderIn, user: CurrentUser, db: DbSession) -> OrderDetailOut:
    """g1: chị tạo đơn tay (khách đặt qua điện thoại, gặp trực tiếp, tin nhắn...)."""
    overrides = {i: ln.unit_price_vnd for i, ln in enumerate(body.items) if ln.unit_price_vnd is not None}
    res = await service.create_order(
        db, lines=list(body.items), name=body.name, phone=body.phone, address=_address(body),
        payment_method=body.payment_method, channel=body.channel,
        opts=service.ResolveOptions(store=False, price_overrides=overrides), shipping_fee_vnd=body.shipping_fee_vnd,
        discount_vnd=body.discount_vnd, customer_note=body.customer_note, internal_note=body.internal_note,
        actor=Actor(user.role.value), already_paid=body.already_paid, user=user,
    )  # fmt: skip
    return await views.order_detail(db, res.order)


@desk.get("/catalog", response_model=list[SellableProduct])
async def sellable(_: CurrentUser, db: DbSession) -> list[SellableProduct]:
    """Món chị chọn được khi tạo đơn tay: giá bán, đợt còn nhận đơn (kèm suất còn lại), tồn giữ sẵn."""
    from app.modules.catalog.models import DropStatus, ProductStatus, SaleMode

    products = list(
        (
            await db.execute(
                select(Product)
                .where(Product.status.in_((ProductStatus.PUBLISHED, ProductStatus.PAUSED)))
                .order_by(Product.name)
            )
        ).scalars()
    )
    images = await refs.primary_images(db, [p.id for p in products])
    open_drops = list(
        (
            await db.execute(
                select(Drop).where(Drop.status.in_((DropStatus.OPEN, DropStatus.SCHEDULED, DropStatus.CLOSED)))
            )
        ).scalars()
    )
    out = []
    for p in products:
        drops_ = []
        for d in open_drops:
            di = next((x for x in d.items if x.product_id == p.id and x.variant_id is None), None)
            if di is None:
                continue
            avail = (
                None
                if di.slots_total is None
                else max(0, di.slots_total - di.slots_reserved - await service.pending_drop_qty(db, di.id))
            )
            drops_.append(
                SellableDrop(
                    drop_id=d.id,
                    code=d.code,
                    status=d.status.value,
                    price_vnd=di.price_vnd or p.price_vnd,
                    available=avail,
                )
            )
        stock = None
        if p.sale_mode in (SaleMode.IN_STOCK, SaleMode.BOTH):
            inv = await refs.inventory_for(db, p.id, None)
            stock = (
                0
                if inv is None
                else max(0, inv.on_hand - inv.reserved - await service.pending_stock_qty(db, p.id, None))
            )
        out.append(
            SellableProduct(
                product_id=p.id,
                name=p.name,
                slug=p.slug,
                price_vnd=p.price_vnd,
                sale_mode=p.sale_mode.value,
                image_url=images.get(p.id),
                stock_available=stock,
                drops=drops_,
            )
        )
    return out


@desk.get("/drops", response_model=list[DropOverview])
async def drop_overviews(_: CurrentUser, db: DbSession) -> list[DropOverview]:
    """g3: các đợt đang mở / đã chốt / hàng đang về — suất, doanh thu, số lượng theo món, lô hàng."""
    return [await drops.overview(db, d) for d in await drops.active_drops(db)]


@desk.get("/drops/{drop_id}", response_model=DropOverview)
async def drop_overview(drop_id: uuid.UUID, _: CurrentUser, db: DbSession) -> DropOverview:
    d = await db.get(Drop, drop_id)
    if d is None:
        raise NotFound("Không tìm thấy đợt.")
    return await drops.overview(db, d)


@desk.get("/payments", response_model=Paginated[PaymentRowOut])
async def list_payments(
    _: CurrentUser, db: DbSession, page: Page, status_: PaymentStatus | None = Query(None, alias="status")
) -> Paginated[PaymentRowOut]:
    q = select(Payment).order_by(Payment.received_at.desc())
    if status_:
        q = q.where(Payment.status == status_)
    res = await paginate(db, q, page)
    return Paginated[PaymentRowOut](
        items=await views.payment_rows(db, list(res.items)),
        total=res.total,
        page=res.page,
        size=res.size,
        pages=res.pages,
    )


async def _payment(db: DbSession, payment_id: uuid.UUID) -> Payment:
    p = await db.get(Payment, payment_id, with_for_update=True)
    if p is None:
        raise NotFound("Không thấy khoản tiền.")
    return p


@desk.post("/payments/simulate", response_model=list[PaymentRowOut])
async def simulate_transfer(body: SimulateTransferIn, _: CurrentUser, db: DbSession) -> list[PaymentRowOut]:
    """Chỉ khi dùng thanh toán giả (mock) ở dev/test: giả lập khách chuyển khoản để chạy thử luồng khớp tiền."""
    if not settings.allows_simulation:
        raise NotFound("Không có đường dẫn này.")
    driver = get_driver("payments")
    if driver.name != "mock":
        raise BadRequest("Chỉ giả lập được khi dùng thanh toán giả.")
    got = await payments.ingest_transfers(db, "mock", [driver.simulate_transfer(body.amount_vnd, body.content)])
    return await views.payment_rows(db, got)


@desk.post("/payments/{payment_id}/match", response_model=PaymentRowOut)
async def match_payment(payment_id: uuid.UUID, body: PaymentMatchIn, user: OwnerUser, db: DbSession) -> PaymentRowOut:
    p = await _payment(db, payment_id)
    if p.status not in (PaymentStatus.NEEDS_REVIEW, PaymentStatus.RECEIVED, PaymentStatus.IGNORED):
        raise Conflict("Khoản tiền này đã khớp xong.")
    payload = {"payment_id": str(p.id), "kind": "unmatched", "decision": "match", "order_code": body.order_code}
    if p.order_id:
        o = await db.get(Order, p.order_id)
        if o and normalize_order_code(body.order_code) == o.code:
            payload = {**payload, "kind": "underpaid", "decision": "accept"}
    await payments.resolve_review(db, payload, user=user)
    await control.cancel_pending(db, action=payments.REVIEW_ACTION, dedupe_key=f"payment:{p.id}")
    await control.audit(
        db,
        "orders.payment_matched",
        user=user,
        entity_type="payments",
        entity_id=p.id,
        summary=f"Khớp tay vào {body.order_code}",
    )
    return (await views.payment_rows(db, [p]))[0]


@desk.post("/payments/{payment_id}/ignore", response_model=PaymentRowOut)
async def ignore_payment(payment_id: uuid.UUID, user: OwnerUser, db: DbSession) -> PaymentRowOut:
    p = await _payment(db, payment_id)
    if p.order_id and p.status == PaymentStatus.MATCHED:
        raise Conflict("Khoản tiền đã khớp đơn, không bỏ qua được.")
    await payments.resolve_review(db, {"payment_id": str(p.id), "decision": "ignore"}, user=user)
    await control.cancel_pending(db, action=payments.REVIEW_ACTION, dedupe_key=f"payment:{p.id}")
    return (await views.payment_rows(db, [p]))[0]


@desk.get("/inventory", response_model=list[InventoryRow])
async def inventory(_: CurrentUser, db: DbSession) -> list[InventoryRow]:
    """g8: tồn món giữ sẵn (đọc từ catalog) trừ phần đơn chưa thanh toán đang giữ."""
    return await drops.inventory_rows(db)


@desk.get("/returns", response_model=Paginated[ReturnRowOut])
async def list_returns(_: CurrentUser, db: DbSession, page: Page, open_only: bool = True) -> Paginated[ReturnRowOut]:
    q = (
        select(Return, Order.code, Order.recipient_name)
        .join(Order, Order.id == Return.order_id)
        .order_by(Return.created_at.desc())
    )
    if open_only:
        q = q.where(Return.status.in_(returns.OPEN_STATUSES))
    res = await paginate(db, q, page, scalars=False)
    items = [
        ReturnRowOut(**ReturnOut.model_validate(r).model_dump(), order_code=code, recipient_name=name)
        for r, code, name in res.items
    ]
    return Paginated[ReturnRowOut](items=items, total=res.total, page=res.page, size=res.size, pages=res.pages)


@desk.post("/returns/{return_id}/received", response_model=ReturnOut)
async def return_received(return_id: uuid.UUID, user: OwnerUser, db: DbSession) -> Return:
    r = await db.get(Return, return_id, with_for_update=True)
    if r is None:
        raise NotFound("Không thấy yêu cầu đổi trả.")
    return await returns.mark_received(db, r, user=user)


@desk.get("/templates", response_model=TemplatesOut)
async def get_templates(_: CurrentUser, db: DbSession) -> TemplatesOut:
    return TemplatesOut(
        templates=await notify.get_templates(db), defaults=notify.DEFAULT_TEMPLATES, labels=notify.TEMPLATE_LABELS,
        placeholders=notify.PLACEHOLDERS, channels=await notify.channel_status(db),
        failed=await notify.recent_failures(db),
    )  # fmt: skip


@desk.put("/templates", response_model=TemplatesOut)
async def put_templates(body: TemplatesIn, user: OwnerUser, db: DbSession) -> TemplatesOut:
    """g5: chị sửa mẫu tin. Mẫu trùng câu mặc định hoặc để trống thì không lưu (dùng mặc định)."""
    saved: dict[str, str] = {}
    for k, v in body.templates.items():
        if k not in notify.DEFAULT_TEMPLATES:
            raise BadRequest(f"Không có mẫu «{k}».")
        v = v.strip()
        if not v or v == notify.DEFAULT_TEMPLATES[k]:
            continue
        if len(v) > 1000:
            raise BadRequest("Mẫu tin quá dài (tối đa 1000 ký tự).")
        try:
            notify.render(v, {})
        except (ValueError, IndexError) as e:
            raise BadRequest(f"Mẫu «{notify.TEMPLATE_LABELS[k]}» viết sai chỗ ngoặc nhọn {{…}}.") from e
        saved[k] = v
    await control.set_setting(db, "orders.notify_templates", saved, user)
    return await get_templates(user, db)


@desk.get("/marketplaces/listings", response_model=list[ListingRow])
async def listings(_: CurrentUser, db: DbSession) -> list[ListingRow]:
    rows = (
        await db.execute(
            select(MarketplaceListing, Product.name)
            .join(Product, Product.id == MarketplaceListing.product_id)
            .order_by(Product.name)
        )
    ).all()
    return [ListingRow(**MarketplaceListingOut.model_validate(r).model_dump(), product_name=name) for r, name in rows]


@desk.post("/marketplaces/{mk}/sync-products", response_model=MarketplaceSyncOut)
async def sync_products(mk: Channel, _: CurrentUser, db: DbSession) -> MarketplaceSyncOut:
    """g9: đẩy món giữ sẵn + số tồn lên sàn."""
    return await marketplace.sync_products(db, mk)


@desk.post("/marketplaces/{mk}/pull-orders", response_model=MarketplaceSyncOut)
async def pull_orders(mk: Channel, _: CurrentUser, db: DbSession) -> MarketplaceSyncOut:
    """g9: kéo đơn sàn về danh sách chung (không sinh trùng)."""
    return await marketplace.pull_orders(db, mk)


@desk.post("/marketplaces/{mk}/simulate", response_model=MarketplaceSyncOut)
async def simulate_marketplace(
    mk: Channel, body: SimulateMarketplaceOrderIn, _: CurrentUser, db: DbSession
) -> MarketplaceSyncOut:
    """Chỉ với sàn giả (mock) ở dev/test: giả lập một đơn trên sàn rồi kéo về."""
    if not settings.allows_simulation:
        raise NotFound("Không có đường dẫn này.")
    p = await db.get(Product, body.product_id)
    if p is None:
        raise NotFound("Không thấy sản phẩm.")
    await marketplace.simulate(db, mk, p, body.quantity)
    return await marketplace.pull_orders(db, mk)


@desk.post("/shipments", response_model=ShipmentsResultOut)
async def create_shipments(body: CreateShipmentsIn, _: CurrentUser, db: DbSession) -> ShipmentsResultOut:
    """g4: tạo vận đơn từng đơn hoặc hàng loạt (qua control.propose — mặc định AI tự làm)."""
    return ShipmentsResultOut(
        results=await shipping.ship_orders(db, body.order_ids, driver=body.driver, service_key=body.service)
    )


@desk.get("/labels", response_model=list[LabelOut])
async def get_labels(
    _: CurrentUser, db: DbSession, ids: list[uuid.UUID] = Query(min_length=1, max_length=50)
) -> list[LabelOut]:
    """Dữ liệu in nhãn A6 cho các đơn đã có vận đơn."""
    return await shipping.labels(db, ids)


async def _shipment(db: DbSession, shipment_id: uuid.UUID) -> Shipment:
    sh = await db.get(Shipment, shipment_id, with_for_update=True)
    if sh is None:
        raise NotFound("Không thấy vận đơn.")
    return sh


async def _shipment_out(db: DbSession, sh: Shipment) -> ShipmentWithEvents:
    from app.modules.orders.models import ShipmentEvent

    evs = (
        await db.execute(
            select(ShipmentEvent).where(ShipmentEvent.shipment_id == sh.id).order_by(ShipmentEvent.occurred_at.desc())
        )
    ).scalars()
    return ShipmentWithEvents(
        **ShipmentOut.model_validate(sh).model_dump(), events=[ShipmentEventOut.model_validate(e) for e in evs]
    )


@desk.post("/shipments/{shipment_id}/sync", response_model=ShipmentWithEvents)
async def sync_shipment(shipment_id: uuid.UUID, _: CurrentUser, db: DbSession) -> ShipmentWithEvents:
    sh = await _shipment(db, shipment_id)
    await shipping.sync_shipment(db, sh)
    return await _shipment_out(db, sh)


@desk.post("/shipments/{shipment_id}/cancel", response_model=ShipmentWithEvents)
async def cancel_shipment(shipment_id: uuid.UUID, _: CurrentUser, db: DbSession) -> ShipmentWithEvents:
    sh = await shipping.cancel_shipment(db, await _shipment(db, shipment_id))
    return await _shipment_out(db, sh)


@desk.get("/{order_id}", response_model=OrderDetailOut)
async def get_order(order_id: uuid.UUID, _: CurrentUser, db: DbSession) -> OrderDetailOut:
    return await views.order_detail(db, await service.get_order(db, order_id))


@desk.patch("/{order_id}", response_model=OrderDetailOut)
async def patch_order(order_id: uuid.UUID, body: OrderPatchIn, user: CurrentUser, db: DbSession) -> OrderDetailOut:
    order = await service.get_order(db, order_id, lock=True)
    data = body.model_dump(exclude_unset=True)
    addr_keys = {"address_line", "ward", "district", "province", "recipient_name", "recipient_phone"}
    if addr_keys & data.keys() and order.status not in service.ADDRESS_EDITABLE:
        raise Conflict("Đơn đã giao cho hãng vận chuyển, không đổi người nhận / địa chỉ được nữa.")
    if data.get("recipient_phone"):
        data["recipient_phone"] = normalize_phone(data["recipient_phone"])
    changed = []
    for k, v in data.items():
        if getattr(order, k) != v:
            setattr(order, k, v)
            changed.append(k)
    if addr_keys & set(changed):
        order.address_codes = {}
        service.add_event(
            db,
            order,
            "address_changed",
            "Chị đã cập nhật người nhận / địa chỉ",
            actor=Actor(user.role.value),
            visible=False,
        )
    await db.flush()
    return await views.order_detail(db, order)


@desk.post("/{order_id}/cancel", response_model=OrderDetailOut)
async def cancel(order_id: uuid.UUID, body: CancelIn, user: OwnerUser, db: DbSession) -> OrderDetailOut:
    order = await service.get_order(db, order_id, lock=True)
    await service.cancel_order(
        db, order, body.reason, actor=Actor.OWNER, notify_customer=body.notify_customer, user=user
    )
    return await views.order_detail(db, order)


@desk.post("/{order_id}/payments", response_model=OrderDetailOut, status_code=status.HTTP_201_CREATED)
async def add_payment(order_id: uuid.UUID, body: ManualPaymentIn, user: OwnerUser, db: DbSession) -> OrderDetailOut:
    """Chị ghi nhận tiền nhận tay (tiền mặt / chuyển khoản không qua cổng)."""
    order = await service.get_order(db, order_id, lock=True)
    await payments.record_manual(db, order, body.amount_vnd, PaymentMethod(body.method), note=body.note, user=user)
    return await views.order_detail(db, order)


@desk.post("/{order_id}/confirm-draft", response_model=OrderDetailOut)
async def confirm_draft(order_id: uuid.UUID, body: DraftConfirmIn, user: CurrentUser, db: DbSession) -> OrderDetailOut:
    """g6: chị điền nốt thông tin rồi chốt đơn nháp (thay cho duyệt ở hàng chờ)."""
    order = await service.get_order(db, order_id, lock=True)
    await drafts.confirm(db, order, body, user=user)
    await control.cancel_pending(db, action=drafts.CONFIRM_ACTION, ref_type="orders", ref_id=order.id)
    await control.audit(
        db,
        "orders.draft_confirmed",
        user=user,
        entity_type="orders",
        entity_id=order.id,
        summary=f"Chốt đơn nháp {order.code}",
    )
    return await views.order_detail(db, order)


@desk.get("/{order_id}/shipping-quotes", response_model=dict[str, Any])
async def shipping_quotes(order_id: uuid.UUID, _: CurrentUser, db: DbSession) -> dict[str, Any]:
    order = await service.get_order(db, order_id)
    options, best, reason = await shipping.quote_for_order(db, order)
    return {
        "options": [ShippingOption.model_validate(o).model_dump(mode="json") for o in options],
        "recommended": best.model_dump(mode="json") if best else None,
        "reason": reason,
    }


@desk.post("/{order_id}/returns", response_model=OrderDetailOut, status_code=status.HTTP_201_CREATED)
async def open_return(order_id: uuid.UUID, body: DeskReturnIn, user: CurrentUser, db: DbSession) -> OrderDetailOut:
    order = await service.get_order(db, order_id, lock=True)
    await returns.open_return(
        db, order, kind=body.kind, reason=body.reason, description=body.description, quantity=body.quantity,
        order_item_id=body.order_item_id, actor=Actor(user.role.value), user=user,
    )  # fmt: skip
    return await views.order_detail(db, order)


# ======================================================================================================================
# hooks — webhook từ bên ngoài (tự kiểm chữ ký / khoá)
# ======================================================================================================================


def _allowed(kind: str, name: str) -> bool:
    if name == "mock":  # webhook giả lập: chỉ dev/test, production luôn 404 dù driver đang là mock
        return settings.allows_simulation
    return name == getattr(settings, f"{kind}_driver", "mock")


@hooks.post("/payments/{provider}", response_model=WebhookAck)
async def payments_webhook(provider: str, request: Request, db: DbSession) -> WebhookAck:
    """g2: khoản chuyển tới (SePay: `/api/hooks/payments/sepay`). Trả `{"success": true}` theo yêu cầu của SePay."""
    if provider not in ("mock", "sepay") or not _allowed("payments", provider):
        raise NotFound("Không có webhook này.")
    body = await request.body()
    transfers = await get_driver("payments", provider).parse_webhook(dict(request.headers), body)
    got = await payments.ingest_transfers(db, provider, transfers)
    return WebhookAck(success=True, received=len(got))


@hooks.post("/shipping/{carrier}", response_model=WebhookAck)
async def shipping_webhook(carrier: str, request: Request, db: DbSession) -> WebhookAck:
    """g4: trạng thái vận đơn từ hãng (GHN, GHTK...)."""
    if carrier not in ("mock", "ghn", "ghtk") or not (
        _allowed("shipping", carrier) or (carrier != "mock" and carrier in (await shipping.carrier_drivers(db)))
    ):
        raise NotFound("Không có webhook này.")
    headers = {**dict(request.headers), **{f"x-query-{k}": v for k, v in request.query_params.items()}}
    evs = await get_driver("shipping", carrier).parse_webhook(headers, await request.body())
    n = await shipping.handle_webhook(db, carrier, evs)
    return WebhookAck(success=True, received=n)
