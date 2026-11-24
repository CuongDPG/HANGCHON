"""Nghiệp vụ bàn chọn (c1–c6).

- Chỉ module này ghi `candidates.stage` / `stage_changed_at` / `board_position` (data-model.md, mục selection).
- Việc AI làm đều qua `ai.run` + `control.propose`; module khác nhận tin qua sự kiện (ARCHITECTURE mục 10).
"""

from __future__ import annotations

import logging
import math
import re
import uuid
from collections import Counter
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from unidecode import unidecode

from app import ai, control
from app.core import events
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.storage import get_storage
from app.core.timeutil import now_utc
from app.modules.catalog.models import Category
from app.modules.control.models import ApprovalItem, User
from app.modules.selection.ai_tasks import (
    DraftNote,
    DraftReasonsIn,
    DraftReasonsOut,
    NoteCandidateRef,
    OrganizedPoint,
    OrganizeNoteIn,
    OrganizeNoteOut,
    TasteDecision,
    TasteIn,
    TasteOut,
    TasteTraitOut,
)
from app.modules.selection.models import (
    Decision,
    DraftStatus,
    ProcessingStatus,
    SelectionDecision,
    SelectionPrinciple,
    TasteProfile,
    TrialNote,
)
from app.modules.sourcing.models import Candidate, CandidateStage
from app.modules.supply.models import CostSheet

log = logging.getLogger("app.selection")

STAGES = [s.value for s in CandidateStage]
TRIAL_DAYS_KEY = "selection.trial_days"
DEFAULT_TRIAL_DAYS = 14
BOARD_LIMIT = 200

# ---- c4: nhóm lý do loại (để thống kê «21 mẫu loại: rò nước 8…») ------------------------------------------------

REJECT_GROUPS: list[tuple[str, str, tuple[str, ...]]] = [
    ("ro_ri", "Rò nước", ("ro nuoc", "ro ri", "chay nuoc", "tham nuoc", "ri nuoc", "ro", "khong kin")),
    ("chat_lieu", "Chất liệu kém", ("chat lieu", "mong", "nhua", "de vo", "bong troc", "mau nhat", "xuoc")),
    ("do_ben", "Không bền", ("gay", "hong", "long", "lung lay", "gi set", "gi", "nut", "mop", "bung", "sut")),
    ("mui", "Có mùi", ("mui", "hoi")),
    ("kich_thuoc", "Sai kích thước", ("nho hon", "to hon", "khong vua", "kich thuoc", "chat", "ngan")),
    ("kho_dung", "Khó dùng, khó vệ sinh", ("kho dung", "kho rua", "kho ve sinh", "bat tien", "ket", "nang tay")),
    ("an_toan", "Không an toàn", ("an toan", "sac", "chay", "doc", "hoa chat", "bpa")),
    ("gia", "Giá về tay cao", ("gia", "dat", "bien", "lo von", "cuoc cao")),
    ("van_chuyen", "Khó nhập, khó giao", ("van chuyen", "cong kenh", "pin", "chat long", "de vo khi giao", "nang qua")),
    ("tham_my", "Không đẹp như ảnh", ("xau", "khong dep", "khac anh", "mau khac")),
    ("nguon", "Nguồn không ổn", ("shop", "nha cung cap", "xuong", "giao cham", "het hang", "hang nhai", "nhai")),
    ("khac", "Lý do khác", ()),
]
REJECT_GROUP_LABELS = {k: label for k, label, _ in REJECT_GROUPS}

DEFAULT_QUICK_REASONS = [
    ("Rò nước sau vài lần dùng", "ro_ri"),
    ("Chất liệu mỏng, có mùi nhựa", "chat_lieu"),
    ("Nhỏ hơn mô tả", "kich_thuoc"),
    ("Khó vệ sinh các khe", "kho_dung"),
    ("Giá về tay cao, biên mỏng", "gia"),
    ("Ốc lỏng, lung lay sau một tuần", "do_ben"),
]


def suggest_groups(text: str) -> list[str]:
    """Gợi ý nhóm lý do theo từ khoá (khớp nguyên từ, không dấu)."""
    plain = " " + re.sub(r"[^a-z0-9]+", " ", unidecode(text).lower()) + " "
    found = [k for k, _, words in REJECT_GROUPS if any(f" {w.strip()} " in plain for w in words)]
    return found[:2] or ["khac"]


def normalize_tags(tags: list[str] | None, reason: str | None) -> list[str]:
    clean = [t for t in (tags or []) if t in REJECT_GROUP_LABELS]
    if clean:
        return list(dict.fromkeys(clean))
    return suggest_groups(reason or "")


# ---- tiện ích ------------------------------------------------------------------------------------------------------


def file_url(key: str | None) -> str | None:
    if not key:
        return None
    storage = get_storage()
    if storage.name == "local":  # cùng origin với web (Next chuyển tiếp /api/*) để cookie đăng nhập đi kèm
        return f"/api/files/{key}"
    return storage.url(key)


def split_lines(text: str | None) -> list[str]:
    return [line.strip().lstrip("-•· ").strip() for line in (text or "").splitlines() if line.strip()]


def join_lines(items: list[str]) -> str:
    return "\n".join(i.strip() for i in items if i.strip())


async def trial_days(db: AsyncSession) -> int:
    v = await control.get_setting(db, TRIAL_DAYS_KEY)
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return DEFAULT_TRIAL_DAYS


def trial_day_of(c: Candidate, now: datetime | None = None) -> int | None:
    if c.stage != CandidateStage.TRIAL or c.stage_changed_at is None:
        return None
    now = now or now_utc()
    return max(1, math.floor((now - c.stage_changed_at).total_seconds() / 86400) + 1)


async def get_candidate(db: AsyncSession, candidate_id: uuid.UUID) -> Candidate:
    c = await db.get(Candidate, candidate_id)
    if c is None or c.is_archived:
        raise NotFound("Không tìm thấy ứng viên này.")
    return c


async def latest_decisions(db: AsyncSession, candidate_ids: list[uuid.UUID]) -> dict[uuid.UUID, SelectionDecision]:
    if not candidate_ids:
        return {}
    rows = (
        await db.execute(
            select(SelectionDecision)
            .where(SelectionDecision.candidate_id.in_(candidate_ids))
            .order_by(SelectionDecision.candidate_id, SelectionDecision.decided_at.desc())
            .ext(distinct_on(SelectionDecision.candidate_id))
        )
    ).scalars()
    return {d.candidate_id: d for d in rows}


async def seal_counts(db: AsyncSession, brief_ids: set[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    """Con dấu «ĐÃ CHỌN n/m»: m = số ứng viên cùng đề, n = số đã chọn."""
    if not brief_ids:
        return {}
    rows = await db.execute(
        select(
            Candidate.brief_id,
            func.count(),
            func.count().filter(Candidate.stage == CandidateStage.SELECTED),
        )
        .where(Candidate.brief_id.in_(brief_ids))
        .group_by(Candidate.brief_id)
    )
    return {bid: (int(sel), int(total)) for bid, total, sel in rows}


def decision_summary(d: SelectionDecision | None) -> str | None:
    if d is None:
        return None
    if d.decision == Decision.REJECTED:
        return d.rejection_reason
    first = split_lines(d.reason_selected or d.draft_reason_selected)
    return first[0] if first else None


async def build_cards(db: AsyncSession, cands: list[Candidate]) -> list[dict[str, Any]]:
    ids = [c.id for c in cands]
    days = await trial_days(db)
    now = now_utc()
    note_stats: dict[uuid.UUID, tuple[int, datetime | None]] = {}
    last_text: dict[uuid.UUID, str | None] = {}
    decisions: dict[uuid.UUID, SelectionDecision] = {}
    costs: dict[uuid.UUID, int] = {}
    if ids:
        for cid, n, last in await db.execute(
            select(TrialNote.candidate_id, func.count(), func.max(TrialNote.recorded_at))
            .where(TrialNote.candidate_id.in_(ids))
            .group_by(TrialNote.candidate_id)
        ):
            note_stats[cid] = (int(n), last)
        for cid, text in await db.execute(
            select(TrialNote.candidate_id, TrialNote.text)
            .where(TrialNote.candidate_id.in_(ids), TrialNote.text.is_not(None))
            .order_by(TrialNote.candidate_id, TrialNote.recorded_at.desc())
            .ext(distinct_on(TrialNote.candidate_id))
        ):
            last_text[cid] = text
        decisions = await latest_decisions(db, ids)
        for cid, landed in await db.execute(
            select(CostSheet.candidate_id, CostSheet.landed_cost_vnd).where(
                CostSheet.candidate_id.in_(ids), CostSheet.is_current.is_(True)
            )
        ):
            costs[cid] = int(landed)
    seals = await seal_counts(db, {c.brief_id for c in cands if c.brief_id})
    cards = []
    for c in cands:
        d = decisions.get(c.id) if c.stage in (CandidateStage.SELECTED, CandidateStage.REJECTED) else None
        n, last_at = note_stats.get(c.id, (0, None))
        seal = seals.get(c.brief_id) if c.brief_id else None
        cards.append(
            {
                "id": c.id,
                "title": c.title_vi,
                "image_url": c.main_image_url or (c.images[0] if c.images else None),
                "source_platform": c.source_platform.value,
                "price_vnd_estimate": c.price_vnd_estimate,
                "ai_score": c.ai_score,
                "stage": c.stage.value,
                "stage_changed_at": c.stage_changed_at,
                "board_position": c.board_position,
                "brief_id": c.brief_id,
                "category_id": c.category_id,
                "trial_day": trial_day_of(c, now),
                "trial_days": days,
                "note_count": n,
                "last_note": last_text.get(c.id),
                "last_note_at": last_at,
                "landed_cost_vnd": costs.get(c.id),
                "seal": {"chosen": seal[0], "total": seal[1]} if seal else None,
                "decision_id": d.id if d else None,
                "decision_summary": decision_summary(d),
                "draft_status": d.draft_status if d else None,
            }
        )
    return cards


async def board(db: AsyncSession, q: str | None = None) -> dict[str, Any]:
    stmt = select(Candidate).where(Candidate.is_archived.is_(False))
    if q:
        stmt = stmt.where(Candidate.title_vi.ilike(f"%{q.strip()}%"))
    counts = dict.fromkeys(STAGES, 0)
    for stage, n in await db.execute(
        select(Candidate.stage, func.count()).where(Candidate.is_archived.is_(False)).group_by(Candidate.stage)
    ):
        counts[stage.value] = int(n)
    columns: dict[str, list[dict[str, Any]]] = {}
    for stage in CandidateStage:
        rows = list(
            (
                await db.execute(
                    stmt.where(Candidate.stage == stage)
                    .order_by(
                        Candidate.board_position,
                        Candidate.stage_changed_at.desc().nulls_last(),
                        Candidate.created_at.desc(),
                    )
                    .limit(BOARD_LIMIT)
                )
            ).scalars()
        )
        columns[stage.value] = await build_cards(db, rows)
    return {"trial_days": await trial_days(db), "counts": counts, "columns": columns}


# ---- c1: chuyển cột ------------------------------------------------------------------------------------------------


async def _top_position(db: AsyncSession, stage: CandidateStage) -> int:
    lo = await db.scalar(select(func.min(Candidate.board_position)).where(Candidate.stage == stage))
    return 0 if lo is None else max(0, int(lo) - 1)


async def _reposition(db: AsyncSession, c: Candidate, position: int) -> None:
    """Đặt món vào vị trí `position` trong cột, đánh số lại cả cột (cột nhỏ, đủ nhanh)."""
    rows = list(
        (
            await db.execute(
                select(Candidate)
                .where(Candidate.stage == c.stage, Candidate.id != c.id, Candidate.is_archived.is_(False))
                .order_by(Candidate.board_position, Candidate.stage_changed_at.desc().nulls_last())
            )
        ).scalars()
    )
    rows.insert(min(position, len(rows)), c)
    for i, r in enumerate(rows):
        r.board_position = i


async def _trial_window(db: AsyncSession, c: Candidate) -> tuple[datetime | None, int | None]:
    first_note = await db.scalar(select(func.min(TrialNote.recorded_at)).where(TrialNote.candidate_id == c.id))
    starts = [t for t in (c.stage_changed_at if c.stage == CandidateStage.TRIAL else None, first_note) if t]
    if not starts:
        return None, None
    start = min(starts)
    return start, max(1, round((now_utc() - start).total_seconds() / 86400))


async def change_stage(
    db: AsyncSession,
    candidate_id: uuid.UUID,
    to: str,
    user: User | None,
    *,
    reason: str | None = None,
    reason_tags: list[str] | None = None,
    position: int | None = None,
) -> tuple[Candidate, SelectionDecision | None]:
    c = await get_candidate(db, candidate_id)
    target = CandidateStage(to)
    src = c.stage
    if target == src:
        if position is None:
            raise Conflict("Món này đã ở cột đó rồi.", code="same_stage")
        await _reposition(db, c, position)
        await db.flush()
        return c, None

    reason = (reason or "").strip() or None
    if target == CandidateStage.REJECTED and not reason:
        raise BadRequest("Chị ghi lý do loại (hoặc chọn nhanh một lý do hay dùng).", code="reason_required")

    trial_start, days_tried = await _trial_window(db, c)
    if src == CandidateStage.SELECTED:  # đổi ý: bỏ bản nháp lý do chọn đang chờ duyệt
        prev = (await latest_decisions(db, [c.id])).get(c.id)
        if prev is not None:
            await control.cancel_pending(
                db, action="selection.draft_reasons", ref_type="selection_decisions", ref_id=prev.id
            )
    c.stage = target
    c.stage_changed_at = now_utc()
    if position is None:
        c.board_position = await _top_position(db, target)
    else:
        await _reposition(db, c, position)

    decision: SelectionDecision | None = None
    if target in (CandidateStage.SELECTED, CandidateStage.REJECTED):
        decision = SelectionDecision(
            candidate_id=c.id,
            brief_id=c.brief_id,
            decision=Decision(target.value),
            decided_at=c.stage_changed_at,
            decided_by_id=user.id if user else None,
            trial_days=days_tried,
            trial_started_at=trial_start,
            trial_ended_at=c.stage_changed_at if trial_start else None,
        )
        if target == CandidateStage.REJECTED:
            decision.rejection_reason = reason
            decision.rejection_tags = normalize_tags(reason_tags, reason)
        db.add(decision)
    await db.flush()

    await control.audit(
        db, "selection.stage_changed", user=user, entity_type="candidates", entity_id=c.id,
        summary=f"«{c.title_vi}»: {src.value} → {target.value}", data={"from": src.value, "to": target.value, "reason": reason},
    )  # fmt: skip
    await events.emit(
        "candidate.stage_changed", {"candidate_id": str(c.id), "from": src.value, "to": target.value}, db=db
    )
    if decision is not None:
        name = "candidate.selected" if target == CandidateStage.SELECTED else "candidate.rejected"
        await events.emit(name, {"candidate_id": str(c.id), "decision_id": str(decision.id)}, db=db)
        if target == CandidateStage.SELECTED:
            await draft_reasons(db, decision)
    return c, decision


# ---- c2: nhật ký thử hàng -----------------------------------------------------------------------------------------


def note_points(note: TrialNote) -> list[dict[str, str]]:
    return [t for t in note.tags if isinstance(t, dict) and t.get("kind") in ("good", "bad", "measure")]


async def create_note(
    db: AsyncSession,
    *,
    candidate: Candidate | None,
    text: str | None,
    kind: str,
    user: User | None,
    photos: list[dict[str, Any]] | None = None,
    audio_key: str | None = None,
    duration_seconds: int | None = None,
    recorded_at: datetime | None = None,
) -> TrialNote:
    text = (text or "").strip() or None
    if not text and not photos and not audio_key:
        raise BadRequest("Ghi chú đang trống: chị nói, gõ hoặc thêm ảnh nhé.", code="empty_note")
    note = TrialNote(
        candidate_id=candidate.id if candidate else None,
        kind=kind,
        text=text,
        media=photos or [],
        audio_storage_key=audio_key,
        duration_seconds=duration_seconds,
        recorded_at=recorded_at or now_utc(),
        trial_day=trial_day_of(candidate) if candidate else None,
        processing_status=ProcessingStatus.PENDING if text else ProcessingStatus.DONE,
        created_by_id=user.id if user else None,
    )
    db.add(note)
    await db.flush()
    if text:
        await organize_note(db, note)
    return note


async def organize_note(db: AsyncSession, note: TrialNote) -> None:
    """AI sắp ghi chú thành ý gọn + nhãn; ghi chú chưa gắn món thì AI xếp vào món đang mua mẫu/đang thử."""
    candidate = await db.get(Candidate, note.candidate_id) if note.candidate_id else None
    refs: list[NoteCandidateRef] = []
    if candidate is None:
        rows = (
            await db.execute(
                select(Candidate.id, Candidate.title_vi).where(
                    Candidate.stage.in_([CandidateStage.SAMPLE, CandidateStage.TRIAL]), Candidate.is_archived.is_(False)
                )
            )
        ).all()
        refs = [NoteCandidateRef(id=str(i), title=t) for i, t in rows]
    note.processing_status = ProcessingStatus.PROCESSING
    try:
        res = await ai.run(
            "selection.organize_note",
            OrganizeNoteIn(
                text=note.text or "", candidate_title=candidate.title_vi if candidate else None,
                trial_day=note.trial_day, candidates=refs,
            ),
            OrganizeNoteOut,
        )  # fmt: skip
    except ai.AIError as e:
        note.processing_status = ProcessingStatus.FAILED
        log.warning("Không sắp được ghi chú %s: %s", note.id, e)
        return
    out = res.output
    assign: str | None = None
    if candidate is None and out.candidate_id and out.candidate_id in {r.id for r in refs} and out.confidence >= 0.5:
        assign = out.candidate_id
    note.ai_run_id = res.run_id
    outcome = await control.propose(
        "selection.organize_note",
        f"Sắp ghi chú thử: {(candidate.title_vi if candidate else 'chưa gắn món')}",
        {
            "note_id": str(note.id),
            "points": [p.model_dump() for p in out.points],
            "sentiment": out.sentiment,
            "candidate_id": assign,
            "confidence": out.confidence,
        },
        {"text": note.text, "points": [p.model_dump() for p in out.points]},
        db=db, ref_type="trial_notes", ref_id=note.id, ai_run_id=res.run_id, dedupe_key=f"note:{note.id}",
    )  # fmt: skip
    if outcome.status != "applied":
        note.processing_status = ProcessingStatus.PENDING if outcome.status == "pending" else ProcessingStatus.FAILED


async def apply_note_organization(db: AsyncSession, payload: dict[str, Any]) -> TrialNote:
    note = await db.get(TrialNote, uuid.UUID(payload["note_id"]))
    if note is None:
        raise NotFound("Ghi chú đã bị xoá.")
    note.tags = [OrganizedPoint.model_validate(p).model_dump() for p in payload.get("points") or []]
    note.sentiment = payload.get("sentiment")
    if payload.get("candidate_id") and note.candidate_id is None:
        cand = await db.get(Candidate, uuid.UUID(payload["candidate_id"]))
        if cand is not None:
            note.candidate_id = cand.id
            note.ai_assigned = True
            note.assignment_confidence = Decimal(str(round(float(payload.get("confidence") or 0), 2)))
            note.trial_day = trial_day_of(cand)
    note.processing_status = ProcessingStatus.DONE
    await db.flush()
    return note


async def list_notes(db: AsyncSession, candidate_id: uuid.UUID | None) -> list[TrialNote]:
    stmt = select(TrialNote).order_by(TrialNote.recorded_at.desc())
    stmt = (
        stmt.where(TrialNote.candidate_id == candidate_id)
        if candidate_id
        else stmt.where(TrialNote.candidate_id.is_(None))
    )
    return list((await db.execute(stmt.limit(300))).scalars())


# ---- c3: lý do chọn, điều chưa ưng ---------------------------------------------------------------------------------


async def draft_reasons(db: AsyncSession, decision: SelectionDecision, owner_request: str | None = None) -> None:
    """AI soạn «Vì sao mình chọn» + «Điều mình chưa ưng» CHỈ từ ghi chú thử, đưa qua control.propose (mặc định hỏi chị)."""
    cand = await db.get(Candidate, decision.candidate_id)
    notes = list(
        (
            await db.execute(
                select(TrialNote)
                .where(TrialNote.candidate_id == decision.candidate_id, TrialNote.text.is_not(None))
                .order_by(TrialNote.recorded_at)
            )
        ).scalars()
    )
    decision.draft_status = DraftStatus.DRAFTING
    if not notes:
        decision.draft_reason_selected = None
        decision.draft_not_satisfied = None
        decision.draft_status = DraftStatus.PENDING_REVIEW
        await db.flush()
        return
    try:
        res = await ai.run(
            "selection.draft_reasons",
            DraftReasonsIn(
                candidate_title=cand.title_vi if cand else "",
                trial_days=decision.trial_days,
                notes=[
                    DraftNote(day=n.trial_day, text=n.text or "", points=[OrganizedPoint(**p) for p in note_points(n)])
                    for n in notes
                ],
                owner_request=owner_request,
            ),
            DraftReasonsOut,
        )
    except ai.AIError as e:
        log.warning("AI chưa soạn được lý do chọn %s: %s", decision.id, e)
        decision.draft_status = DraftStatus.PENDING_REVIEW
        await db.flush()
        return
    out = res.output
    decision.draft_reason_selected = join_lines(out.reasons_selected)
    decision.draft_not_satisfied = join_lines(out.not_satisfied)
    decision.ai_run_id = res.run_id
    decision.draft_status = DraftStatus.PENDING_REVIEW
    await db.flush()
    outcome = await control.propose(
        "selection.draft_reasons",
        f"Lý do chọn: {cand.title_vi if cand else 'ứng viên'}",
        {
            "decision_id": str(decision.id),
            "reason_selected": out.reasons_selected,
            "not_satisfied": out.not_satisfied,
        },
        {
            "candidate": cand.title_vi if cand else None,
            "reason_selected": out.reasons_selected,
            "not_satisfied": out.not_satisfied,
            "missing_info": out.missing_info,
            "note_count": len(notes),
        },
        db=db,
        summary="AI soạn từ ghi chú thử của chị; chị sửa lời rồi chốt.",
        rationale=f"Từ {len(notes)} ghi chú thử hàng.",
        ref_type="selection_decisions",
        ref_id=decision.id,
        ai_run_id=res.run_id,
        dedupe_key=f"decision:{decision.id}",
    )
    if outcome.status == "pending":
        decision.approval_item_id = outcome.item_id
    await db.flush()


async def apply_reasons(
    db: AsyncSession, decision_id: uuid.UUID, reasons: list[str], not_satisfied: list[str]
) -> SelectionDecision:
    d = await db.get(SelectionDecision, decision_id)
    if d is None:
        raise NotFound("Không tìm thấy quyết định chọn này.")
    if d.decision != Decision.SELECTED:
        raise BadRequest("Chỉ món đã chọn mới có «Vì sao mình chọn».")
    clean = [r.strip() for r in reasons if r and r.strip()]
    if not clean:
        raise BadRequest("Chị ghi ít nhất một ý «Vì sao mình chọn».", code="reason_required")
    d.reason_selected = join_lines(clean[:3])
    d.not_satisfied = join_lines([r for r in not_satisfied if r and r.strip()][:3]) or None
    d.draft_status = DraftStatus.APPROVED
    await db.flush()
    return d


async def approve_reasons(
    db: AsyncSession, decision_id: uuid.UUID, user: User, reasons: list[str], not_satisfied: list[str]
) -> SelectionDecision:
    """Chị sửa lời rồi chốt. Có việc chờ duyệt thì duyệt luôn việc đó (để hàng chờ khớp), không thì ghi thẳng."""
    d = await db.get(SelectionDecision, decision_id)
    if d is None:
        raise NotFound("Không tìm thấy quyết định chọn này.")
    payload = {"reason_selected": reasons, "not_satisfied": not_satisfied}
    if d.approval_item_id is not None:
        item = await db.get(ApprovalItem, d.approval_item_id)
        if item is not None and item.status in (control.ApprovalStatus.PENDING, control.ApprovalStatus.FAILED):
            item = await control.approve(db, item.id, user, edited_payload=payload)
            if item.status == control.ApprovalStatus.FAILED:
                raise BadRequest(item.error or "Chưa lưu được lời chị sửa.")
            await db.refresh(d)
            return d
    d = await apply_reasons(db, decision_id, reasons, not_satisfied)
    await control.audit(
        db, "selection.reasons_approved", user=user, entity_type="selection_decisions", entity_id=d.id,
        summary="Chị chốt «Vì sao mình chọn»",
    )  # fmt: skip
    return d


# ---- c4: lý do loại ------------------------------------------------------------------------------------------------


async def reject_reasons(db: AsyncSession) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(SelectionDecision.rejection_reason, SelectionDecision.rejection_tags, func.count())
            .where(SelectionDecision.decision == Decision.REJECTED, SelectionDecision.rejection_reason.is_not(None))
            .group_by(SelectionDecision.rejection_reason, SelectionDecision.rejection_tags)
            .order_by(func.count().desc())
            .limit(8)
        )
    ).all()
    frequent = [{"text": r, "group": (tags or ["khac"])[0], "count": int(n)} for r, tags, n in rows]
    have = {f["text"].lower() for f in frequent}
    for text, group in DEFAULT_QUICK_REASONS:
        if len(frequent) >= 8:
            break
        if text.lower() not in have:
            frequent.append({"text": text, "group": group, "count": 0})
    return {"groups": [{"key": k, "label": label} for k, label, _ in REJECT_GROUPS], "frequent": frequent}


async def rejection_stats(
    db: AsyncSession, *, brief_id: uuid.UUID | None = None, public_only: bool = False
) -> dict[str, Any]:
    """Đếm các món đang ở cột «Đã loại» theo nhóm lý do (quyết định hiện hành của từng món)."""
    stmt = select(Candidate.id).where(Candidate.stage == CandidateStage.REJECTED)
    if brief_id:
        stmt = stmt.where(Candidate.brief_id == brief_id)
    ids = list((await db.execute(stmt)).scalars())
    decisions = [d for d in (await latest_decisions(db, ids)).values() if d.decision == Decision.REJECTED]
    if public_only:
        decisions = [d for d in decisions if d.show_on_profile]
    counter: Counter[str] = Counter()
    for d in decisions:
        counter[(d.rejection_tags or ["khac"])[0]] += 1
    groups = [{"key": k, "label": REJECT_GROUP_LABELS.get(k, k), "count": n} for k, n in counter.most_common()]
    total = len(decisions)
    summary = f"{total} mẫu loại" + (
        ": " + ", ".join(f"{g['label'].lower()} {g['count']}" for g in groups) if groups else ""
    )
    return {"total": total, "groups": groups, "summary": summary}


# ---- c5: bộ nguyên tắc ---------------------------------------------------------------------------------------------


async def active_principles(db: AsyncSession, category_id: uuid.UUID | None = None) -> list[SelectionPrinciple]:
    """Nguyên tắc đang bật cho một nhóm hàng (gồm cả nguyên tắc chung). Module khác đọc thẳng bảng theo cùng điều kiện:
    `is_active AND (category_id IS NULL OR category_id = :nhom)` sắp theo `priority`."""
    stmt = select(SelectionPrinciple).where(SelectionPrinciple.is_active.is_(True))
    cond = SelectionPrinciple.category_id.is_(None)
    if category_id:
        cond = cond | (SelectionPrinciple.category_id == category_id)
    return list((await db.execute(stmt.where(cond).order_by(SelectionPrinciple.priority))).scalars())


# ---- c6: gu của chị ------------------------------------------------------------------------------------------------


async def _profile(db: AsyncSession, category_id: uuid.UUID | None) -> TasteProfile:
    cond = TasteProfile.category_id.is_(None) if category_id is None else TasteProfile.category_id == category_id
    p = await db.scalar(select(TasteProfile).where(cond))
    if p is None:
        p = TasteProfile(category_id=category_id, examples={"selected": [], "rejected": [], "pending": []})
        db.add(p)
        await db.flush()
    return p


async def mark_taste_pending(db: AsyncSession, candidate_id: uuid.UUID) -> None:
    """Nghe candidate.selected/rejected: đánh dấu hồ sơ gu (chung + nhóm hàng) cần học lại. Chạy lặp lại không trùng."""
    cand = await db.get(Candidate, candidate_id)
    if cand is None:
        return
    for cat in {None, cand.category_id}:
        p = await _profile(db, cat)
        ex = dict(p.examples or {})
        pending = list(ex.get("pending") or [])
        if str(candidate_id) not in pending:
            pending.append(str(candidate_id))
        ex["pending"] = pending
        p.examples = ex
    await db.flush()


def traits_of(p: TasteProfile) -> list[dict[str, Any]]:
    return [{"trait": k, "weight": float(v)} for k, v in (p.weights or {}).items() if isinstance(v, int | float)]


async def retrain_taste(db: AsyncSession, category_id: uuid.UUID | None, *, force: bool = False) -> TasteProfile | None:
    p = await _profile(db, category_id)
    if not force and not (p.examples or {}).get("pending"):
        return None
    cand_q = select(Candidate.id, Candidate.title_vi).where(
        Candidate.stage.in_([CandidateStage.SELECTED, CandidateStage.REJECTED])
    )
    if category_id:
        cand_q = cand_q.where(Candidate.category_id == category_id)
    titles = dict((await db.execute(cand_q)).all())
    decisions = await latest_decisions(db, list(titles))
    if not decisions:
        return None
    cat_name = await db.scalar(select(Category.name).where(Category.id == category_id)) if category_id else None
    principles = [pr.text for pr in await active_principles(db, category_id)]
    inp = TasteIn(
        category_name=cat_name,
        decisions=[
            TasteDecision(
                decision=d.decision.value,  # type: ignore[arg-type]
                title=titles[cid],
                reasons=split_lines(d.reason_selected or d.draft_reason_selected),
                rejection_reason=d.rejection_reason,
                rejection_tags=list(d.rejection_tags or []),
            )
            for cid, d in decisions.items()
        ],
        principles=principles,
        previous_summary=p.summary,
        previous_traits=[TasteTraitOut(**t) for t in traits_of(p)],
        owner_edited=bool((p.examples or {}).get("owner_edited")),
    )
    try:
        res = await ai.run("selection.taste_profile", inp, TasteOut)
    except ai.AIError as e:
        log.warning("Chưa học được gu: %s", e)
        return None
    out = res.output
    selected = [str(cid) for cid, d in decisions.items() if d.decision == Decision.SELECTED]
    rejected = [str(cid) for cid, d in decisions.items() if d.decision == Decision.REJECTED]
    await control.propose(
        "selection.update_taste",
        f"Cập nhật gu của chị{f' · {cat_name}' if cat_name else ''}",
        {
            "profile_id": str(p.id),
            "summary": out.summary,
            "weights": {t.trait: t.weight for t in out.traits},
            "selected": selected,
            "rejected": rejected,
            "ai_run_id": str(res.run_id) if res.run_id else None,
        },
        {"summary": out.summary, "traits": [t.model_dump() for t in out.traits]},
        db=db,
        rationale=f"Từ {len(selected)} món đã chọn và {len(rejected)} món đã loại.",
        ref_type="taste_profiles",
        ref_id=p.id,
        ai_run_id=res.run_id,
        dedupe_key=f"taste:{p.id}",
    )
    return p


async def apply_taste(db: AsyncSession, payload: dict[str, Any]) -> tuple[TasteProfile, dict[str, Any]]:
    p = await db.get(TasteProfile, uuid.UUID(payload["profile_id"]))
    if p is None:
        raise NotFound("Không tìm thấy hồ sơ gu.")
    before = {"summary": p.summary, "weights": p.weights, "version": p.version}
    ex = dict(p.examples or {})
    ex.update(selected=payload.get("selected", []), rejected=payload.get("rejected", []), pending=[])
    p.examples = ex
    p.summary = payload.get("summary")
    p.weights = {str(k): float(v) for k, v in (payload.get("weights") or {}).items()}
    p.sample_count = len(ex["selected"]) + len(ex["rejected"])
    p.version = (p.version or 0) + 1
    p.trained_at = now_utc()
    if payload.get("ai_run_id"):
        p.ai_run_id = uuid.UUID(payload["ai_run_id"])
    await db.flush()
    return p, before


async def taste_categories(db: AsyncSession) -> list[uuid.UUID | None]:
    rows = (await db.execute(select(TasteProfile.category_id))).scalars()
    return list(rows)
