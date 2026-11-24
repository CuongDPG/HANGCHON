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


@events.on("candidate.assessed")
async def _suggest_sample(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Hồ sơ thẩm định đạt điểm đạt của khung chấm → việc chờ chị «mua mẫu?» (một việc cho mỗi ứng viên)."""
    await service.suggest_sample_if_passing(db, uuid.UUID(payload["candidate_id"]), payload.get("assessment_id"))


@events.on("tester.feedback_received")
async def _tester_feedback(db: AsyncSession, payload: dict[str, Any]) -> None:
    """h8: cảm nhận của khách thử hàng → một ghi chú thử (author=tester) cạnh ghi chú của chị. Mỗi lời mời một ghi chú."""
    from sqlalchemy import select

    from app.core.timeutil import now_utc
    from app.modules.selection.models import NoteAuthor, ProcessingStatus, TrialNote, TrialNoteKind

    invite_id = uuid.UUID(payload["tester_invite_id"])
    if await db.scalar(select(TrialNote.id).where(TrialNote.tester_invite_id == invite_id)):
        return
    rating = payload.get("rating")
    text = str(payload.get("feedback") or "").strip()
    db.add(
        TrialNote(
            candidate_id=uuid.UUID(payload["candidate_id"]),
            kind=TrialNoteKind.TEXT,
            author=NoteAuthor.TESTER,
            tester_invite_id=invite_id,
            author_name=payload.get("customer_name") or "Khách thử",
            text=f"{text} ({rating}/5)" if rating else text,
            recorded_at=now_utc(),
            processing_status=ProcessingStatus.DONE,
        )
    )
    await db.flush()
