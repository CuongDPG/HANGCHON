"""Dữ liệu mẫu hộp thư (h1–h3): tin đến được đưa qua đúng luồng thật (ingest → AI soạn → chờ chị / tự trả lời).

    uv run python -m app.modules.inbox.seed      # tài khoản chị + dữ liệu nền + khu Khách (crm) + hộp thư

Tên khách, nội dung là ví dụ. Chạy lặp lại không sinh trùng (khoá theo mã tin `demo_*`).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.config import settings
from app.core.enums import Channel
from app.core.timeutil import now_utc
from app.integrations.social import InboundEvent
from app.modules.control.models import AutonomyLevel, AutonomySetting
from app.modules.inbox import service
from app.modules.inbox.context import SHIPPING_POLICY_KEY
from app.modules.inbox.models import Message

log = logging.getLogger("app.seed")

# (mã, kênh, loại, id người gửi, tên, nội dung, cách đây (phút), AI tự trả lời câu thường gặp?)
DEMO = [
    ("demo_m01", Channel.FACEBOOK, "direct_message", "demo_psid_thuha", "Thu Hà",
     "Bình giữ nhiệt này cho bé 3 tuổi dùng được không chị?", 10, False),
    ("demo_m02", Channel.ZALO_OA, "direct_message", "demo_zalo_minh", "anh Minh",
     "Đơn HCDEMO0004 mình nhận bị móp nắp hộp cơm rồi shop ơi", 32, False),
    ("demo_m03", Channel.INSTAGRAM, "comment", "demo_ig_ngoc", "Lê Ngọc",
     "Bình giữ nhiệt còn hàng không shop?", 60, True),
    ("demo_m04", Channel.FACEBOOK, "direct_message", "demo_psid_khoa", "Đỗ Khoa",
     "Phí ship về Đà Nẵng bao nhiêu chị?", 95, True),
    ("demo_m05", Channel.FACEBOOK, "comment", "demo_psid_mai", "Vũ Mai",
     "Hộp cơm inox giá bao nhiêu ạ?", 140, True),
    ("demo_m06", Channel.ZALO_OA, "direct_message", "demo_zalo_lan", "Phạm Lan",
     "Mình bị dị ứng niken, dùng hộp cơm inox có sao không chị?", 180, False),
    ("demo_m07", Channel.FACEBOOK, "direct_message", "demo_psid_huong", "Hương Trần",
     "Chị ơi lấy cho em 2 hộp cơm inox 3 ngăn nhé", 220, False),
    ("demo_m08", Channel.INSTAGRAM, "direct_message", "demo_ig_quynh", "quynh.nha",
     "Khăn tắm cho bé giặt máy được không ạ?", 300, False),
    ("demo_m09", Channel.FACEBOOK, "direct_message", "demo_psid_tung", "Tùng Lê",
     "Hộp cơm inox bao giờ về vậy shop?", 400, True),
]  # fmt: skip

DEMO_SHIPPING = "Phí giao 25.000–35.000đ tuỳ tỉnh, đơn từ 500.000đ miễn phí giao, giao 2–4 ngày"


async def seed_demo(db: AsyncSession) -> dict[str, Any]:
    if not await control.get_setting(db, SHIPPING_POLICY_KEY):
        await control.set_setting(db, SHIPPING_POLICY_KEY, DEMO_SHIPPING, None)
    before = await db.get(AutonomySetting, service.ACTION_FAQ)
    had_level = before.level if before else None
    made = 0
    for ext, ch, kind, author, name, text, ago, auto in DEMO:
        if await db.scalar(select(Message.id).where(Message.external_message_id == ext)):
            continue
        ev = InboundEvent(
            channel=ch,
            kind=kind,  # type: ignore[arg-type]
            account_external_id=f"mock_{ch.value}_page",
            thread_external_id=f"demo_t_{author}" if kind == "direct_message" else f"c:demo_c_{ext}",
            message_external_id=ext,
            post_external_id="demo_post_1" if kind == "comment" else None,
            author_external_id=author,
            author_name=name,
            text=text,
            sent_at=now_utc() - timedelta(minutes=ago),
        )
        msg = await service.ingest(db, ev, driver_name="mock")
        if msg is None:
            continue
        # vài câu thường gặp cho AI tự trả lời để tab «AI đã trả lời» có dữ liệu; xong trả mức tự chủ về như cũ
        await control.set_level(db, service.ACTION_FAQ, AutonomyLevel.AUTO if auto else AutonomyLevel.ASK, None)
        await service.triage(db, msg.id)
        made += 1
    row = await db.get(AutonomySetting, service.ACTION_FAQ)
    if row is not None and had_level is None:
        await db.delete(row)
    elif row is not None and had_level is not None:
        row.level = had_level
    await db.flush()
    return {"messages": made}


async def main() -> None:
    from app.core.db import SessionLocal
    from app.core.discovery import discover_modules
    from app.modules.crm.seed import seed_demo as crm_demo
    from app.seed import seed as base_seed

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings.jobs_eager = True  # tóm tắt sổ khách chạy ngay, không cần worker
    discover_modules()
    async with SessionLocal() as db:
        log.info("Nền: %s", await base_seed(db))
        log.info("Khách: %s", await crm_demo(db))
        log.info("Hộp thư: %s", await seed_demo(db))
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
