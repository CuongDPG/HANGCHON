"""Việc nền của hộp thư: AI xử lý tin đến từ webhook (để webhook trả lời nền tảng thật nhanh)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.jobs import job
from app.modules.inbox import service

log = logging.getLogger("app.inbox")


@job("inbox.triage")
async def triage_message(ctx: dict[str, Any], message_id: str) -> None:
    async with ctx["db"]() as db:
        try:
            await service.triage(db, uuid.UUID(message_id))
            await db.commit()
        except Exception:
            await db.rollback()
            log.exception("Xử lý tin %s lỗi", message_id)
