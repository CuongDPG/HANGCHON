"""Dữ liệu khởi đầu: `uv run python -m app.seed` (chạy lại nhiều lần không sinh trùng).

Tạo tài khoản chị (OWNER_EMAIL / OWNER_PASSWORD) và dữ liệu mẫu tối thiểu: nhóm hàng, khung chấm điểm 7 tiêu chí,
giọng viết mặc định, vài nguyên tắc chọn, tài khoản kênh giả. Dữ liệu mẫu đầy đủ do các module bổ sung sau."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.discovery import discover_modules

log = logging.getLogger("app.seed")

CATEGORIES = [
    # (slug, tên, tiêu hao?, số ngày dùng hết)
    ("nha-bep", "Nhà bếp", False, None),
    ("phong-tam", "Phòng tắm", False, None),
    ("sap-xep-luu-tru", "Sắp xếp, lưu trữ", False, None),
    ("mang-theo", "Đồ mang theo", False, None),
    ("tieu-hao", "Đồ tiêu hao", True, 60),
]

CRITERIA = [
    ("cong_nang", "Công năng", 20, "Làm đúng việc, giải quyết được vấn đề thật"),
    ("do_ben", "Chất lượng, độ bền", 20, "Chắc tay, đánh giá dài hạn tốt"),
    ("an_toan", "Chất liệu an toàn", 15, "Đặc biệt đồ tiếp xúc thực phẩm"),
    ("de_dung", "Dễ dùng, dễ vệ sinh", 15, "Không cầu kỳ, rửa nhanh"),
    ("tham_my", "Thẩm mỹ", 10, "Gọn, hợp nhà Việt"),
    ("gia_tri", "Đáng tiền", 15, "So với giá bán ở Việt Nam"),
    ("van_chuyen", "Dễ nhập, dễ giao", 5, "Nhẹ, không pin/chất lỏng, ít vỡ"),
]

PRINCIPLES = [
    ("must", "Đồ tiếp xúc thực phẩm phải có chất liệu rõ ràng (inox 304, silicon thực phẩm, PP...)"),
    ("must_not", "Không chọn hàng có pin hoặc chất lỏng ở giai đoạn đầu"),
    ("prefer", "Ưu tiên món giải quyết một phiền toái cụ thể trong bếp hoặc nhà tắm"),
    ("avoid", "Tránh món chỉ đẹp ảnh mà đánh giá dài hạn kém"),
]


async def seed(db: AsyncSession) -> dict[str, int]:
    from app.core.enums import Channel
    from app.modules.assessment.models import ScoringProfile
    from app.modules.catalog.models import Category
    from app.modules.content.models import VoiceProfile
    from app.modules.control.models import User
    from app.modules.control.service import ensure_owner
    from app.modules.inbox.models import AccountStatus, ChannelAccount
    from app.modules.selection.models import PrincipleKind, SelectionPrinciple

    counts = dict.fromkeys(("owner", "categories", "scoring_profiles", "voice_profiles", "principles", "channels"), 0)
    if settings.owner_email and settings.owner_password:
        before = await db.scalar(select(User.id).where(User.email == settings.owner_email.strip().lower()))
        await ensure_owner(db, settings.owner_email, settings.owner_password, settings.owner_name)
        counts["owner"] = 0 if before else 1

    existing = set((await db.execute(select(Category.slug))).scalars())
    for i, (slug, name, consumable, days) in enumerate(CATEGORIES):
        if slug not in existing:
            db.add(Category(slug=slug, name=name, position=i, is_consumable=consumable, default_reorder_days=days))
            counts["categories"] += 1

    if not await db.scalar(select(ScoringProfile.id).where(ScoringProfile.is_default.is_(True))):
        db.add(
            ScoringProfile(
                name="Khung mặc định",
                is_default=True,
                pass_score=65,
                criteria=[{"key": k, "label": lbl, "weight": w, "description": d} for k, lbl, w, d in CRITERIA],
            )
        )
        counts["scoring_profiles"] += 1

    if not await db.scalar(select(VoiceProfile.id).limit(1)):
        db.add(
            VoiceProfile(
                name="Giọng của chị",
                style_summary="Kể như đang dùng thật: ngắn, thật thà, nói cả điều chưa ưng. Không hô hào, không nói quá.",
                rules=[
                    "Xưng «mình», gọi khách «bạn»",
                    "Mỗi bài nêu một điều chưa ưng",
                    "Không dùng từ «tốt nhất», «số 1», «thần thánh»",
                    "Số liệu phải lấy từ hồ sơ thẩm định",
                ],
            )
        )
        counts["voice_profiles"] += 1

    if not await db.scalar(select(SelectionPrinciple.id).limit(1)):
        for i, (kind, text) in enumerate(PRINCIPLES):
            db.add(SelectionPrinciple(kind=PrincipleKind(kind), text=text, priority=i))
            counts["principles"] += 1

    have = set((await db.execute(select(ChannelAccount.channel))).scalars())
    for ch, name in ((Channel.FACEBOOK, "Trang Hàng Chọn (giả)"), (Channel.INSTAGRAM, "@hangchon (giả)"),
                     (Channel.ZALO_OA, "Zalo OA Hàng Chọn (giả)"), (Channel.TIKTOK, "TikTok Hàng Chọn (giả)")):  # fmt: skip
        if ch not in have:
            db.add(
                ChannelAccount(channel=ch, name=name, external_id=f"mock_{ch.value}_page", status=AccountStatus.MOCK)
            )
            counts["channels"] += 1
    await db.flush()
    return counts


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    discover_modules()
    async with SessionLocal() as db:
        counts = await seed(db)
        await db.commit()
    log.info("Đã tạo: %s", ", ".join(f"{k}={v}" for k, v in counts.items()))
    if settings.owner_email:
        log.info("Đăng nhập bàn làm việc bằng %s", settings.owner_email)


if __name__ == "__main__":
    asyncio.run(main())
