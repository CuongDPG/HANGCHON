"""API thẩm định: /api/desk/assessment/** . Xem: chị và người phụ. Sửa điểm, duyệt điểm/an toàn, sửa khung chấm: chỉ chị."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.core.db import DbSession
from app.core.deps import CurrentUser, OwnerUser
from app.core.errors import BadRequest, NotFound
from app.core.jobs import enqueue
from app.core.pagination import Page, Paginated, paginate
from app.modules.assessment import service
from app.modules.assessment.models import Assessment, Comparison, ScoringProfile
from app.modules.assessment.schemas import (
    AssessmentView,
    BriefRef,
    CompareRequest,
    ComparisonOut,
    ComparisonView,
    ConfirmSafetyIn,
    CostView,
    MarketPriceOut,
    MarketView,
    OwnerScoreIn,
    ProfilePage,
    ReviewDigestOut,
    RunIn,
    ScoreView,
    ScoringProfileIn,
    ScoringProfileOut,
    ScoringProfilePatch,
    WarningItem,
)
from app.modules.sourcing.estimate import landed_total
from app.modules.sourcing.models import Candidate, CandidateStage, SourcingBrief
from app.modules.sourcing.router import candidate_cards
from app.modules.sourcing.schemas import CandidateDetail, Offer

router = APIRouter(prefix="/api/desk/assessment", tags=["assessment"])


def assessment_view(a: Assessment) -> AssessmentView:
    scores = [
        ScoreView.model_validate(s).model_copy(
            update={
                "effective_score": service.effective(s),
                "points": float(service.effective(s)) * float(s.weight) / 10
                if service.effective(s) is not None
                else None,
            }
        )
        for s in a.scores
    ]
    return AssessmentView.model_validate(a).model_copy(
        update={"scores": scores, "pending_steps": list((a.price_overview or {}).get("pending_steps") or [])}
    )


async def _profile_page(db, c: Candidate) -> ProfilePage:
    a = await service.assessment_of(db, c.id)
    rates = await service._rates(db)
    detail = CandidateDetail.model_validate(c).model_copy(
        update={
            "landed_estimate_vnd": landed_total(
                c.price_amount, c.price_currency, weight_grams=c.weight_grams, rates=rates
            ),
            "offers": [Offer.model_validate(o) for o in (c.raw or {}).get("offers", [])],
        }
    )
    brief_ref = None
    if c.brief_id:
        brief = await db.get(SourcingBrief, c.brief_id)
        if brief is not None:
            n, s = (
                await db.execute(
                    select(func.count(), func.count().filter(Candidate.stage == CandidateStage.SELECTED)).where(
                        Candidate.brief_id == brief.id
                    )
                )
            ).one()
            brief_ref = BriefRef(id=brief.id, title=brief.title, considered_count=n, selected_count=s)
    cost = await service.cost_view(db, c, a)
    rows = await service.latest_market(db, c.id)
    mk = service.market_summary(rows, cost["landed_cost_vnd"] if cost else None)
    digest = await service.latest_digest(db, c.id)
    prof = (
        await db.get(ScoringProfile, a.scoring_profile_id)
        if a and a.scoring_profile_id
        else await service.profile_for(db, c.category_id)
    )
    return ProfilePage(
        candidate=detail,
        brief=brief_ref,
        assessment=assessment_view(a) if a else None,
        review_digest=ReviewDigestOut.model_validate(digest) if digest else None,
        cost=CostView.model_validate(cost) if cost else None,
        market=MarketView(**mk, listings=[MarketPriceOut.model_validate(r) for r in rows]) if mk else None,
        warnings=[WarningItem.model_validate(w) for w in service.warnings_for(a, c, cost)],
        scoring_profile=ScoringProfileOut.model_validate(prof or await service.ensure_default_profile(db)),
    )


# ---- b1: hồ sơ thẩm định -----------------------------------------------------------------------------------------


@router.get("/candidates/{candidate_id}", response_model=ProfilePage)
async def get_profile(candidate_id: uuid.UUID, _: CurrentUser, db: DbSession) -> ProfilePage:
    return await _profile_page(db, await service.get_candidate(db, candidate_id))


@router.post("/candidates/{candidate_id}/run", response_model=AssessmentView)
async def run_assessment(candidate_id: uuid.UUID, body: RunIn, _: CurrentUser, db: DbSession) -> AssessmentView:
    """Chạy (lại) thẩm định — job nền; web hỏi lại GET hồ sơ tới khi `status` là ready/failed."""
    c = await service.get_candidate(db, candidate_id)
    a = await service.request_run(db, c, list(body.steps) if body.steps else None)
    await db.commit()
    if a.status != "running":
        await enqueue("assessment.run", candidate_id=str(c.id))
    a = await db.get(Assessment, a.id, populate_existing=True)
    assert a is not None
    return assessment_view(a)


# ---- b4: chị sửa điểm từng dòng ----------------------------------------------------------------------------------


@router.patch("/assessments/{assessment_id}/scores/{criterion_key}", response_model=AssessmentView)
async def set_score(
    assessment_id: uuid.UUID, criterion_key: str, body: OwnerScoreIn, _: OwnerUser, db: DbSession
) -> AssessmentView:
    a = await service.get_assessment(db, assessment_id)
    score = body.owner_score.quantize(Decimal("0.1")) if body.owner_score is not None else None
    await service.set_owner_score(db, a, criterion_key, score, (body.owner_note or "").strip() or None)
    await db.flush()
    return assessment_view(a)


@router.post("/assessments/{assessment_id}/confirm-score", response_model=AssessmentView)
async def confirm_score(assessment_id: uuid.UUID, user: OwnerUser, db: DbSession) -> AssessmentView:
    a = await service.confirm_score(db, await service.get_assessment(db, assessment_id), user.id)
    return assessment_view(a)


@router.post("/assessments/{assessment_id}/confirm-safety", response_model=AssessmentView)
async def confirm_safety(
    assessment_id: uuid.UUID, body: ConfirmSafetyIn, user: OwnerUser, db: DbSession
) -> AssessmentView:
    a = service.confirm_safety(await service.get_assessment(db, assessment_id), body.status, body.note, user.id)
    await db.flush()
    return assessment_view(a)


# ---- b4: khung chấm điểm -----------------------------------------------------------------------------------------


@router.get("/scoring-profiles", response_model=list[ScoringProfileOut])
async def list_profiles(_: CurrentUser, db: DbSession) -> list[ScoringProfile]:
    await service.ensure_default_profile(db)
    rows = await db.execute(select(ScoringProfile).order_by(ScoringProfile.is_default.desc(), ScoringProfile.name))
    return list(rows.scalars().all())


def _criteria(items) -> list[dict]:
    return service.validate_criteria(
        [{**c.model_dump(), "weight": float(c.weight) if c.weight % 1 else int(c.weight)} for c in items]
    )


@router.post("/scoring-profiles", response_model=ScoringProfileOut, status_code=status.HTTP_201_CREATED)
async def create_profile(body: ScoringProfileIn, _: OwnerUser, db: DbSession) -> ScoringProfile:
    if body.category_id is None:
        raise BadRequest("Khung riêng phải gắn với một nhóm hàng; khung chung đã có sẵn.")
    exists = await db.execute(select(ScoringProfile.id).where(ScoringProfile.category_id == body.category_id))
    if exists.first():
        raise BadRequest("Nhóm hàng này đã có khung chấm riêng.")
    prof = ScoringProfile(
        name=body.name, category_id=body.category_id, criteria=_criteria(body.criteria), pass_score=body.pass_score
    )
    db.add(prof)
    await db.flush()
    await db.refresh(prof)
    return prof


async def _prof(db, profile_id: uuid.UUID) -> ScoringProfile:
    prof = await db.get(ScoringProfile, profile_id)
    if prof is None:
        raise NotFound("Không tìm thấy khung chấm này.")
    return prof


@router.patch("/scoring-profiles/{profile_id}", response_model=ScoringProfileOut)
async def patch_profile(
    profile_id: uuid.UUID, body: ScoringProfilePatch, _: OwnerUser, db: DbSession
) -> ScoringProfile:
    prof = await _prof(db, profile_id)
    if body.name is not None:
        prof.name = body.name
    if body.criteria is not None:
        prof.criteria = _criteria(body.criteria)
    if "pass_score" in body.model_fields_set:
        prof.pass_score = body.pass_score
    await db.flush()
    await db.refresh(prof)
    return prof


@router.delete("/scoring-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: uuid.UUID, _: OwnerUser, db: DbSession) -> None:
    prof = await _prof(db, profile_id)
    if prof.is_default:
        raise BadRequest("Không xoá được khung mặc định.")
    await db.delete(prof)


# ---- b3: so sánh -------------------------------------------------------------------------------------------------


async def _comparison_view(db, comp: Comparison) -> ComparisonView:
    ids = [i.candidate_id for i in comp.items]
    rows = (await db.execute(select(Candidate).where(Candidate.id.in_(ids)))).scalars().all()
    by_id = {c.id: c for c in rows}
    cards = await candidate_cards(db, [by_id[i] for i in ids if i in by_id])
    return ComparisonView.model_validate(comp).model_copy(update={"candidates": cards})


@router.post("/comparisons", response_model=ComparisonView, status_code=status.HTTP_201_CREATED)
async def create_comparison(body: CompareRequest, _: CurrentUser, db: DbSession) -> ComparisonView:
    comp = await service.create_comparison(db, body.candidate_ids, body.title)
    await db.flush()
    await db.refresh(comp)
    return await _comparison_view(db, comp)


@router.get("/comparisons", response_model=Paginated[ComparisonOut])
async def list_comparisons(
    _: CurrentUser, db: DbSession, page: Page, brief_id: uuid.UUID | None = None
) -> Paginated[ComparisonOut]:
    q = select(Comparison).order_by(Comparison.created_at.desc())
    if brief_id:
        q = q.where(Comparison.brief_id == brief_id)
    return await paginate(db, q, page, ComparisonOut)


@router.get("/comparisons/{comparison_id}", response_model=ComparisonView)
async def get_comparison(comparison_id: uuid.UUID, _: CurrentUser, db: DbSession) -> ComparisonView:
    comp = await db.get(Comparison, comparison_id)
    if comp is None:
        raise NotFound("Không tìm thấy bảng so sánh này.")
    return await _comparison_view(db, comp)
