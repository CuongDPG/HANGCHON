"""Dữ liệu mẫu cho khu Khách (h4–h8): vài món, một đợt đang mở, khách, đơn, nhắc mua lại, mã giới thiệu, món đang thử.

Tên người, món hàng, số điện thoại đều là ví dụ (số 0900…). Chạy lặp lại không sinh trùng: mọi thứ khoá theo slug /
mã / số điện thoại. Chạy cùng hộp thư: `uv run python -m app.modules.inbox.seed`.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Channel, SourcePlatform
from app.core.security import random_token
from app.core.timeutil import now_utc
from app.modules.catalog.models import (
    Category,
    Drop,
    DropItem,
    DropStatus,
    InventoryItem,
    Product,
    ProductStatus,
)
from app.modules.crm import service
from app.modules.crm.models import (
    CustomerNote,
    GroupDigest,
    NoteKind,
    NoteSource,
    ReorderReminder,
    TesterInvite,
    TesterInviteStatus,
)
from app.modules.orders.models import Customer, CustomerIdentity, Order, OrderItem, OrderStatus, PaymentState
from app.modules.selection.models import NoteAuthor, TrialNote, TrialNoteKind
from app.modules.sourcing.models import Candidate, CandidateStage

PRODUCTS = [
    # slug, tên, giá, tồn, tiêu hao (ngày), mô tả ngắn, lý do chọn, điều chưa ưng
    ("binh-giu-nhiet-480ml", "Bình giữ nhiệt 480 ml", 385_000, 12, None,
     "Giữ nóng khoảng 9 tiếng, nắp không ám mùi, rửa được bằng tay",
     "Thử 5 chiếc trong 3 tuần, chiếc này giữ nóng lâu nhất và nắp không ám mùi cà phê.",
     "Hơi nặng khi đầy nước"),
    ("hop-com-inox-3-ngan", "Hộp cơm inox 3 ngăn", 245_000, None, None,
     "Inox 304, ba ngăn kín, dùng được lò hấp (không dùng lò vi sóng)",
     "Ngăn kín thật, mang canh không rỉ.", "Nắp hơi chặt lúc đầu"),
    ("khan-tam-cho-be", "Khăn tắm cho bé", 168_000, 20, None,
     "Cotton dày, thấm nhanh, qua 30 lần giặt vẫn mềm", "Mềm nhất trong 6 mẫu đã giặt thử.", "Lâu khô hơn khăn mỏng"),
    ("tui-loc-tra-giay-100", "Túi lọc trà giấy (100 cái)", 90_000, 40, 45,
     "Giấy không tẩy trắng, buộc dây, pha được 1 ấm nhỏ", "Không bục khi pha nước sôi.", "Hơi nhỏ với ấm lớn"),
    ("vien-tay-bon-cau-12", "Viên tẩy bồn cầu (hộp 12 viên)", 120_000, 30, 60,
     "Mỗi viên dùng khoảng 5 ngày, mùi nhẹ", "Mùi dễ chịu nhất trong 4 loại.", "Tan nhanh nếu nước cứng"),
]  # fmt: skip

CUSTOMERS = [
    # sđt, tên, email, định danh kênh
    ("0900000101", "Nguyễn Thu Hà", "thuha.demo@example.com", (Channel.FACEBOOK, "demo_psid_thuha")),
    ("0900000102", "Trần Minh", None, (Channel.ZALO_OA, "demo_zalo_minh")),
    ("0900000103", "Lê Ngọc", None, (Channel.INSTAGRAM, "demo_ig_ngoc")),
    ("0900000104", "Phạm Lan", "lan.demo@example.com", (Channel.ZALO_OA, "demo_zalo_lan")),
    ("0900000105", "Đỗ Khoa", None, (Channel.FACEBOOK, "demo_psid_khoa")),
    ("0900000106", "Vũ Mai", "mai.demo@example.com", (Channel.FACEBOOK, "demo_psid_mai")),
]

# đơn: mã, sđt, [(slug, sl)], trạng thái, cách đây (ngày), mã giới thiệu
ORDERS = [
    ("HCDEMO0001", "0900000101", [("binh-giu-nhiet-480ml", 1)], OrderStatus.COMPLETED, 80, None),
    ("HCDEMO0002", "0900000101", [("khan-tam-cho-be", 2)], OrderStatus.COMPLETED, 40, None),
    ("HCDEMO0003", "0900000101", [("binh-giu-nhiet-480ml", 1)], OrderStatus.DELIVERED, 6, None),
    ("HCDEMO0004", "0900000102", [("hop-com-inox-3-ngan", 1)], OrderStatus.DELIVERED, 2, None),
    ("HCDEMO0005", "0900000102", [("khan-tam-cho-be", 1)], OrderStatus.COMPLETED, 50, None),
    ("HCDEMO0006", "0900000103", [("hop-com-inox-3-ngan", 2)], OrderStatus.AWAITING_STOCK, 1, None),
    ("HCDEMO0007", "0900000104", [("tui-loc-tra-giay-100", 1)], OrderStatus.COMPLETED, 42, None),
    ("HCDEMO0008", "0900000104", [("vien-tay-bon-cau-12", 1)], OrderStatus.COMPLETED, 30, None),
    ("HCDEMO0009", "0900000104", [("binh-giu-nhiet-480ml", 1)], OrderStatus.COMPLETED, 90, None),
    ("HCDEMO0010", "0900000104", [("khan-tam-cho-be", 1)], OrderStatus.COMPLETED, 20, None),
    ("HCDEMO0011", "0900000106", [("tui-loc-tra-giay-100", 2)], OrderStatus.DELIVERED, 5, "LAN-DEMO"),
]


async def _products(db: AsyncSession) -> dict[str, Product]:
    cat = await db.scalar(select(Category).where(Category.slug == "tieu-hao"))
    out = {}
    for slug, name, price, stock, reorder, short, reason, not_ok in PRODUCTS:
        p = await db.scalar(select(Product).where(Product.slug == slug))
        if p is None:
            p = Product(
                slug=slug, name=name, price_vnd=price, status=ProductStatus.PUBLISHED, published_at=now_utc(),
                short_description=short, reason_selected=reason, not_satisfied=not_ok, is_consumable=bool(reorder),
                reorder_days=reorder, category_id=cat.id if (reorder and cat) else None, selected_count=1,
                considered_count=12, trial_days=21,
            )  # fmt: skip
            db.add(p)
            await db.flush()
            if stock is not None:
                db.add(InventoryItem(product_id=p.id, on_hand=stock))
        out[slug] = p
    await db.flush()
    return out


async def _drop(db: AsyncSession, products: dict[str, Product]) -> Drop:
    d = await db.scalar(select(Drop).where(Drop.code == "DOT-12-DEMO"))
    if d is None:
        d = Drop(
            code="DOT-12-DEMO", slug="dot-12", title="Đợt 12", status=DropStatus.OPEN, opens_at=now_utc(),
            closes_at=now_utc() + timedelta(days=2), expected_arrival_date=date.today() + timedelta(days=14),
            description="Hộp cơm inox về từ Quảng Châu",
        )  # fmt: skip
        db.add(d)
        await db.flush()
        db.add(
            DropItem(
                drop_id=d.id, product_id=products["hop-com-inox-3-ngan"].id, price_vnd=245_000, slots_total=120,
                slots_reserved=86,
            )
        )  # fmt: skip
        await db.flush()
    return d


async def _customers(db: AsyncSession) -> dict[str, Customer]:
    out = {}
    for phone, name, email, ident in CUSTOMERS:
        c = await db.scalar(select(Customer).where(Customer.phone == phone))
        if c is None:
            c = Customer(phone=phone, name=name, email=email, first_channel=ident[0])
            db.add(c)
            await db.flush()
            db.add(CustomerIdentity(customer_id=c.id, channel=ident[0], external_id=ident[1], display_name=name))
        out[phone] = c
    await db.flush()
    return out


async def _orders(db: AsyncSession, products: dict[str, Product], customers: dict[str, Customer], drop: Drop) -> None:
    now = now_utc()
    for code, phone, lines, status, ago, ref in ORDERS:
        if await db.scalar(select(Order.id).where(Order.code == code)):
            continue
        c = customers[phone]
        placed = now - timedelta(days=ago)
        delivered = status in (OrderStatus.DELIVERED, OrderStatus.COMPLETED)
        items = [
            OrderItem(
                product_id=products[s].id,
                name=products[s].name,
                quantity=q,
                unit_price_vnd=products[s].price_vnd,
                line_total_vnd=products[s].price_vnd * q,
                position=i,
            )
            for i, (s, q) in enumerate(lines)
        ]
        total = sum(i.line_total_vnd for i in items)
        o = Order(
            code=code, customer_id=c.id, channel=Channel.WEB, status=status, recipient_name=c.name or "Khách",
            recipient_phone=phone, subtotal_vnd=total, total_vnd=total, paid_vnd=total, placed_at=placed,
            payment_state=PaymentState.PAID, delivered_at=placed + timedelta(days=3) if delivered else None,
            referral_code=ref, drop_id=drop.id if any(s == "hop-com-inox-3-ngan" for s, _ in lines) else None,
        )  # fmt: skip
        o.items = items
        db.add(o)
        await db.flush()
    # thống kê trên hồ sơ khách (bảng của orders — chỉ dữ liệu mẫu mới ghi ở đây)
    for c in customers.values():
        orders = list((await db.execute(select(Order).where(Order.customer_id == c.id))).scalars())
        c.order_count = len(orders)
        c.total_spent_vnd = sum(o.total_vnd for o in orders)
        c.first_order_at = min((o.placed_at for o in orders), default=None)
        c.last_order_at = max((o.placed_at for o in orders), default=None)
    await db.flush()


async def _trial(db: AsyncSession, customers: dict[str, Customer]) -> None:
    cand = await db.scalar(select(Candidate).where(Candidate.source_external_id == "demo-binh-loc-2l"))
    if cand is None:
        cand = Candidate(
            title_vi="Bình lọc nước để bàn 2 lít", source_platform=SourcePlatform.TAOBAO,
            source_external_id="demo-binh-loc-2l", stage=CandidateStage.TRIAL,
            stage_changed_at=now_utc() - timedelta(days=6),
            main_image_url="https://placehold.co/800x800/E1E3EC/2E3F8F/png?text=Binh+loc",
        )  # fmt: skip
        db.add(cand)
        await db.flush()
        for day, text in (
            (2, "Lọc nhanh, nước hết mùi clo. Vòi hơi lỏng."),
            (5, "Lõi lọc vẫn trắng, rửa bình dễ. Nắp trên hơi kêu khi mở."),
        ):
            db.add(
                TrialNote(
                    candidate_id=cand.id, kind=TrialNoteKind.TEXT, author=NoteAuthor.OWNER, text=text,
                    recorded_at=now_utc() - timedelta(days=6 - day), trial_day=day,
                )
            )  # fmt: skip
    if not await db.scalar(select(TesterInvite.id).where(TesterInvite.candidate_id == cand.id)):
        lan, ha = customers["0900000104"], customers["0900000101"]
        db.add(
            TesterInvite(
                candidate_id=cand.id, customer_id=lan.id, token=random_token(18), status=TesterInviteStatus.FEEDBACK_RECEIVED,
                message="Lan dùng thử bình lọc cùng mình vài ngày nhé?", invited_at=now_utc() - timedelta(days=5),
                sample_sent_at=now_utc() - timedelta(days=4), feedback_at=now_utc() - timedelta(hours=5),
                feedback="Lọc nhanh, nước ngọt hơn hẳn. Bình hơi to so với bàn bếp nhà mình, vòi cũng lỏng như chị nói.",
                feedback_rating=4,
            )
        )  # fmt: skip
        db.add(
            TesterInvite(
                candidate_id=cand.id, customer_id=ha.id, token=random_token(18), status=TesterInviteStatus.SAMPLE_SENT,
                message="Hà dùng thử bình lọc cùng mình vài ngày nhé?", invited_at=now_utc() - timedelta(days=5),
                sample_sent_at=now_utc() - timedelta(days=4),
            )
        )  # fmt: skip
    await db.flush()


DIGEST_TEXT = """Lan: Hộp cơm inox nhà mình dùng 2 tuần rồi, giữ nóng tốt lắm mọi người
Hà: Hộp cơm inox có loại 2 ngăn không chị?
Minh: Đợt trước mình chờ hơi lâu, 3 tuần mới về
Ngọc: Bình giữ nhiệt màu xám xinh ghê
Mai: Bao giờ có túi lọc trà lại ạ?
Lan: Túi lọc trà pha nước sôi không bục, thích"""


async def seed_demo(db: AsyncSession) -> dict[str, Any]:
    products = await _products(db)
    drop = await _drop(db, products)
    customers = await _customers(db)
    await _orders(db, products, customers, drop)
    lan, ha = customers["0900000104"], customers["0900000101"]

    ref = await service.get_or_create_referral(db, lan.id)
    if ref.code != "LAN-DEMO" and not await db.scalar(select(type(ref).id).where(type(ref).code == "LAN-DEMO")):
        ref.code = "LAN-DEMO"
        await db.flush()
    mai_order = await db.scalar(select(Order).where(Order.code == "HCDEMO0011"))
    await service.record_referral(db, mai_order.id)
    await service.qualify_referral(db, mai_order.id)
    await service.get_or_create_referral(db, ha.id)

    for code in ("HCDEMO0007", "HCDEMO0008", "HCDEMO0011"):  # món tiêu hao đã giao → lịch nhắc
        o = await db.scalar(select(Order).where(Order.code == code))
        await service.schedule_reminders(db, o.id)
    first = await db.scalar(
        select(ReorderReminder).join(Order, Order.id == ReorderReminder.order_id).where(Order.code == "HCDEMO0007")
    )
    if first and str(first.status) == "scheduled":
        first.due_on = date.today()  # tới hạn hôm nay để thấy tin AI soạn
    await db.flush()
    await service.run_due(db)

    if not await db.scalar(
        select(CustomerNote.id).where(CustomerNote.customer_id == ha.id, CustomerNote.source == NoteSource.OWNER)
    ):
        db.add(
            CustomerNote(
                customer_id=ha.id, kind=NoteKind.PREFERENCE, body="Thích màu xám, hay mua làm quà", pinned=True
            )
        )
        db.add(CustomerNote(customer_id=lan.id, kind=NoteKind.NOTE, body="Khách quen từ đợt đầu, hay giới thiệu bạn"))
    await service.add_tag(db, lan.id, service.REGULAR_TAG)
    await service.add_tag(db, ha.id, "mua-lam-qua")

    if not await db.scalar(select(GroupDigest.id).limit(1)):
        await service.create_digest(db, DIGEST_TEXT, period_start=now_utc() - timedelta(days=1), period_end=now_utc())
    await _trial(db, customers)
    await service.draft_drop_announcement(db, drop.id)
    for c in customers.values():
        await service.refresh_profile(db, c.id)
    await db.flush()
    return {"products": len(products), "customers": len(customers), "drop": drop.title}
