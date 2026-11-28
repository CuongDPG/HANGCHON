"""API săn hàng: /api/desk/sourcing/** (cần đăng nhập; chị và người phụ đều dùng được)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from sqlalchemy import func, select

from app.core.db import DbSession
from app.core.deps import CurrentUser
from app.core.errors import BadRequest, NotFound
from app.core.jobs import enqueue
from app.core.pagination import Page, Paginated, paginate
from app.core.storage import get_storage, new_key
from app.modules.sourcing import guidance, service
from app.modules.sourcing.estimate import landed_total
from app.modules.sourcing.models import (
    BriefStatus,
    Candidate,
    CandidateStage,
    DemandMention,
    DemandSignal,
    DemandStatus,
    RunKind,
    SourcingBrief,
    SourcingRun,
    TrendSignal,
    TrendStatus,
)
from app.modules.sourcing.schemas import (
    BriefCard,
    BriefIn,
    BriefPatch,
    CandidateCard,
    CandidateDetail,
    CandidateGallery,
    ClipIn,
    ClipMatch,
    DemandMentionOut,
    DemandSignalOut,
    DemandView,
    DetailFetch,
    GalleryImage,
    ImportLinkIn,
    Offer,
    RankGuidance,
    ReinterpretIn,
    RunView,
    SourcingBriefOut,
    TrendCard,
)

router = APIRouter(prefix="/api/desk/sourcing", tags=["sourcing"])

MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}


def run_view(run: SourcingRun) -> RunView:
    return RunView.model_validate(run).model_copy(update={"progress": service.run_progress(run)})


async def _cards(db, briefs: list[SourcingBrief]) -> list[BriefCard]:
    ids = [b.id for b in briefs]
    counts, runs = await service.brief_counts(db, ids), await service.last_runs(db, ids)
    out = []
    for b in briefs:
        n, s = counts.get(b.id, (0, 0))
        r = runs.get(b.id)
        out.append(
            BriefCard.model_validate(b).model_copy(
                update={"candidate_count": n, "selected_count": s, "last_run": run_view(r) if r else None}
            )
        )
    return out


def rank_guidance(c: Candidate) -> RankGuidance | None:
    g = guidance.view(c.raw)
    return RankGuidance.model_validate(g) if g else None


async def candidate_cards(db, rows: list[Candidate]) -> list[CandidateCard]:
    from app.modules.assessment.models import Assessment  # cùng lát cắt, chỉ đọc

    rates = await service.fx_rates(db)
    ids = [c.id for c in rows]
    assessed = (
        {
            a.candidate_id: a
            for a in (await db.execute(select(Assessment).where(Assessment.candidate_id.in_(ids)))).scalars()
        }
        if ids
        else {}
    )
    out = []
    for c in rows:
        a = assessed.get(c.id)
        out.append(
            CandidateCard.model_validate(c).model_copy(
                update={
                    "landed_estimate_vnd": landed_total(
                        c.price_amount, c.price_currency, weight_grams=c.weight_grams, rates=rates
                    ),
                    "offers_count": len(service.offers_of(c)),
                    "guidance": rank_guidance(c),
                    "assessment_status": a.status.value if a else None,
                    "score_total": a.score_total if a else None,
                }
            )
        )
    return out


# ---- đề tìm (a1, a4, a7) -----------------------------------------------------------------------------------------


@router.get("/briefs", response_model=Paginated[BriefCard])
async def list_briefs(
    _: CurrentUser, db: DbSession, page: Page, status_: Annotated[BriefStatus | None, Query(alias="status")] = None
) -> Paginated[BriefCard]:
    q = select(SourcingBrief).order_by(SourcingBrief.updated_at.desc())
    q = q.where(SourcingBrief.status == status_) if status_ else q.where(SourcingBrief.status != BriefStatus.ARCHIVED)
    res = await paginate(db, q, page)
    return Paginated[BriefCard](**{**res.model_dump(exclude={"items"}), "items": await _cards(db, list(res.items))})


@router.post("/briefs", response_model=BriefCard, status_code=status.HTTP_201_CREATED)
async def create_brief(body: BriefIn, user: CurrentUser, db: DbSession) -> BriefCard:
    brief = await service.create_brief(db, body.text, input_mode=body.input_mode, user_id=user.id)
    await db.flush()
    await db.refresh(brief)
    return (await _cards(db, [brief]))[0]


@router.get("/briefs/{brief_id}", response_model=BriefCard)
async def get_brief(brief_id: uuid.UUID, _: CurrentUser, db: DbSession) -> BriefCard:
    return (await _cards(db, [await service.get_brief(db, brief_id)]))[0]


@router.patch("/briefs/{brief_id}", response_model=BriefCard)
async def patch_brief(brief_id: uuid.UUID, body: BriefPatch, _: CurrentUser, db: DbSession) -> BriefCard:
    brief = await service.get_brief(db, brief_id)
    service.apply_patch(brief, body)
    await db.flush()
    await db.refresh(brief)
    return (await _cards(db, [brief]))[0]


@router.post("/briefs/{brief_id}/reinterpret", response_model=BriefCard)
async def reinterpret(brief_id: uuid.UUID, body: ReinterpretIn, _: CurrentUser, db: DbSession) -> BriefCard:
    brief = await service.reinterpret(db, await service.get_brief(db, brief_id), body.text)
    await db.flush()
    await db.refresh(brief)
    return (await _cards(db, [brief]))[0]


@router.post("/briefs/{brief_id}/run", response_model=RunView)
async def run_brief(brief_id: uuid.UUID, _: CurrentUser, db: DbSession) -> RunView:
    """Xác nhận đề (nếu đang nháp) và quét nhiều nguồn (job nền, có tiến độ)."""
    run = await service.start_scan(db, await service.get_brief(db, brief_id))
    await db.commit()
    await enqueue("sourcing.scan_brief", run_id=str(run.id))
    await db.refresh(run)
    return run_view(run)


@router.get("/briefs/{brief_id}/candidates", response_model=Paginated[CandidateCard])
async def brief_candidates(
    brief_id: uuid.UUID,
    _: CurrentUser,
    db: DbSession,
    page: Page,
    stage: CandidateStage | None = None,
) -> Paginated[CandidateCard]:
    await service.get_brief(db, brief_id)
    q = select(Candidate).where(Candidate.brief_id == brief_id, Candidate.is_archived.is_(False))
    if stage:
        q = q.where(Candidate.stage == stage)
    violates = func.coalesce(Candidate.raw["guidance"]["violates"].as_boolean(), False)  # trái nguyên tắc xuống cuối
    q = q.order_by(violates, Candidate.ai_score.desc().nulls_last(), Candidate.created_at)
    res = await paginate(db, q, page)
    return Paginated[CandidateCard](
        **{**res.model_dump(exclude={"items"}), "items": await candidate_cards(db, list(res.items))}
    )


@router.get("/briefs/{brief_id}/runs", response_model=list[RunView])
async def brief_runs(brief_id: uuid.UUID, _: CurrentUser, db: DbSession) -> list[RunView]:
    rows = (
        await db.execute(
            select(SourcingRun)
            .where(SourcingRun.brief_id == brief_id)
            .order_by(SourcingRun.created_at.desc())
            .limit(20)
        )
    ).scalars()
    return [run_view(r) for r in rows]


# ---- lượt tìm ----------------------------------------------------------------------------------------------------


@router.get("/runs/{run_id}", response_model=RunView)
async def get_run(run_id: uuid.UUID, _: CurrentUser, db: DbSession) -> RunView:
    return run_view(await service.get_run(db, run_id))


# ---- a2: dán link ------------------------------------------------------------------------------------------------


@router.post("/import-link", response_model=RunView)
async def import_link(body: ImportLinkIn, user: CurrentUser, db: DbSession) -> RunView:
    url = str(body.url)
    if len(url) > 2000:
        raise BadRequest("Link quá dài.")
    if body.brief_id:
        await service.get_brief(db, body.brief_id)
    brief = await db.get(SourcingBrief, body.brief_id) if body.brief_id else None
    run = await service.start_run(db, RunKind.LINK_IMPORT, brief=brief, input={"url": url, "user_id": str(user.id)})
    await db.commit()
    await enqueue("sourcing.import_link", run_id=str(run.id))
    await db.refresh(run)
    return run_view(run)


# ---- «Gửi sang Hàng Chọn»: trang sản phẩm chị mở trên trình duyệt (web/src/lib/clipper) --------------------------


@router.get("/clip/match", response_model=ClipMatch)
async def clip_match(_: CurrentUser, db: DbSession, url: Annotated[str, Query(max_length=2000)]) -> ClipMatch:
    """Cửa sổ /desk/kep hỏi trước: trang này là món nào, đã có ứng viên chưa (cùng sàn + mã món)."""
    if not url.startswith("https://"):
        raise BadRequest("Link trang phải là https.")
    platform, ext_id, canon = service.clip_identity(url)
    c = await service.find_by_source(db, platform, ext_id)
    return ClipMatch(
        platform=platform,
        platform_label=service.platform_label(platform),
        external_id=ext_id,
        canonical_url=canon,
        candidate_id=c.id if c else None,
        candidate_title=c.title_vi if c else None,
        brief_id=c.brief_id if c else None,
        thumb_url=c.thumb_url if c else None,
    )


@router.post("/clip", response_model=RunView)
async def clip(body: ClipIn, user: CurrentUser, db: DbSession) -> RunView:
    """Lưu trang chị gửi thành ứng viên (mới, hoặc cập nhật món cùng sàn + mã) — đi đường «dán link» không đọc trang."""
    brief = await service.get_brief(db, body.brief_id) if body.brief_id else None
    _, _, canon = service.clip_identity(body.url)
    payload = body.model_dump(mode="json", exclude={"brief_id"})
    run = await service.start_run(
        db, RunKind.LINK_IMPORT, brief=brief, input={"url": canon, "clip": payload, "user_id": str(user.id)}
    )
    await db.commit()
    await enqueue("sourcing.import_link", run_id=str(run.id))
    await db.refresh(run)
    return run_view(run)


# ---- a3: tìm bằng ảnh --------------------------------------------------------------------------------------------


@router.post("/image-search", response_model=RunView)
async def image_search(
    user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File(description="Ảnh chụp món hàng")],
    note: Annotated[str | None, Form(max_length=500)] = None,
) -> RunView:
    ctype = (file.content_type or "").lower()
    if ctype not in IMAGE_TYPES:
        raise BadRequest("Chị chọn ảnh JPG, PNG hoặc WEBP nhé.")
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if not data:
        raise BadRequest("Ảnh trống.")
    if len(data) > MAX_IMAGE_BYTES:
        raise BadRequest("Ảnh lớn quá 8 MB, chị chọn ảnh nhỏ hơn.")
    stored = await get_storage().put(new_key("private/sourcing/images", IMAGE_TYPES[ctype]), data, ctype)
    run = await service.start_run(
        db,
        RunKind.IMAGE_SEARCH,
        input={
            "storage_key": stored.key,
            "content_type": ctype,
            "note": (note or "").strip() or None,
            "user_id": str(user.id),
        },
    )
    await db.commit()
    await enqueue("sourcing.image_search", run_id=str(run.id))
    await db.refresh(run)
    return run_view(run)


# ---- ứng viên ----------------------------------------------------------------------------------------------------


@router.get("/candidates", response_model=Paginated[CandidateCard])
async def list_candidates(
    _: CurrentUser,
    db: DbSession,
    page: Page,
    brief_id: uuid.UUID | None = None,
    stage: CandidateStage | None = None,
) -> Paginated[CandidateCard]:
    q = select(Candidate).where(Candidate.is_archived.is_(False))
    if brief_id:
        q = q.where(Candidate.brief_id == brief_id)
    if stage:
        q = q.where(Candidate.stage == stage)
    res = await paginate(db, q.order_by(Candidate.created_at.desc()), page)
    return Paginated[CandidateCard](
        **{**res.model_dump(exclude={"items"}), "items": await candidate_cards(db, list(res.items))}
    )


@router.get("/candidates/{candidate_id}", response_model=CandidateDetail)
async def get_candidate(candidate_id: uuid.UUID, _: CurrentUser, db: DbSession) -> CandidateDetail:
    c = await service.get_candidate(db, candidate_id)
    rates = await service.fx_rates(db)
    return CandidateDetail.model_validate(c).model_copy(
        update={
            "landed_estimate_vnd": landed_total(
                c.price_amount, c.price_currency, weight_grams=c.weight_grams, rates=rates
            ),
            "offers": [Offer.model_validate(o) for o in service.offers_of(c)],
            "guidance": rank_guidance(c),
        }
    )


def gallery_view(c: Candidate) -> CandidateGallery:
    st = service.detail_state(c)
    return CandidateGallery(
        candidate_id=c.id,
        title_vi=c.title_vi,
        source_url=c.source_url,
        images=[GalleryImage.model_validate(g) for g in c.gallery],
        detail_fetch=DetailFetch.model_validate(st) if st and st.get("status") else None,
    )


@router.get("/candidates/{candidate_id}/gallery", response_model=CandidateGallery)
async def candidate_gallery(candidate_id: uuid.UUID, _: CurrentUser, db: DbSession) -> CandidateGallery:
    """Ảnh nhà cung cấp của một ứng viên (chỉ desk) + trạng thái «Lấy ảnh và chi tiết»."""
    return gallery_view(await service.get_candidate(db, candidate_id))


@router.post("/candidates/{candidate_id}/fetch-details", response_model=CandidateGallery)
async def fetch_details(candidate_id: uuid.UUID, _: CurrentUser, db: DbSession) -> CandidateGallery:
    """«Lấy ảnh và chi tiết»: đọc trang nguồn (job nền) rồi lưu ảnh về kho riêng. Đang chạy thì không xếp thêm."""
    c = await service.get_candidate(db, candidate_id)
    if service.request_details(c):
        await db.commit()
        await enqueue("sourcing.fetch_details", candidate_id=str(c.id))
        await db.refresh(c)
    return gallery_view(c)


# ---- a5: radar xu hướng ------------------------------------------------------------------------------------------


@router.get("/trends", response_model=Paginated[TrendCard])
async def list_trends(
    _: CurrentUser, db: DbSession, page: Page, status_: Annotated[TrendStatus | None, Query(alias="status")] = None
) -> Paginated[TrendCard]:
    q = select(TrendSignal)
    q = q.where(TrendSignal.status == status_) if status_ else q.where(TrendSignal.status != TrendStatus.DISMISSED)
    res = await paginate(db, q.order_by(TrendSignal.detected_on.desc(), TrendSignal.score.desc().nulls_last()), page)
    briefs = {}
    ids = [str(t.id) for t in res.items]
    if ids:
        rows = (
            await db.execute(
                select(SourcingBrief.id, SourcingBrief.filters["trend_signal_id"].astext).where(
                    SourcingBrief.filters["trend_signal_id"].astext.in_(ids)
                )
            )
        ).all()
        briefs = {tid: bid for bid, tid in rows}
    items = [TrendCard.model_validate(t).model_copy(update={"brief_id": briefs.get(str(t.id))}) for t in res.items]
    return Paginated[TrendCard](**{**res.model_dump(exclude={"items"}), "items": items})


@router.post("/trends/refresh", response_model=RunView)
async def refresh_trends(_: CurrentUser, db: DbSession) -> RunView:
    run = await service.start_run(db, RunKind.TREND_RADAR)
    await db.commit()
    await enqueue("sourcing.trend_radar", run_id=str(run.id))
    await db.refresh(run)
    return run_view(run)


async def _trend(db, trend_id: uuid.UUID) -> TrendSignal:
    t = await db.get(TrendSignal, trend_id)
    if t is None:
        raise NotFound("Không tìm thấy tín hiệu này.")
    return t


@router.post("/trends/{trend_id}/brief", response_model=BriefCard, status_code=status.HTTP_201_CREATED)
async def trend_brief(trend_id: uuid.UUID, user: CurrentUser, db: DbSession) -> BriefCard:
    """Mở đề tìm từ tín hiệu xu hướng (đề nháp, chị xem «AI hiểu là» rồi mới tìm)."""
    brief = await service.brief_from_trend(db, await _trend(db, trend_id), user.id)
    await db.flush()
    await db.refresh(brief)
    return (await _cards(db, [brief]))[0]


@router.post("/trends/{trend_id}/dismiss", response_model=TrendCard)
async def dismiss_trend(trend_id: uuid.UUID, _: CurrentUser, db: DbSession) -> TrendCard:
    t = await _trend(db, trend_id)
    t.status = TrendStatus.DISMISSED
    await db.flush()
    await db.refresh(t)
    return TrendCard.model_validate(t)


# ---- a6: nghe khách muốn gì --------------------------------------------------------------------------------------


async def _demand_views(db, signals: list[DemandSignal]) -> list[DemandView]:
    ids = [s.id for s in signals]
    mentions: dict[uuid.UUID, list[DemandMention]] = {}
    briefs: dict[uuid.UUID, uuid.UUID] = {}
    if ids:
        for m in (
            await db.execute(
                select(DemandMention).where(DemandMention.signal_id.in_(ids)).order_by(DemandMention.created_at.desc())
            )
        ).scalars():
            mentions.setdefault(m.signal_id, []).append(m)
        briefs = dict(
            (
                await db.execute(
                    select(SourcingBrief.demand_signal_id, SourcingBrief.id).where(
                        SourcingBrief.demand_signal_id.in_(ids)
                    )
                )
            ).all()
        )
    return [
        DemandView(
            **DemandSignalOut.model_validate(s).model_dump(),
            mentions=[DemandMentionOut.model_validate(m) for m in mentions.get(s.id, [])[:5]],
            brief_id=briefs.get(s.id),
        )
        for s in signals
    ]


@router.get("/demand", response_model=Paginated[DemandView])
async def list_demand(
    _: CurrentUser, db: DbSession, page: Page, status_: Annotated[DemandStatus | None, Query(alias="status")] = None
) -> Paginated[DemandView]:
    q = select(DemandSignal)
    q = q.where(DemandSignal.status == status_) if status_ else q.where(DemandSignal.status != DemandStatus.DISMISSED)
    q = q.order_by(DemandSignal.ask_count.desc(), DemandSignal.last_asked_at.desc().nulls_last())
    res = await paginate(db, q, page)
    return Paginated[DemandView](
        **{**res.model_dump(exclude={"items"}), "items": await _demand_views(db, list(res.items))}
    )


@router.post("/demand/digest", response_model=RunView)
async def digest_demand(_: CurrentUser, db: DbSession) -> RunView:
    run = await service.start_run(db, RunKind.DEMAND_DIGEST)
    await db.commit()
    await enqueue("sourcing.demand_digest", run_id=str(run.id))
    await db.refresh(run)
    return run_view(run)


async def _signal(db, signal_id: uuid.UUID) -> DemandSignal:
    s = await db.get(DemandSignal, signal_id)
    if s is None:
        raise NotFound("Không tìm thấy nhu cầu này.")
    return s


@router.post("/demand/{signal_id}/brief", response_model=BriefCard, status_code=status.HTTP_201_CREATED)
async def demand_brief(signal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> BriefCard:
    brief = await service.brief_from_demand(db, await _signal(db, signal_id), user.id)
    await db.flush()
    await db.refresh(brief)
    return (await _cards(db, [brief]))[0]


@router.post("/demand/{signal_id}/dismiss", response_model=DemandView)
async def dismiss_demand(signal_id: uuid.UUID, _: CurrentUser, db: DbSession) -> DemandView:
    s = await _signal(db, signal_id)
    s.status = DemandStatus.DISMISSED
    await db.flush()
    await db.refresh(s)
    return (await _demand_views(db, [s]))[0]


__all__ = ["SourcingBriefOut", "candidate_cards", "router"]
