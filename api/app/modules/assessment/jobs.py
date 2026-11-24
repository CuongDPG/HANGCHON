"""Việc nền của assessment."""

from __future__ import annotations

import uuid
from typing import Any

from app.core.jobs import job
from app.modules.assessment import service


@job("assessment.run")
async def run_assessment(ctx: dict[str, Any], candidate_id: str) -> str:
    async with ctx["db"]() as db:
        a = await service.execute(db, uuid.UUID(candidate_id))
        await db.commit()
        return a.status.value
