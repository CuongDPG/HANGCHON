"""Người nghe sự kiện của sourcing (idempotent — chạy lặp lại không sinh trùng)."""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.modules.sourcing import service
from app.modules.sourcing.models import Candidate


@events.on("message.received")
async def _on_message(db: AsyncSession, payload: dict[str, Any]) -> None:
    """a6: khách hỏi một món → gom vào nhu cầu."""
    await service.on_message(db, payload["thread_id"], payload["message_id"])


@events.on("find_request.created")
async def _on_find_request(db: AsyncSession, payload: dict[str, Any]) -> None:
    await service.on_find_request(db, payload["find_request_id"])


@events.on("find_request.threshold")
async def _on_threshold(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Đủ người cùng cần → đề xuất chị mở đề tìm (việc chờ chị)."""
    await service.on_find_request_threshold(db, payload["find_request_id"])


@events.on("candidate.assessed")
async def _on_assessed(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Hồ sơ thẩm định có điểm → cập nhật điểm xếp hạng của ứng viên."""
    from app.modules.assessment.models import Assessment  # chỉ đọc

    cand = await db.get(Candidate, uuid.UUID(payload["candidate_id"]))
    a = await db.get(Assessment, uuid.UUID(payload["assessment_id"])) if payload.get("assessment_id") else None
    if cand is None or a is None or a.score_total is None:
        return
    score = int(Decimal(a.score_total).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    gd = (cand.raw or {}).get("guidance")
    if isinstance(gd, dict) and gd.get("delta"):
        # c5 + c6: nguyên tắc/gu vẫn chỉnh điểm sau thẩm định (chạy lặp lại cho cùng kết quả)
        cand.raw = {**cand.raw, "guidance": {**gd, "base_score": score}}
        score = max(0, min(100, score + int(gd["delta"])))
    cand.ai_score = score


@events.on("candidate.details_fetched")
async def _on_details_fetched(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Thẩm định đã đọc trang chi tiết → ghi ảnh nhà cung cấp vào ứng viên rồi lưu bản sao về kho riêng."""
    from sqlalchemy.orm.attributes import flag_modified

    from app.core.timeutil import now_utc
    from app.modules.sourcing import gallery

    cand = await db.get(Candidate, uuid.UUID(payload["candidate_id"]))
    if cand is None:
        return
    service.merge_images(cand, payload.get("images") or [])
    if not (cand.raw or {}).get("detail"):
        cand.raw = {**(cand.raw or {}), "detail": {"fetched_at": now_utc().isoformat(), "by": "assessment"}}
        flag_modified(cand, "raw")
    if gallery.caching_enabled():
        await gallery.cache_images(cand)
