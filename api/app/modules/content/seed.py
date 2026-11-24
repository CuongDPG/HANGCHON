"""Dữ liệu mẫu cho xưởng nội dung (idempotent): vài sản phẩm đã lên web (tên món, khách đều là ví dụ), một đợt đang mở,
bản nháp cho mọi kênh, vài bài đã đăng tuần trước có số liệu và đơn gắn theo mã bài, hồ sơ giọng, kịch bản live.

Chạy: `uv run python -c "import asyncio; from app.modules.content.seed import main; asyncio.run(main())"`
(sau `uv run python -m app.seed` để có tài khoản chị). Nên chạy với AI_PROVIDER=fake để không tốn tiền."""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.enums import Channel
from app.core.storage import get_storage
from app.core.timeutil import VN_TZ, local_today, now_utc
from app.modules.catalog.models import Drop, DropItem, DropStatus, Product, ProductImage, ProductStatus
from app.modules.content import livestream, publishing, service, voice
from app.modules.content.channels import DEFAULT_TIMES
from app.modules.content.models import (
    ContentDraft,
    DraftStatus,
    LivestreamScript,
    PostMetric,
    PostStatus,
    ScheduledPost,
)
from app.modules.content.schedule import src_code
from app.modules.control.models import User, UserRole

log = logging.getLogger("app.content.seed")

PRODUCTS = [
    {
        "slug": "demo-binh-giu-nhiet-480",
        "name": "Bình giữ nhiệt 480 ml",
        "subtitle": "Inox 304, nắp tháo rời rửa được",
        "price_vnd": 385_000,
        "compare_at_price_vnd": 450_000,
        "trial_days": 21,
        "considered_count": 5,
        "reason_selected": "Sáng pha trà, 5 giờ chiều vẫn còn ấm. Nắp tháo rời nên rửa xong không còn mùi.",
        "not_satisfied": "Hơi nặng khi bỏ túi xách nhỏ.",
        "specs": [{"label": "Dung tích", "value": "480 ml"}, {"label": "Chất liệu", "value": "Inox 304"}],
        "color": (46, 63, 143),
    },
    {
        "slug": "demo-gia-phoi-chu-x",
        "name": "Giá phơi chữ X gấp gọn",
        "subtitle": "Phơi chăn mùa đông không võng",
        "price_vnd": 520_000,
        "compare_at_price_vnd": None,
        "trial_days": 14,
        "considered_count": 4,
        "reason_selected": "Phơi chăn mùa đông không võng. Gấp lại dày 6 cm, dựng gọn sau cửa.",
        "not_satisfied": "Chân hơi trơn trên sàn gạch bóng.",
        "specs": [{"label": "Gấp gọn", "value": "dày 6 cm"}, {"label": "Tải trọng", "value": "15 kg"}],
        "color": (92, 110, 88),
    },
    {
        "slug": "demo-hop-com-inox-3-ngan",
        "name": "Hộp cơm inox 3 ngăn",
        "subtitle": "Nắp kín, mang canh không đổ",
        "price_vnd": 245_000,
        "compare_at_price_vnd": 290_000,
        "trial_days": 30,
        "considered_count": 6,
        "reason_selected": "Mang đi làm cả tháng, nắp kín không đổ canh. Ba ngăn tách riêng, không lẫn mùi.",
        "not_satisfied": "Không dùng được lò vi sóng.",
        "specs": [{"label": "Chất liệu", "value": "Inox 304"}, {"label": "Số ngăn", "value": "3"}],
        "color": (150, 98, 60),
    },
]

VOICE_SAMPLES = [
    "Cả nhà ơi, mình mới thử cái giá phơi này 2 tuần. Phơi chăn mùa đông không võng. Gấp lại dày 6 cm, dựng sau cửa. "
    "Ai cần nhắn mình nha?",
    "Mình dùng hộp cơm này mang đi làm cả tháng. Nắp kín, không đổ canh. Mỗi tội không cho vào lò vi sóng được. "
    "Cả nhà thấy sao?",
    "Mình không thích nói quá. Món nào mình giữ lại là vì dùng thật thấy ổn, món nào chưa ưng mình nói luôn.",
]


def _image(text: str, color: tuple[int, int, int], i: int) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (800, 800), (246, 246, 242))
    d = ImageDraw.Draw(img)
    shade = tuple(min(255, c + 30 * i) for c in color)
    d.rounded_rectangle((180, 140 + 20 * i, 620, 660), radius=24, fill=shade)
    d.ellipse((330, 90 + 20 * i, 470, 200 + 20 * i), fill=tuple(max(0, c - 30) for c in color))
    from app.modules.content.video import _font

    d.text((40, 740), f"Ảnh minh hoạ · {text} · {i + 1}", fill=(28, 29, 34), font=_font(22))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


async def _products(db: AsyncSession) -> list[Product]:
    out = []
    storage = get_storage()
    for spec in PRODUCTS:
        p = await db.scalar(select(Product).where(Product.slug == spec["slug"]))
        if p is None:
            data = {k: v for k, v in spec.items() if k != "color"}
            p = Product(**data, status=ProductStatus.PUBLISHED, published_at=now_utc() - timedelta(days=10))
            db.add(p)
            await db.flush()
            for i in range(4):
                key = f"public/demo/content/{spec['slug']}-{i}.png"
                if not await storage.exists(key):
                    await storage.put(key, _image(spec["name"], spec["color"], i), "image/png")
                db.add(
                    ProductImage(
                        product_id=p.id,
                        original_key=key,
                        position=i,
                        is_primary=i == 0,
                        alt=None if i else f"{spec['name']} — ảnh chị chụp",
                    )
                )
            await db.flush()
            await db.refresh(p)
        out.append(p)
    return out


async def _drop(db: AsyncSession, products: list[Product]) -> Drop:
    d = await db.scalar(select(Drop).where(Drop.code == "DEMO12"))
    if d is None:
        d = Drop(
            code="DEMO12",
            slug="demo-dot-12",
            title="Đợt 12: đồ bếp đã thử",
            status=DropStatus.OPEN,
            opens_at=now_utc() - timedelta(days=1),
            closes_at=now_utc() + timedelta(days=3),
            deposit_pct=30,
            expected_arrival_date=(now_utc() + timedelta(days=18)).date(),
        )
        db.add(d)
        await db.flush()
        for i, p in enumerate(products[:2] + products[2:]):
            db.add(DropItem(drop_id=d.id, product_id=p.id, price_vnd=p.price_vnd, slots_total=40, position=i))
        await db.flush()
        await db.refresh(d)
    return d


def _at(days_ago: int, hm: tuple[int, int]) -> datetime:
    """Giờ đăng mặc định của kênh, `days_ago` ngày trước (giờ Việt Nam)."""
    return datetime.combine(local_today() - timedelta(days=days_ago), time(*hm), tzinfo=VN_TZ)


def _next_thursday_evening() -> datetime:
    today = local_today()
    return datetime.combine(today + timedelta(days=(3 - today.weekday()) % 7 or 7), time(20, 0), tzinfo=VN_TZ)


async def _demo_video(db: AsyncSession, product: Product, owner: User) -> int:
    """Clip mẫu dựng từ ảnh minh hoạ + một video AI dựng chờ chị xem (chỉ khi máy có ffmpeg)."""
    from app.modules.content import video
    from app.modules.content.models import MediaAsset, MediaPurpose

    if not video.ffmpeg_available() or await db.scalar(
        select(MediaAsset.id).where(MediaAsset.purpose == MediaPurpose.TRIAL_CLIP)
    ):
        return 0
    import tempfile
    from pathlib import Path

    storage = get_storage()
    keys = [i.original_key for i in sorted(product.images, key=lambda i: i.position)][:3]
    notes = ["Rót trà nóng vào bình buổi sáng", "Tháo nắp, rửa dưới vòi", "Mở nắp lúc 5 giờ chiều, còn ấm"]
    ids = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, key in enumerate(keys):
            img, out = Path(tmp) / f"{i}.png", Path(tmp) / f"{i}.mp4"
            img.write_bytes(await storage.get(key))
            await video._run("ffmpeg", "-y", "-loop", "1", "-i", str(img), "-t", "6", "-vf",
                             "scale=720:720,pad=720:1280:0:280:color=0xF6F6F2,format=yuv420p", "-r", "24",
                             "-c:v", "libx264", str(out))  # fmt: skip
            asset = await video.upload_clip(db, data=out.read_bytes(), content_type="video/mp4", filename=f"clip-{i}.mp4",
                                            product_id=product.id, note=notes[i], user=owner)  # fmt: skip
            ids.append(asset.id)
    planned = await video.plan_video(db, product_id=product.id, clip_ids=ids, notes=None, target_seconds=18, user=owner)
    await video.render_job(db, planned.id)
    return 1


async def seed_demo(db: AsyncSession) -> dict[str, int]:
    counts = {"products": 0, "drafts": 0, "published": 0, "livestreams": 0}
    owner = await db.scalar(select(User).where(User.role == UserRole.OWNER).limit(1))
    if owner is None:
        log.warning("Chưa có tài khoản chị — chạy `python -m app.seed` trước.")
        return counts
    already = await db.scalar(select(Product.id).where(Product.slug == PRODUCTS[0]["slug"]))
    products = await _products(db)
    counts["products"] = 0 if already else len(products)
    if already and await db.scalar(select(ContentDraft.id).where(ContentDraft.product_id == products[0].id).limit(1)):
        return counts  # đã có dữ liệu mẫu

    vp = await voice.learn(db, VOICE_SAMPLES, "Không dùng chữ «siêu phẩm»\nTránh viết hoa cả câu", owner)
    log.info("Giọng của chị: %s", vp.status)

    for p in products:  # đúng luồng thật: catalog phát product.published → content tạo bản → soạn
        await events.emit("product.published", {"product_id": str(p.id)}, db=db)
    drop = await _drop(db, products)
    await events.emit("drop.opened", {"drop_id": str(drop.id)}, db=db)
    await service.compose_pending(db)

    async def drafts_of(p: Product) -> dict[Channel, ContentDraft]:
        return {d.channel: d for d in await service.current_drafts(db, product_id=p.id)}

    counts["drafts"] = len(list((await db.execute(select(ContentDraft.id))).scalars()))

    # Bình giữ nhiệt: tuần trước đã đăng Facebook + Instagram + Threads (có số liệu, có đơn); TikTok đã đẩy nháp
    binh = await drafts_of(products[0])
    past_posts: list[ScheduledPost] = []
    for i, ch in enumerate((Channel.FACEBOOK, Channel.INSTAGRAM, Channel.THREADS, Channel.TIKTOK)):
        d = binh.get(ch)
        if d is None:
            continue
        post = await service.approve_draft(db, d, owner)
        when = _at(6 - i, DEFAULT_TIMES[ch])
        post.scheduled_at = when
        await db.flush()
        await publishing.publish_one(db, post)
        if post.status == PostStatus.PUBLISHED:
            post.published_at = when
            past_posts.append(post)
            counts["published"] += 1
    # Hộp cơm: Facebook đã đăng 3 ngày trước
    hop = await drafts_of(products[2])
    if Channel.FACEBOOK in hop:
        post = await service.approve_draft(db, hop[Channel.FACEBOOK], owner)
        post.scheduled_at = _at(3, DEFAULT_TIMES[Channel.FACEBOOK])
        await db.flush()
        await publishing.publish_one(db, post)
        post.published_at = post.scheduled_at
        past_posts.append(post)
        counts["published"] += 1
    # Giá phơi: Zalo đã duyệt chờ giờ; Facebook bị chèn lời nói quá → soát chưa đạt
    gia = await drafts_of(products[1])
    if Channel.ZALO_OA in gia:
        await service.approve_draft(db, gia[Channel.ZALO_OA], owner)
    if Channel.FACEBOOK in gia:
        fb = gia[Channel.FACEBOOK]
        await service.edit_draft(db, fb, {"body": fb.body + "\n\nGiá phơi tốt nhất thị trường, bền vĩnh viễn!"}, owner)
    await db.flush()

    # đơn mẫu gắn theo mã bài (đọc bởi f7) + số liệu
    from app.modules.orders.models import Order, OrderStatus

    plan = [(0, 3), (1, 1), (3, 2)]  # (bài, số đơn)
    n = 0
    for idx, k in plan:
        if idx >= len(past_posts):
            continue
        post = past_posts[idx]
        for _ in range(k):
            n += 1
            code = f"HCDEMO{n:04d}"
            if await db.scalar(select(Order.id).where(Order.code == code)):
                continue
            db.add(
                Order(
                    code=code,
                    recipient_name=f"Khách mẫu {n}",
                    recipient_phone=f"09000000{n:02d}",
                    placed_at=post.published_at + timedelta(hours=3),
                    status=OrderStatus.CONFIRMED,
                    total_vnd=385_000 if idx == 0 else 245_000,
                    subtotal_vnd=385_000 if idx == 0 else 245_000,
                    raw={"src": src_code(post), "demo": True},
                )
            )
    await db.flush()
    attrs = await publishing.attribution(db, past_posts)
    for i, post in enumerate(past_posts):
        orders, rev = attrs.get(post.id, (0, 0))
        reach = [2400, 1800, 650, 1300][i % 4]
        db.add(
            PostMetric(
                scheduled_post_id=post.id,
                captured_at=now_utc(),
                impressions=int(reach * 1.4),
                reach=reach,
                likes=reach // 12,
                comments=8 + 3 * i,
                shares=4 + i,
                saves=10 - i,
                clicks=40 + 30 * orders,
                video_views=0,
                orders_attributed=orders,
                revenue_attributed_vnd=rev,
            )
        )
    await db.flush()
    await publishing.learn(db)

    if not await db.scalar(select(LivestreamScript.id).limit(1)):
        await livestream.create(
            db,
            title="Live tối thứ Năm: Đợt 12",
            drop_id=drop.id,
            product_ids=[],
            minutes=30,
            scheduled_for=_next_thursday_evening(),
            instruction=None,
            user=owner,
        )
        counts["livestreams"] = 1
    counts["videos"] = await _demo_video(db, products[0], owner)
    remaining = await db.scalar(select(ContentDraft.id).where(ContentDraft.status == DraftStatus.DRAFTING).limit(1))
    if remaining:
        log.warning("Còn bản đang soạn: %s", remaining)
    return counts


async def main() -> None:
    from app.core.db import SessionLocal
    from app.core.discovery import discover_modules

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    discover_modules()
    async with SessionLocal() as db:
        counts = await seed_demo(db)
        await db.commit()
    log.info("Dữ liệu mẫu content: %s", counts)


if __name__ == "__main__":
    asyncio.run(main())
