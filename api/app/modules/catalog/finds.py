"""Trang Nhờ chị tìm (e9): khách gửi nhu cầu (chống spam cơ bản), người khác bấm «mình cũng cần» (một lượt mỗi
thiết bị); đủ ngưỡng (mặc định 30) thì phát `find_request.threshold` để module sourcing đề xuất mở đề tìm."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core import events
from app.core.errors import AppError, BadRequest, Conflict, NotFound
from app.core.timeutil import now_utc
from app.modules.catalog.ai_tasks import ModerateIn, ModerateOut, moderate_rules
from app.modules.catalog.models import FindRequest, FindRequestStatus, FindRequestVote, Product
from app.modules.catalog.textutil import normalize_vi, slugify_vi
from app.modules.sourcing.models import Candidate, CandidateStage

log = logging.getLogger("app.catalog")

THRESHOLD_SETTING = "catalog.find_request_threshold"
DEFAULT_THRESHOLD = 30
MAX_PER_DEVICE_PER_DAY = 3

PUBLIC = (FindRequestStatus.OPEN, FindRequestStatus.THRESHOLD_REACHED, FindRequestStatus.SEARCHING,
          FindRequestStatus.FOUND, FindRequestStatus.CLOSED)  # fmt: skip
VOTABLE = (FindRequestStatus.OPEN, FindRequestStatus.THRESHOLD_REACHED, FindRequestStatus.SEARCHING)


class TooManyRequests(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Bạn gửi nhiều quá trong hôm nay, mai gửi tiếp nhé."


async def threshold(db: AsyncSession) -> int:
    v = await control.get_setting(db, THRESHOLD_SETTING)
    try:
        return max(2, int(v)) if v is not None else DEFAULT_THRESHOLD
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD


async def get(db: AsyncSession, find_id: uuid.UUID) -> FindRequest:
    fr = await db.get(FindRequest, find_id)
    if fr is None:
        raise NotFound("Không tìm thấy yêu cầu nhờ tìm.")
    return fr


async def get_public(db: AsyncSession, slug: str) -> FindRequest:
    fr = (
        await db.execute(select(FindRequest).where(FindRequest.public_slug == slug, FindRequest.status.in_(PUBLIC)))
    ).scalar_one_or_none()
    if fr is None:
        raise NotFound("Không tìm thấy yêu cầu này.")
    return fr


def _check_text(title: str, description: str | None) -> tuple[str, str | None]:
    title = " ".join(title.split())
    description = (description or "").strip() or None
    if len(title) < 6:
        raise BadRequest("Bạn tả món cần tìm dài hơn một chút nhé (ít nhất vài chữ).")
    if len(title) > 200 or (description and len(description) > 1000):
        raise BadRequest("Nội dung dài quá, bạn viết gọn lại giúp mình.")
    links = len(re.findall(r"https?://|www\.", f"{title} {description or ''}"))
    if links > 1:
        raise BadRequest("Bạn bớt đường link giúp mình (tối đa một link tham khảo).")
    return title, description


async def create(
    db: AsyncSession,
    *,
    title: str,
    description: str | None,
    budget_vnd: int | None,
    contact_name: str | None,
    contact: str | None,
    device_key: str,
) -> tuple[FindRequest, bool]:
    """Trả (yêu cầu, có_phải_trùng). Trùng tiêu đề với yêu cầu đang hiện → cộng một phiếu thay vì tạo mới."""
    title, description = _check_text(title, description)
    since = now_utc() - timedelta(days=1)
    recent = (
        await db.execute(
            select(func.count()).where(FindRequest.submitter_key == device_key, FindRequest.created_at >= since)
        )
    ).scalar_one()
    if recent >= MAX_PER_DEVICE_PER_DAY:
        raise TooManyRequests()
    key = normalize_vi(title)
    for fr in (await db.execute(select(FindRequest).where(FindRequest.status.in_(VOTABLE)))).scalars():
        if normalize_vi(fr.title) == key:
            await vote(db, fr, device_key, contact=contact)
            return fr, True
    fr = FindRequest(
        public_slug=f"{slugify_vi(title, max_length=60)}-{uuid.uuid4().hex[:5]}",
        title=title,
        description=description,
        budget_vnd=budget_vnd,
        contact_name=(contact_name or "").strip()[:120] or None,
        contact=(contact or "").strip()[:200] or None,
        status=FindRequestStatus.PENDING_REVIEW,
        vote_threshold=await threshold(db),
        submitter_key=device_key,
        vote_count=0,
    )
    db.add(fr)
    await db.flush()
    await _add_vote(db, fr, device_key, contact=contact)
    await events.emit("find_request.created", {"find_request_id": str(fr.id)}, db=db)
    await moderate_and_propose(db, fr)
    return fr, False


async def moderate_and_propose(db: AsyncSession, fr: FindRequest) -> control.ProposeOutcome:
    inp = ModerateIn(kind="find_request", text=f"{fr.title}\n{fr.description or ''}".strip())
    rules = moderate_rules(inp)
    run_id = None
    try:
        res = await ai.run("catalog.moderate_find_request", inp, ModerateOut)
        verdict, run_id = res.output, res.run_id
    except ai.AIError as e:
        log.warning("Lọc yêu cầu nhờ tìm bằng AI lỗi: %s", e)
        verdict = rules
    hide = verdict.recommend == "hide" or rules.recommend == "hide"
    reason = rules.reason if (hide and verdict.recommend != "hide") else verdict.reason
    fr.moderation_note = reason
    await db.flush()
    return await control.propose(
        "catalog.publish_find_request",
        f"Hiện lời nhờ tìm: {fr.title}",
        {"find_request_id": str(fr.id), "title": fr.title},
        {
            "title": fr.title,
            "description": fr.description,
            "budget_vnd": fr.budget_vnd,
            "recommend": "hide" if hide else "publish",
            "reason": reason,
            "suggested_title": verdict.cleaned_title,
        },
        db=db,
        summary=reason,
        ref_type="find_requests",
        ref_id=fr.id,
        ai_run_id=run_id,
        dedupe_key=f"find:{fr.id}",
    )


async def publish(db: AsyncSession, fr: FindRequest, *, title: str | None, mode: str, hide: bool) -> FindRequest:
    if fr.status != FindRequestStatus.PENDING_REVIEW:
        return fr
    if mode == "auto" and hide:
        fr.status = FindRequestStatus.REJECTED
        await db.flush()
        return fr
    if title and title.strip():
        fr.title = " ".join(title.split())[:200]
    fr.status = FindRequestStatus.OPEN
    await db.flush()
    await _check_threshold(db, fr)
    return fr


async def _add_vote(db: AsyncSession, fr: FindRequest, device_key: str, *, contact: str | None = None) -> bool:
    stmt = (
        pg_insert(FindRequestVote)
        .values(
            id=uuid.uuid4(),
            find_request_id=fr.id,
            voter_key=device_key,
            contact=(contact or None),
            notify=bool(contact),
        )
        .on_conflict_do_nothing(constraint="uq_find_request_votes_voter")
        .returning(FindRequestVote.id)
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        return False
    new_count = (
        await db.execute(
            update(FindRequest)
            .where(FindRequest.id == fr.id)
            .values(vote_count=FindRequest.vote_count + 1)
            .returning(FindRequest.vote_count)
        )
    ).scalar_one()
    fr.vote_count = new_count
    return True


async def vote(db: AsyncSession, fr: FindRequest, device_key: str, *, contact: str | None = None) -> bool:
    if fr.status not in VOTABLE:
        raise Conflict("Yêu cầu này không còn nhận thêm người cùng cần.", code="find_not_votable")
    added = await _add_vote(db, fr, device_key, contact=contact)
    if added:
        await _check_threshold(db, fr)
    return added


async def _check_threshold(db: AsyncSession, fr: FindRequest) -> None:
    if fr.status == FindRequestStatus.OPEN and fr.vote_count >= fr.vote_threshold:
        fr.status = FindRequestStatus.THRESHOLD_REACHED
        fr.threshold_reached_at = now_utc()
        await db.flush()
        await events.emit("find_request.threshold", {"find_request_id": str(fr.id)}, db=db)


async def trying_counts(db: AsyncSession, brief_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Số mẫu chị đang mua thử / dùng thử theo đề săn hàng (đọc bảng candidates)."""
    if not brief_ids:
        return {}
    rows = (
        await db.execute(
            select(Candidate.brief_id, func.count())
            .where(
                Candidate.brief_id.in_(brief_ids), Candidate.stage.in_((CandidateStage.SAMPLE, CandidateStage.TRIAL))
            )
            .group_by(Candidate.brief_id)
        )
    ).all()
    return {r[0]: int(r[1]) for r in rows}


def public_status(fr: FindRequest, trying: int = 0) -> dict[str, str]:
    """Trạng thái công khai: mới / AI đang tìm / chị đang thử n mẫu / đã có trên kệ / chưa có món ưng."""
    s = fr.status
    if s == FindRequestStatus.FOUND:
        return {"key": "found", "label": "Đã có trên kệ"}
    if s == FindRequestStatus.CLOSED:
        return {"key": "none", "label": "Chưa có món ưng"}
    if s == FindRequestStatus.SEARCHING:
        if trying:
            return {"key": "trying", "label": f"Mình đang thử {trying} mẫu"}
        return {"key": "searching", "label": "AI đang tìm ứng viên"}
    if s == FindRequestStatus.THRESHOLD_REACHED:
        return {"key": "threshold", "label": "Đủ người cần, mình sắp mở tìm"}
    if s == FindRequestStatus.PENDING_REVIEW:
        return {"key": "pending", "label": "Chờ xem qua"}
    if s == FindRequestStatus.REJECTED:
        return {"key": "rejected", "label": "Không hiện"}
    return {"key": "new", "label": "Mới"}


async def set_status(db: AsyncSession, fr: FindRequest, data: dict[str, Any], user: Any) -> FindRequest:
    status = FindRequestStatus(data["status"])
    if status == FindRequestStatus.FOUND:
        pid = data.get("product_id")
        if not pid or await db.get(Product, uuid.UUID(str(pid))) is None:
            raise BadRequest("Chị chọn món trên kệ đã đáp ứng yêu cầu này.")
        fr.product_id = uuid.UUID(str(pid))
    if status == FindRequestStatus.REJECTED:
        await control.cancel_pending(db, action="catalog.publish_find_request", dedupe_key=f"find:{fr.id}")
    if data.get("brief_id"):
        fr.brief_id = uuid.UUID(str(data["brief_id"]))
    if data.get("note") is not None:
        fr.moderation_note = data["note"]
    old = fr.status
    fr.status = status
    await control.audit(db, "catalog.find_request_status", user=user, entity_type="find_requests", entity_id=fr.id,
                        summary=f"Nhờ tìm «{fr.title}»: {old.value} → {status.value}")  # fmt: skip
    await db.flush()
    if old == FindRequestStatus.PENDING_REVIEW and status == FindRequestStatus.OPEN:
        await _check_threshold(db, fr)
    return fr
