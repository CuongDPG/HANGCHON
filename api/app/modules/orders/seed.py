"""Dữ liệu mẫu của orders để chạy thử (tên món, người, số điện thoại đều là ví dụ, không phải dữ liệu thật).

`await seed_demo(db)` — chạy lặp không sinh trùng. Tự tạo vài sản phẩm + một đợt đang mở (catalog), một đợt cũ đang
có lô hàng về (supply) để trang theo dõi đơn có đủ chặng, rồi vài đơn ở các trạng thái khác nhau.
Chạy tay: `uv run python -m app.modules.orders.seed`."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Actor, Channel
from app.core.timeutil import local_today, now_utc
from app.modules.catalog.models import Drop, DropItem, DropStatus, InventoryItem, Product, ProductStatus, SaleMode
from app.modules.orders import drops, payments, service
from app.modules.orders.models import Order, PaymentMethod
from app.modules.orders.schemas import CartLineIn
from app.modules.orders.util import code_suffix
from app.modules.supply.models import InboundShipment, InboundStatus, POKind, POStatus, PurchaseOrder

PRODUCTS = [
    # slug, tên, giá, cân nặng, cách bán, mô tả ngắn
    ("binh-giu-nhiet-480", "Bình giữ nhiệt 480 ml", 385_000, 380, SaleMode.DROP, "Giữ nóng 8 giờ, nắp bật một tay."),
    ("hop-gia-vi-6-ngan", "Hộp gia vị 6 ngăn", 245_000, 600, SaleMode.DROP, "Nắp trượt, muỗng gắn sẵn."),
    ("ke-up-bat-inox", "Kệ úp bát inox gấp gọn", 320_000, 1200, SaleMode.DROP, "Gấp phẳng khi không dùng."),
    ("khan-lau-soi-tre", "Khăn lau bếp sợi tre (bộ 3)", 89_000, 150, SaleMode.IN_STOCK, "Thấm nhanh, ít bám mùi."),
    ("moc-dan-tuong", "Móc dán tường chịu lực (bộ 6)", 65_000, 120, SaleMode.BOTH, "Dán gạch men, không cần khoan."),
]


async def _product(
    db: AsyncSession, slug: str, name: str, price: int, grams: int, mode: SaleMode, short: str
) -> Product:
    p = (await db.execute(select(Product).where(Product.slug == slug))).scalar_one_or_none()
    if p is None:
        p = Product(
            slug=slug, name=name, price_vnd=price, weight_grams=grams, sale_mode=mode, short_description=short,
            status=ProductStatus.PUBLISHED, published_at=now_utc(), sku=f"HC-{slug[:16].upper()}",
            landed_cost_vnd=int(price * 0.55), considered_count=12, trial_days=14,
        )  # fmt: skip
        db.add(p)
        await db.flush()
    return p


async def _drop(db: AsyncSession, code: str, **kw: Any) -> tuple[Drop, bool]:
    d = (await db.execute(select(Drop).where(Drop.code == code))).scalar_one_or_none()
    if d is not None:
        return d, False
    d = Drop(code=code, **kw)
    d.items = []
    db.add(d)
    await db.flush()
    return d, True


async def seed_demo(db: AsyncSession) -> dict[str, int]:
    counts = {"products": 0, "drops": 0, "orders": 0}
    products = {}
    for row in PRODUCTS:
        before = await db.scalar(select(Product.id).where(Product.slug == row[0]))
        products[row[0]] = await _product(db, *row)
        counts["products"] += 0 if before else 1

    today = local_today()
    # đợt cũ: đã chốt, hàng đang về
    d11, new11 = await _drop(
        db, "DOT-11", slug="dot-11-do-bep-nhat", title="Đợt 11 · Đồ bếp Nhật", status=DropStatus.OPEN,
        opens_at=now_utc() - timedelta(days=20), closes_at=now_utc() - timedelta(days=12),
        expected_arrival_date=today + timedelta(days=5),
    )  # fmt: skip
    if new11:
        counts["drops"] += 1
        d11.items.append(
            DropItem(product_id=products["hop-gia-vi-6-ngan"].id, price_vnd=235_000, slots_total=60, position=0)
        )
        await db.flush()
        po = PurchaseOrder(code="PO-DEMO-11", kind=POKind.BATCH, status=POStatus.PAID, drop_id=d11.id, currency="JPY")
        db.add(po)
        await db.flush()
        db.add(
            InboundShipment(
                purchase_order_id=po.id,
                code="Lô Osaka",
                status=InboundStatus.INTERNATIONAL_TRANSIT,
                eta=today + timedelta(days=5),
                milestones=[
                    {
                        "status": "ordered",
                        "at": (now_utc() - timedelta(days=11)).isoformat(),
                        "note": "Đã đặt nhà cung cấp",
                    },
                    {
                        "status": "at_agent_warehouse",
                        "at": (now_utc() - timedelta(days=4)).isoformat(),
                        "note": "Về kho bên mua hộ ở Osaka",
                    },
                    {
                        "status": "international_transit",
                        "at": (now_utc() - timedelta(days=1)).isoformat(),
                        "note": "Rời kho Osaka",
                    },
                ],
            )
        )
    # đợt đang mở
    d12, new12 = await _drop(
        db, "DOT-12", slug="dot-12-binh-giu-nhiet", title="Đợt 12 · Bình giữ nhiệt và đồ bếp", status=DropStatus.OPEN,
        opens_at=now_utc() - timedelta(days=2), closes_at=now_utc() + timedelta(days=2),
        expected_arrival_date=today + timedelta(days=17),
    )  # fmt: skip
    if new12:
        counts["drops"] += 1
        d12.items += [
            DropItem(product_id=products["binh-giu-nhiet-480"].id, price_vnd=385_000, slots_total=120, max_per_order=5, position=0),
            DropItem(product_id=products["ke-up-bat-inox"].id, price_vnd=320_000, slots_total=40, position=1),
            DropItem(product_id=products["moc-dan-tuong"].id, price_vnd=59_000, slots_total=None, position=2),
        ]  # fmt: skip
    for slug, on_hand, threshold in (("khan-lau-soi-tre", 9, 3), ("moc-dan-tuong", 4, 2)):
        pid = products[slug].id
        if not await db.scalar(select(InventoryItem.id).where(InventoryItem.product_id == pid)):
            db.add(
                InventoryItem(
                    product_id=pid,
                    on_hand=on_hand,
                    low_stock_threshold=threshold,
                    unit_cost_vnd=products[slug].landed_cost_vnd,
                )
            )
    await db.flush()

    if await db.scalar(select(Order.id).where(Order.raw["demo"].astext == "1").limit(1)):
        d11.status = DropStatus.ARRIVING
        return counts

    def line(slug: str, qty: int, drop: Drop | None = None) -> CartLineIn:
        return CartLineIn(product_id=products[slug].id, drop_id=drop.id if drop else None, quantity=qty)

    opts = service.ResolveOptions(store=False)
    demo = [
        # (tên, sđt, địa chỉ, tỉnh, dòng, cách trả, đã trả?)
        ("Nguyễn Thị Lan", "0900000101", "12 Ngõ Mẫu, phường Ví Dụ", "Hà Nội", [line("binh-giu-nhiet-480", 1, d12)], PaymentMethod.BANK_TRANSFER, False),
        ("Trần Văn Tùng", "0900000102", "45 Đường Thử, phường Mẫu", "TP. Hồ Chí Minh", [line("ke-up-bat-inox", 1, d12)], PaymentMethod.COD, False),
        ("Lê Minh Mai", "0900000103", "8 Phố Giả Định", "Đà Nẵng", [line("binh-giu-nhiet-480", 2, d12), line("moc-dan-tuong", 1, d12)], PaymentMethod.BANK_TRANSFER, True),
        ("Phạm Thu Hà", "0900000104", "3 Hẻm Minh Hoạ", "Cần Thơ", [line("hop-gia-vi-6-ngan", 1, d11)], PaymentMethod.BANK_TRANSFER, True),
        ("Đỗ Quang Huy", "0900000105", "21 Đường Ví Dụ", "Hải Phòng", [line("hop-gia-vi-6-ngan", 2, d11)], PaymentMethod.COD, False),
        ("Võ Ngọc Anh", "0900000106", "9 Ngõ Thử Nghiệm", "Hà Nội", [line("khan-lau-soi-tre", 2)], PaymentMethod.COD, False),
        ("Bùi Thanh Tâm", "0900000107", "77 Phố Mẫu", "Huế", [line("khan-lau-soi-tre", 1), line("moc-dan-tuong", 1)], PaymentMethod.BANK_TRANSFER, True),
    ]  # fmt: skip
    for name, phone, addr, prov, lines, method, paid in demo:
        res = await service.create_order(
            db, lines=lines, name=name, phone=phone, address={"address_line": addr, "province": prov},
            payment_method=method, channel=Channel.WEB, opts=opts, actor=Actor.CUSTOMER, raw={"demo": "1"},
        )  # fmt: skip
        o = res.order
        if paid:
            from app.integrations import get_driver

            driver = get_driver("payments")
            if getattr(driver, "name", "") == "mock":
                t = driver.simulate_transfer(service.amount_due(o), f"{o.transfer_content} chuyen tien")
                await payments.ingest_transfers(db, "mock", [t])
            else:
                await payments.record_manual(
                    db, o, service.amount_due(o), PaymentMethod.BANK_TRANSFER, note="Dữ liệu mẫu"
                )
        counts["orders"] += 1
    # một khoản chuyển sai nội dung để thử «khoản tiền cần xem»
    from app.integrations import get_driver

    driver = get_driver("payments")
    if getattr(driver, "name", "") == "mock":
        first = (
            await db.execute(select(Order).where(Order.raw["demo"].astext == "1").order_by(Order.created_at).limit(1))
        ).scalar_one()
        t = driver.simulate_transfer(150_000, f"chuyen tien {code_suffix(first.code)[:2]}")
        await payments.ingest_transfers(db, "mock", [t])
    d11.status = DropStatus.ARRIVING
    await db.flush()
    await drops.on_drop_closed(db, d11.id)
    return counts


async def main() -> None:
    from app.core.db import SessionLocal
    from app.core.discovery import discover_modules
    from app.seed import seed

    discover_modules()
    async with SessionLocal() as db:
        await seed(db)
        print(await seed_demo(db))
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
