"""Bán trên TikTok Shop, Shopee (g9): đẩy sản phẩm giữ sẵn + tồn lên sàn, kéo đơn sàn về cùng danh sách đơn.
Đơn sàn không sinh trùng nhờ khoá duy nhất (kênh, mã đơn sàn). Sàn thu hộ tiền → ghi khoản `marketplace`."""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.config import settings
from app.core.enums import Actor, Channel
from app.core.errors import BadRequest
from app.core.timeutil import now_utc
from app.integrations import get_driver
from app.integrations.base import IntegrationError
from app.integrations.marketplaces import MarketplaceOrder, MarketplaceProduct
from app.modules.catalog.models import Product, ProductStatus, SaleMode
from app.modules.orders import refs, service
from app.modules.orders.models import (
    FulfillmentSource,
    ListingStatus,
    MarketplaceListing,
    MatchMethod,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentDirection,
    PaymentMethod,
    PaymentStatus,
)
from app.modules.orders.schemas import MarketplaceSyncOut
from app.modules.orders.util import try_normalize_phone

log = logging.getLogger("app.orders.marketplace")

MARKETPLACES = (Channel.TIKTOK_SHOP, Channel.SHOPEE)


def driver_for(mk: Channel) -> Any:
    """Sàn giả khi MARKETPLACES_DRIVER=mock; còn lại dùng driver thật của đúng sàn đó (tiktok_shop / shopee)."""
    if settings.marketplaces_driver == "mock":
        return get_driver("marketplaces", "mock")
    return get_driver("marketplaces", mk.value)


def check_marketplace(mk: Channel) -> Channel:
    if mk not in MARKETPLACES:
        raise BadRequest("Chỉ hỗ trợ TikTok Shop và Shopee.")
    return mk


def sku_of(p: Product) -> str:
    return p.sku or f"HC{str(p.id).replace('-', '')[:10].upper()}"


async def sellable_products(db: AsyncSession) -> list[Product]:
    return list(
        (
            await db.execute(
                select(Product).where(
                    Product.status == ProductStatus.PUBLISHED, Product.sale_mode.in_((SaleMode.IN_STOCK, SaleMode.BOTH))
                )
            )
        ).scalars()
    )


async def available_stock(db: AsyncSession, p: Product) -> int:
    inv = await refs.inventory_for(db, p.id, None)
    if inv is None:
        return 0
    return max(0, inv.on_hand - inv.reserved - await service.pending_stock_qty(db, p.id, None))


async def sync_products(db: AsyncSession, mk: Channel) -> MarketplaceSyncOut:
    check_marketplace(mk)
    driver = driver_for(mk)
    out = MarketplaceSyncOut()
    products = await sellable_products(db)
    images = await refs.primary_images(db, [p.id for p in products])
    for p in products:
        listing = (
            await db.execute(
                select(MarketplaceListing).where(
                    MarketplaceListing.marketplace == mk, MarketplaceListing.product_id == p.id,
                    MarketplaceListing.variant_id.is_(None),
                )
            )
        ).scalar_one_or_none()  # fmt: skip
        if listing is None:
            listing = MarketplaceListing(marketplace=mk, product_id=p.id)
            db.add(listing)
        stock = await available_stock(db, p)
        sku = sku_of(p)
        try:
            ext = await driver.upsert_product(
                mk,
                MarketplaceProduct(
                    sku=sku, name=p.name, description=p.short_description or p.description or p.name,
                    price_vnd=p.price_vnd, stock=stock, image_urls=[images[p.id]] if p.id in images else [],
                    weight_grams=p.weight_grams, external_id=listing.external_id,
                ),
            )  # fmt: skip
        except IntegrationError as e:
            listing.status, listing.error = ListingStatus.ERROR, e.message
            out.errors.append(f"{p.name}: {e.message}")
            continue
        listing.external_id = ext
        listing.status = ListingStatus.ACTIVE if stock > 0 else ListingStatus.INACTIVE
        listing.price_vnd = p.price_vnd
        listing.synced_stock = stock
        listing.last_synced_at = now_utc()
        listing.error = None
        listing.data = {**(listing.data or {}), "sku": sku}
        out.synced += 1
    await db.flush()
    return out


async def _product_for_sku(db: AsyncSession, mk: Channel, sku: str) -> Product | None:
    listing = (
        await db.execute(
            select(MarketplaceListing).where(
                MarketplaceListing.marketplace == mk, MarketplaceListing.data["sku"].astext == sku
            )
        )
    ).scalar_one_or_none()
    if listing is not None:
        return await db.get(Product, listing.product_id)
    p = (await db.execute(select(Product).where(Product.sku == sku))).scalar_one_or_none()
    if p is not None:
        return p
    for cand in await sellable_products(db):
        if sku_of(cand) == sku:
            return cand
    return None


async def import_order(db: AsyncSession, mo: MarketplaceOrder) -> Order | None:
    """Một đơn sàn → một đơn trong danh sách chung. Đã có (cùng kênh + mã sàn) thì bỏ qua."""
    exists = await db.scalar(
        select(func.count()).where(Order.channel == mo.marketplace, Order.external_id == mo.external_id)
    )
    if exists:
        return None
    phone = try_normalize_phone(mo.buyer_phone) or (mo.buyer_phone or "")[:20]
    try:
        async with db.begin_nested():
            order = Order(
                code=await service._unique_code(db), channel=mo.marketplace, external_id=mo.external_id,
                status=OrderStatus.CONFIRMED, payment_method=PaymentMethod.MARKETPLACE,
                recipient_name=mo.buyer_name[:120], recipient_phone=phone, address_line=mo.address_line,
                province=mo.province, placed_at=mo.placed_at, confirmed_at=now_utc(), raw={"marketplace": mo.raw, "status": mo.status},
            )  # fmt: skip
            order.items = []
            for i, ln in enumerate(mo.lines):
                p = await _product_for_sku(db, mo.marketplace, ln.sku)
                order.items.append(
                    OrderItem(
                        position=i,
                        product_id=p.id if p else None,
                        fulfillment_source=FulfillmentSource.STOCK,
                        name=(p.name if p else ln.name)[:300],
                        sku=ln.sku,
                        quantity=ln.quantity,
                        unit_price_vnd=ln.unit_price_vnd,
                        line_total_vnd=ln.unit_price_vnd * ln.quantity,
                        unit_cost_vnd=p.landed_cost_vnd if p else None,
                    )
                )
            order.subtotal_vnd = sum(i.line_total_vnd for i in order.items)
            order.shipping_fee_vnd = mo.shipping_fee_vnd
            order.total_vnd = mo.total_vnd or order.subtotal_vnd + mo.shipping_fee_vnd
            db.add(order)
            await db.flush()
    except IntegrityError:  # hai lượt kéo đơn chạy cùng lúc
        return None
    if try_normalize_phone(mo.buyer_phone):
        c = await service.upsert_customer(db, phone, mo.buyer_name, mo.marketplace)
        order.customer_id = c.id
        c.order_count += 1
        c.last_order_at = order.placed_at
        c.first_order_at = c.first_order_at or order.placed_at
    channel_name = "TikTok Shop" if mo.marketplace == Channel.TIKTOK_SHOP else "Shopee"
    service.add_event(
        db, order, "placed", f"Đơn từ {channel_name}", detail=f"Mã đơn sàn {mo.external_id}", actor=Actor.CUSTOMER
    )
    if any(i.product_id is None for i in order.items):
        order.internal_note = "Có món trên sàn chưa khớp sản phẩm nào (kiểm SKU)."
    pay = Payment(
        order_id=order.id, direction=PaymentDirection.IN, method=PaymentMethod.MARKETPLACE, provider=mo.marketplace.value,
        external_id=f"order:{mo.external_id}", status=PaymentStatus.MATCHED, amount_vnd=order.total_vnd,
        received_at=mo.placed_at, matched_at=now_utc(), match_method=MatchMethod.AUTO_CODE, match_confidence=Decimal("1"),
        note="Sàn thu hộ",
    )  # fmt: skip
    db.add(pay)
    order.paid_vnd = order.total_vnd
    service.recompute_payment_state(order)
    await db.flush()
    await events.emit("order.created", {"order_id": str(order.id)}, db=db)
    await service.mark_paid(db, order, pay)
    await service.advance_after_confirm(db, order)
    return order


async def pull_orders(db: AsyncSession, mk: Channel) -> MarketplaceSyncOut:
    check_marketplace(mk)
    last = await db.scalar(select(func.max(Order.placed_at)).where(Order.channel == mk))
    since = last - timedelta(days=1) if last else None
    out = MarketplaceSyncOut()
    for mo in await driver_for(mk).fetch_orders(mk, since):
        if await import_order(db, mo):
            out.created_orders += 1
        else:
            out.skipped += 1
    return out


async def simulate(db: AsyncSession, mk: Channel, product: Product, quantity: int) -> MarketplaceOrder:
    driver = driver_for(mk)
    if getattr(driver, "name", "") != "mock":
        raise BadRequest("Chỉ giả lập được khi dùng sàn giả (mock).")
    return driver.simulate_order(check_marketplace(mk), sku_of(product), quantity, product.price_vnd)
