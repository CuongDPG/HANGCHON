"""Nghe sự kiện: học gu của chị sau mỗi lần chọn/loại (c6)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.modules.selection import service


@events.on("candidate.selected")
@events.on("candidate.rejected")
async def _learn_taste(db: AsyncSession, payload: dict[str, Any]) -> None:
    await service.mark_taste_pending(db, uuid.UUID(payload["candidate_id"]))
