"""API bàn chọn (c1–c6): `/api/desk/selection/**` (cần đăng nhập) và `/api/store/selection/**` (công khai)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile, status
from sqlalchemy import select

from app import control
from app.core.db import DbSession
from app.core.deps import CurrentUser, OwnerUser
from app.core.errors import BadRequest, NotFound
from app.core.storage import get_storage, new_key
from app.modules.catalog.models import Category
from app.modules.selection import service
from app.modules.selection.models import (
    Decision,
    DraftStatus,
    SelectionDecision,
    SelectionPrinciple,
    TasteProfile,
    TrialNote,
    TrialNoteKind,
)
from app.modules.selection.schemas import (
    ApproveReasonsIn,
    BoardCard,
    BoardOut,
    CandidateDetail,
    CategoryLite,
    DecisionView,
    NoteUpdate,
    PrincipleIn,
    PrincipleUpdate,
    RedraftIn,
    RejectionStatsOut,
    RejectionUpdate,
    RejectReasonsOut,
    RetrainIn,
    SelectionPrincipleOut,
    SelectionSettings,
    StageChangeIn,
    StageChangeOut,
    TasteProfileUpdate,
    TasteProfileView,
    TrialNoteView,
)
from app.modules.sourcing.models import Candidate

router = APIRouter(prefix="/api/desk/selection", tags=["selection"])
routers = [router]

MAX_PHOTO_BYTES = 12 * 1024 * 1024
MAX_AUDIO_BYTES = 25 * 1024 * 1024
_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/heic": "heic", "image/gif": "gif",
        "audio/webm": "webm", "audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/wav": "wav",
        "audio/x-m4a": "m4a", "audio/aac": "aac"}  # fmt: skip


# ---- chuyển đổi sang schema màn hình -------------------------------------------------------------------------------


def note_view(n: TrialNote) -> TrialNoteView:
    base = TrialNoteView.model_validate(
        {
            **{c: getattr(n, c) for c in TrialNoteView.model_fields if hasattr(n, c)},
            "points": service.note_points(n),
            "photo_urls": [service.file_url(m.get("storage_key")) for m in n.media if m.get("storage_key")],
            "audio_url": service.file_url(n.audio_storage_key),
        }
    )
    return base


def decision_view(d: SelectionDecision) -> DecisionView:
    return DecisionView.model_validate(
        {
            **{c: getattr(d, c) for c in DecisionView.model_fields if hasattr(d, c)},
            "reasons_list": service.split_lines(d.reason_selected),
            "not_satisfied_list": service.split_lines(d.not_satisfied),
            "draft_reasons_list": service.split_lines(d.draft_reason_selected),
            "draft_not_satisfied_list": service.split_lines(d.draft_not_satisfied),
            "rejection_groups": [
                {"key": t, "label": service.REJECT_GROUP_LABELS.get(t, t)} for t in (d.rejection_tags or [])
            ],
        }
    )


async def card_of(db: DbSession, c: Candidate) -> BoardCard:
    return BoardCard.model_validate((await service.build_cards(db, [c]))[0])


async def _store_upload(f: UploadFile, prefix: str, kinds: tuple[str, ...], limit: int) -> dict[str, Any]:
    ctype = (f.content_type or "").split(";")[0].strip().lower()
    if not ctype.startswith(kinds):
        raise BadRequest(f"Tệp «{f.filename}» không đúng loại (cần ảnh hoặc ghi âm).", code="bad_file_type")
    data = await f.read()
    if len(data) > limit:
        raise BadRequest(f"Tệp «{f.filename}» quá lớn.", code="file_too_large")
    if not data:
        raise BadRequest(f"Tệp «{f.filename}» trống.", code="empty_file")
    ext = _EXT.get(ctype) or (f.filename.rsplit(".", 1)[-1] if f.filename and "." in f.filename else "bin")
    stored = await get_storage().put(new_key(prefix, ext), data, ctype)
    return {"storage_key": stored.key, "content_type": ctype, "size": stored.size}


async def _create_note(
    db: DbSession,
    user: Any,
    candidate: Candidate | None,
    text: str | None,
    photos: list[UploadFile] | None,
    audio: UploadFile | None,
    duration_seconds: int | None,
    recorded_at: datetime | None,
    voice: bool,
) -> TrialNote:
    media = [await _store_upload(p, "private/trial-notes", ("image/",), MAX_PHOTO_BYTES) for p in photos or [] if p]
    audio_key = None
    if audio is not None and audio.filename:
        audio_key = (
            await _store_upload(audio, "private/trial-notes/audio", ("audio/", "video/webm"), MAX_AUDIO_BYTES)
        )["storage_key"]
    kind = TrialNoteKind.VOICE if (voice or audio_key) else TrialNoteKind.TEXT
    if not (text or "").strip() and media and not audio_key:
        kind = TrialNoteKind.PHOTO
    return await service.create_note(
        db, candidate=candidate, text=text, kind=kind, user=user, photos=media, audio_key=audio_key,
        duration_seconds=duration_seconds, recorded_at=recorded_at,
    )  # fmt: skip


# ---- c1: bảng chọn -------------------------------------------------------------------------------------------------


@router.get("/board", response_model=BoardOut, summary="Bảng chọn (c1)")
async def get_board(_: CurrentUser, db: DbSession, q: str | None = None) -> dict:
    return await service.board(db, q)


@router.get("/settings", response_model=SelectionSettings)
async def get_settings(_: CurrentUser, db: DbSession) -> SelectionSettings:
    return SelectionSettings(trial_days=await service.trial_days(db))


@router.patch("/settings", response_model=SelectionSettings)
async def update_settings(body: SelectionSettings, user: OwnerUser, db: DbSession) -> SelectionSettings:
    await control.set_setting(db, service.TRIAL_DAYS_KEY, body.trial_days, user)
    return body


@router.get("/categories", response_model=list[CategoryLite], summary="Nhóm hàng (đọc bảng của catalog)")
async def list_categories(_: CurrentUser, db: DbSession) -> list[Category]:
    return list(
        (await db.execute(select(Category).where(Category.is_active.is_(True)).order_by(Category.position))).scalars()
    )


# ---- c4: lý do loại ------------------------------------------------------------------------------------------------


@router.get("/reject-reasons", response_model=RejectReasonsOut, summary="Nhóm lý do + lý do hay dùng (c4)")
async def get_reject_reasons(_: CurrentUser, db: DbSession) -> dict:
    return await service.reject_reasons(db)


@router.get("/rejection-stats", response_model=RejectionStatsOut, summary="Thống kê lý do loại (c4)")
async def get_rejection_stats(_: CurrentUser, db: DbSession, brief_id: uuid.UUID | None = None) -> dict:
    return await service.rejection_stats(db, brief_id=brief_id)


# ---- c5: bộ nguyên tắc ---------------------------------------------------------------------------------------------


@router.get("/principles", response_model=list[SelectionPrincipleOut], summary="Bộ nguyên tắc (c5)")
async def list_principles(
    _: CurrentUser, db: DbSession, category_id: uuid.UUID | None = None, active_only: bool = False
) -> list[SelectionPrinciple]:
    if category_id and active_only:
        return await service.active_principles(db, category_id)
    stmt = select(SelectionPrinciple).order_by(SelectionPrinciple.priority, SelectionPrinciple.created_at)
    if category_id:
        stmt = stmt.where(SelectionPrinciple.category_id == category_id)
    if active_only:
        stmt = stmt.where(SelectionPrinciple.is_active.is_(True))
    return list((await db.execute(stmt)).scalars())


async def _check_category(db: DbSession, category_id: uuid.UUID | None) -> None:
    if category_id and await db.get(Category, category_id) is None:
        raise BadRequest("Nhóm hàng không tồn tại.", code="bad_category")


@router.post("/principles", response_model=SelectionPrincipleOut, status_code=status.HTTP_201_CREATED)
async def create_principle(body: PrincipleIn, user: OwnerUser, db: DbSession) -> SelectionPrinciple:
    await _check_category(db, body.category_id)
    p = SelectionPrinciple(**body.model_dump(), created_by_id=user.id)
    p.text = p.text.strip()
    db.add(p)
    await db.flush()
    return p


@router.patch("/principles/{principle_id}", response_model=SelectionPrincipleOut)
async def update_principle(
    principle_id: uuid.UUID, body: PrincipleUpdate, _: OwnerUser, db: DbSession
) -> SelectionPrinciple:
    p = await db.get(SelectionPrinciple, principle_id)
    if p is None:
        raise NotFound("Không tìm thấy nguyên tắc này.")
    data = body.model_dump(exclude_unset=True, exclude={"clear_category"})
    if "category_id" in data:
        await _check_category(db, data["category_id"])
    for k, v in data.items():
        if v is not None:
            setattr(p, k, v.strip() if isinstance(v, str) else v)
    if body.clear_category:
        p.category_id = None
    await db.flush()
    return p


@router.delete("/principles/{principle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_principle(principle_id: uuid.UUID, _: OwnerUser, db: DbSession) -> None:
    p = await db.get(SelectionPrinciple, principle_id)
    if p is None:
        raise NotFound("Không tìm thấy nguyên tắc này.")
    await db.delete(p)


# ---- c6: gu của chị ------------------------------------------------------------------------------------------------


async def taste_view(db: DbSession, p: TasteProfile) -> TasteProfileView:
    name = await db.scalar(select(Category.name).where(Category.id == p.category_id)) if p.category_id else None
    traits = service.traits_of(p)
    ex = p.examples or {}
    return TasteProfileView.model_validate(
        {
            **{c: getattr(p, c) for c in TasteProfileView.model_fields if hasattr(p, c)},
            "category_name": name,
            "likes": sorted((t for t in traits if t["weight"] > 0), key=lambda t: -t["weight"]),
            "dislikes": sorted((t for t in traits if t["weight"] < 0), key=lambda t: t["weight"]),
            "pending_count": len(ex.get("pending") or []),
            "owner_edited": bool(ex.get("owner_edited")),
        }
    )


@router.get("/taste-profiles", response_model=list[TasteProfileView], summary="AI đang hiểu gu chị thế nào (c6)")
async def list_taste(_: CurrentUser, db: DbSession) -> list[TasteProfileView]:
    rows = (await db.execute(select(TasteProfile).order_by(TasteProfile.category_id.nulls_first()))).scalars()
    return [await taste_view(db, p) for p in rows]


@router.post("/taste-profiles/retrain", response_model=list[TasteProfileView], summary="Học lại gu ngay")
async def retrain_taste(body: RetrainIn, _: OwnerUser, db: DbSession) -> list[TasteProfileView]:
    cats = await service.taste_categories(db) if body.all else [body.category_id]
    for cat in cats or [None]:
        await service.retrain_taste(db, cat, force=True)
    rows = (await db.execute(select(TasteProfile).order_by(TasteProfile.category_id.nulls_first()))).scalars()
    return [await taste_view(db, p) for p in rows]


@router.patch("/taste-profiles/{profile_id}", response_model=TasteProfileView, summary="Chị sửa gu AI hiểu")
async def update_taste(profile_id: uuid.UUID, body: TasteProfileUpdate, user: OwnerUser, db: DbSession) -> Any:
    p = await db.get(TasteProfile, profile_id)
    if p is None:
        raise NotFound("Không tìm thấy hồ sơ gu.")
    if body.summary is not None:
        p.summary = body.summary.strip() or None
    if body.likes is not None or body.dislikes is not None:
        cur = service.traits_of(p)
        likes = body.likes if body.likes is not None else [t for t in cur if t["weight"] > 0]
        dislikes = body.dislikes if body.dislikes is not None else [t for t in cur if t["weight"] < 0]
        weights: dict[str, float] = {}
        for t in likes:
            t = t if isinstance(t, dict) else t.model_dump()
            weights[t["trait"].strip()] = abs(float(t["weight"])) or 0.5
        for t in dislikes:
            t = t if isinstance(t, dict) else t.model_dump()
            weights[t["trait"].strip()] = -(abs(float(t["weight"])) or 0.5)
        p.weights = weights
    p.examples = {**(p.examples or {}), "owner_edited": True}
    p.version = (p.version or 1) + 1
    await control.audit(
        db, "selection.taste_edited", user=user, entity_type="taste_profiles", entity_id=p.id, summary="Chị sửa gu"
    )
    return await taste_view(db, p)


# ---- c2: ghi chú chưa gắn món (AI xếp vào món) ---------------------------------------------------------------------


@router.get("/notes/unassigned", response_model=list[TrialNoteView], summary="Ghi chú AI chưa xếp được vào món")
async def unassigned_notes(_: CurrentUser, db: DbSession) -> list[TrialNoteView]:
    return [note_view(n) for n in await service.list_notes(db, None)]


@router.post(
    "/notes", response_model=TrialNoteView, status_code=status.HTTP_201_CREATED, summary="Ghi nhanh, AI xếp món"
)
async def create_loose_note(
    user: CurrentUser,
    db: DbSession,
    text: Annotated[str | None, Form(max_length=5000)] = None,
    voice: Annotated[bool, Form()] = False,
    duration_seconds: Annotated[int | None, Form(ge=0)] = None,
    recorded_at: Annotated[datetime | None, Form()] = None,
    photos: Annotated[list[UploadFile] | None, File()] = None,
    audio: Annotated[UploadFile | None, File()] = None,
) -> TrialNoteView:
    n = await _create_note(db, user, None, text, photos, audio, duration_seconds, recorded_at, voice)
    return note_view(n)


async def _note(db: DbSession, note_id: uuid.UUID) -> TrialNote:
    n = await db.get(TrialNote, note_id)
    if n is None:
        raise NotFound("Không tìm thấy ghi chú này.")
    return n


@router.patch("/notes/{note_id}", response_model=TrialNoteView)
async def update_note(note_id: uuid.UUID, body: NoteUpdate, _: CurrentUser, db: DbSession) -> TrialNoteView:
    n = await _note(db, note_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("candidate_id"):
        cand = await service.get_candidate(db, data["candidate_id"])
        n.candidate_id = cand.id
        n.ai_assigned = False
        n.trial_day = service.trial_day_of(cand)
    if "text" in data and data["text"] is not None:
        n.text = data["text"].strip() or None
    if body.points is not None:
        n.tags = [p.model_dump() for p in body.points]
    await db.flush()
    return note_view(n)


@router.post("/notes/{note_id}/reorganize", response_model=TrialNoteView, summary="AI sắp lại ghi chú")
async def reorganize_note(note_id: uuid.UUID, _: CurrentUser, db: DbSession) -> TrialNoteView:
    n = await _note(db, note_id)
    if not n.text:
        raise BadRequest("Ghi chú chưa có chữ để AI sắp.")
    await service.organize_note(db, n)
    return note_view(n)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: uuid.UUID, _: CurrentUser, db: DbSession) -> None:
    n = await _note(db, note_id)
    keys = [m.get("storage_key") for m in n.media] + [n.audio_storage_key]
    await db.delete(n)
    await db.flush()
    for k in keys:
        if k:
            try:
                await get_storage().delete(k)
            except Exception:  # tệp mất trước rồi: bỏ qua
                pass


# ---- ứng viên trên bảng --------------------------------------------------------------------------------------------


@router.get("/candidates/{candidate_id}", response_model=CandidateDetail, summary="Một món trên bảng chọn")
async def get_candidate(candidate_id: uuid.UUID, _: CurrentUser, db: DbSession) -> dict:
    c = await service.get_candidate(db, candidate_id)
    history = list(
        (
            await db.execute(
                select(SelectionDecision)
                .where(SelectionDecision.candidate_id == c.id)
                .order_by(SelectionDecision.decided_at.desc())
            )
        ).scalars()
    )
    card = await card_of(db, c)
    current = history[0] if history and c.stage.value in (Decision.SELECTED, Decision.REJECTED) else None
    if current is not None and current.decision == Decision.SELECTED and current.product_id is None:
        # sản phẩm nháp do catalog tạo khi nghe candidate.selected → ghi lại vào quyết định (bảng của selection)
        from app.modules.catalog.models import Product  # chỉ đọc

        current.product_id = await db.scalar(select(Product.id).where(Product.candidate_id == c.id))
    return {
        "card": card,
        "title_original": c.title_original,
        "source_url": c.source_url,
        "description_vi": c.description_vi,
        "seller_name": c.seller_name,
        "supplier_id": c.supplier_id,
        "price_amount": c.price_amount,
        "price_currency": c.price_currency,
        "weight_grams": c.weight_grams,
        "rank_reason": c.rank_reason,
        "notes": [note_view(n) for n in await service.list_notes(db, c.id)],
        "decision": decision_view(current) if current else None,
        "history": [decision_view(d) for d in history],
    }


@router.post("/candidates/{candidate_id}/stage", response_model=StageChangeOut, summary="Chuyển cột (c1, c3, c4)")
async def change_stage(candidate_id: uuid.UUID, body: StageChangeIn, user: OwnerUser, db: DbSession) -> dict:
    c, d = await service.change_stage(
        db, candidate_id, body.to, user, reason=body.reason, reason_tags=body.reason_tags, position=body.position
    )
    return {"card": await card_of(db, c), "decision": decision_view(d) if d else None}


@router.get("/candidates/{candidate_id}/notes", response_model=list[TrialNoteView])
async def candidate_notes(candidate_id: uuid.UUID, _: CurrentUser, db: DbSession) -> list[TrialNoteView]:
    await service.get_candidate(db, candidate_id)
    return [note_view(n) for n in await service.list_notes(db, candidate_id)]


@router.post(
    "/candidates/{candidate_id}/notes", response_model=TrialNoteView, status_code=status.HTTP_201_CREATED,
    summary="Ghi chú thử hàng: gõ, nói, ảnh, ghi âm (c2)",
)  # fmt: skip
async def create_note(
    candidate_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    text: Annotated[str | None, Form(max_length=5000)] = None,
    voice: Annotated[bool, Form()] = False,
    duration_seconds: Annotated[int | None, Form(ge=0)] = None,
    recorded_at: Annotated[datetime | None, Form()] = None,
    photos: Annotated[list[UploadFile] | None, File()] = None,
    audio: Annotated[UploadFile | None, File()] = None,
) -> TrialNoteView:
    c = await service.get_candidate(db, candidate_id)
    n = await _create_note(db, user, c, text, photos, audio, duration_seconds, recorded_at, voice)
    return note_view(n)


# ---- c3/c4: quyết định ---------------------------------------------------------------------------------------------


async def _decision(db: DbSession, decision_id: uuid.UUID) -> SelectionDecision:
    d = await db.get(SelectionDecision, decision_id)
    if d is None:
        raise NotFound("Không tìm thấy quyết định này.")
    return d


@router.get("/decisions/{decision_id}", response_model=DecisionView)
async def get_decision(decision_id: uuid.UUID, _: CurrentUser, db: DbSession) -> DecisionView:
    return decision_view(await _decision(db, decision_id))


@router.post("/decisions/{decision_id}/approve", response_model=DecisionView, summary="Chị sửa lời rồi chốt (c3)")
async def approve_reasons(
    decision_id: uuid.UUID, body: ApproveReasonsIn, user: OwnerUser, db: DbSession
) -> DecisionView:
    d = await service.approve_reasons(db, decision_id, user, body.reason_selected, body.not_satisfied)
    return decision_view(d)


@router.post("/decisions/{decision_id}/redraft", response_model=DecisionView, summary="AI soạn lại từ ghi chú (c3)")
async def redraft_reasons(decision_id: uuid.UUID, body: RedraftIn, _: OwnerUser, db: DbSession) -> DecisionView:
    d = await _decision(db, decision_id)
    if d.decision != Decision.SELECTED:
        raise BadRequest("Chỉ món đã chọn mới có lý do chọn.")
    if d.draft_status == DraftStatus.APPROVED:
        d.draft_status = DraftStatus.PENDING_REVIEW
    await service.draft_reasons(db, d, owner_request=body.note)
    return decision_view(d)


@router.patch("/decisions/{decision_id}", response_model=DecisionView, summary="Sửa lý do loại (c4)")
async def update_rejection(decision_id: uuid.UUID, body: RejectionUpdate, _: OwnerUser, db: DbSession) -> DecisionView:
    d = await _decision(db, decision_id)
    if d.decision != Decision.REJECTED:
        raise BadRequest("Chỉ món đã loại mới có lý do loại.")
    if body.rejection_reason is not None:
        d.rejection_reason = body.rejection_reason.strip()
    if body.rejection_tags is not None:
        d.rejection_tags = service.normalize_tags(body.rejection_tags, d.rejection_reason)
    if body.show_on_profile is not None:
        d.show_on_profile = body.show_on_profile
    await db.flush()
    return decision_view(d)
