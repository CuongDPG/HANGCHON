"""Nghiệp vụ thẩm định (b1–b7).

Một lượt thẩm định (job `assessment.run`) đi các bước: lấy chi tiết + đánh giá từ nguồn → đọc hộ đánh giá (b2) →
giá ở Việt Nam (b5) → an toàn (b6) → cảnh báo nhái/ảo (b7) → viết hồ sơ + chấm nháp (b1, b4). Mỗi bước là một
`ai.run` (b7 là luật tính trong code) rồi `control.propose` với action riêng; bước lỗi không chặn bước sau.
Xong thì phát `candidate.assessed`."""

from __future__ import annotations

import logging
import statistics
import uuid
from collections import Counter
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app import ai, control
from app.core import events
from app.core.enums import Language, SourcePlatform
from app.core.errors import BadRequest, NotFound
from app.core.money import margin_pct, round_vnd
from app.core.timeutil import now_utc
from app.integrations import IntegrationError, IntegrationNotConfigured, get_driver
from app.integrations.sources import SourceReview
from app.modules.assessment.ai_io import (
    CompareCandidate,
    CompareIn,
    CompareOut,
    CriterionIn,
    DigestIn,
    DigestOut,
    EvaluateIn,
    EvaluateOut,
    ListingIn,
    MatchIn,
    MatchOut,
    ReviewIn,
    SafetyIn,
    SafetyOut,
)
from app.modules.assessment.models import (
    Assessment,
    AssessmentScore,
    AssessmentStatus,
    Comparison,
    ComparisonItem,
    MarketPrice,
    ReviewDigest,
    RiskLevel,
    SafetyStatus,
    ScoreStatus,
    ScoringProfile,
)
from app.modules.sourcing.ai_io import TranslateIn, TranslateOut
from app.modules.sourcing.estimate import DEFAULT_FX, FX_SETTING_KEY, estimate_landed
from app.modules.sourcing.models import Candidate, SourcingBrief

log = logging.getLogger("app.assessment")

STEPS = ("details", "reviews", "market", "safety", "risk", "score")
MAX_REVIEWS_FOR_AI = 80
MIN_MATCH = 0.6

# Bảy tiêu chí mặc định theo bản thiết kế (wireframe «Hồ sơ thẩm định»), tổng trọng số 100.
DEFAULT_CRITERIA: list[dict[str, Any]] = [
    {"key": "chat_luong", "label": "Chất lượng", "weight": 25, "description": "Chắc, bền, đánh giá dài hạn tốt"},
    {
        "key": "an_toan",
        "label": "An toàn",
        "weight": 20,
        "description": "Chất liệu, tiếp xúc thực phẩm, pin/chất lỏng, giấy tờ",
    },
    {
        "key": "bien_loi_nhuan",
        "label": "Biên lợi nhuận",
        "weight": 15,
        "description": "Giá về tay so với giá bán ở Việt Nam",
    },
    {"key": "khac_biet", "label": "Khác biệt", "weight": 15, "description": "Có gì hơn hàng đang bán ở Việt Nam"},
    {
        "key": "hang_nhai",
        "label": "Hàng nhái",
        "weight": 10,
        "description": "Điểm cao = ít rủi ro hàng nhái, đánh giá ảo",
    },
    {"key": "nguon", "label": "Nguồn", "weight": 10, "description": "Người bán uy tín, có nguồn dự phòng"},
    {"key": "van_chuyen", "label": "Vận chuyển", "weight": 5, "description": "Nhẹ, ít vỡ, không pin/chất lỏng"},
]
DEFAULT_PASS_SCORE = 70
# Bộ tiêu chí cũ do app/seed.py của nền móng tạo (khác bản thiết kế) — seed_demo đổi sang bộ mặc định ở trên.
LEGACY_KEYS = {"cong_nang", "do_ben", "an_toan", "de_dung", "tham_my", "gia_tri", "van_chuyen"}


def sources():
    return get_driver("sources")


async def _rates(db: AsyncSession) -> dict[str, Any]:
    v = await control.get_setting(db, FX_SETTING_KEY, None)
    return v if isinstance(v, dict) else dict(DEFAULT_FX)


# ---- khung chấm điểm (b4) ----------------------------------------------------------------------------------------


def validate_criteria(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not 3 <= len(criteria) <= 10:
        raise BadRequest("Khung chấm cần từ 3 đến 10 tiêu chí.")
    keys = [c["key"] for c in criteria]
    if len(set(keys)) != len(keys):
        raise BadRequest("Hai tiêu chí trùng mã.")
    total = sum(Decimal(str(c["weight"])) for c in criteria)
    if total != 100:
        raise BadRequest(f"Tổng trọng số phải là 100 (đang là {total.normalize():f}).")
    return criteria


async def ensure_default_profile(db: AsyncSession) -> ScoringProfile:
    prof = (
        await db.execute(select(ScoringProfile).where(ScoringProfile.is_default.is_(True)).limit(1))
    ).scalar_one_or_none()
    if prof is None:
        prof = ScoringProfile(
            name="Khung mặc định", is_default=True, pass_score=DEFAULT_PASS_SCORE, criteria=list(DEFAULT_CRITERIA)
        )
        db.add(prof)
        await db.flush()
    return prof


async def profile_for(db: AsyncSession, category_id: uuid.UUID | None) -> ScoringProfile:
    if category_id:
        prof = (
            await db.execute(select(ScoringProfile).where(ScoringProfile.category_id == category_id).limit(1))
        ).scalar_one_or_none()
        if prof is not None:
            return prof
    return await ensure_default_profile(db)


def effective(s: AssessmentScore) -> Decimal | None:
    return s.owner_score if s.owner_score is not None else s.ai_score


def recompute_total(a: Assessment) -> None:
    total = Decimal(0)
    weights = Decimal(0)
    for s in a.scores:
        e = effective(s)
        if e is None:
            continue
        total += Decimal(e) * Decimal(s.weight) / 10
        weights += Decimal(s.weight)
    a.score_total = (total * 100 / weights).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if weights else None


# ---- đọc ---------------------------------------------------------------------------------------------------------


async def get_candidate(db: AsyncSession, candidate_id: uuid.UUID) -> Candidate:
    c = await db.get(Candidate, candidate_id)
    if c is None:
        raise NotFound("Không tìm thấy ứng viên này.")
    return c


async def get_assessment(db: AsyncSession, assessment_id: uuid.UUID) -> Assessment:
    a = await db.get(Assessment, assessment_id)
    if a is None:
        raise NotFound("Không tìm thấy hồ sơ thẩm định.")
    return a


async def assessment_of(db: AsyncSession, candidate_id: uuid.UUID) -> Assessment | None:
    return (await db.execute(select(Assessment).where(Assessment.candidate_id == candidate_id))).scalar_one_or_none()


async def latest_digest(db: AsyncSession, candidate_id: uuid.UUID) -> ReviewDigest | None:
    q = select(ReviewDigest).where(ReviewDigest.candidate_id == candidate_id).order_by(ReviewDigest.created_at.desc())
    return (await db.execute(q.limit(1))).scalar_one_or_none()


async def latest_market(db: AsyncSession, candidate_id: uuid.UUID) -> list[MarketPrice]:
    last = (
        await db.execute(
            select(MarketPrice.captured_at)
            .where(MarketPrice.candidate_id == candidate_id)
            .order_by(MarketPrice.captured_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last is None:
        return []
    rows = await db.execute(
        select(MarketPrice)
        .where(MarketPrice.candidate_id == candidate_id, MarketPrice.captured_at == last)
        .order_by(MarketPrice.price_vnd)
    )
    return list(rows.scalars().all())


def _weight(c: Candidate, a: Assessment | None) -> int | None:
    return c.weight_grams or ((a.price_overview or {}).get("weight_grams") if a else None)


async def cost_view(db: AsyncSession, c: Candidate, a: Assessment | None) -> dict[str, Any] | None:
    """Giá vốn về tay: bảng giá vốn hiện hành của module supply nếu có, không thì ước tính sơ bộ (ghi rõ)."""
    from app.modules.supply.models import CostSheet  # chỉ đọc

    sheet = (
        await db.execute(
            select(CostSheet)
            .where(CostSheet.candidate_id == c.id, CostSheet.is_current.is_(True))
            .order_by(CostSheet.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if sheet is not None:
        lines = sheet.breakdown or [
            {"label": "Giá gốc", "amount_vnd": sheet.unit_price_vnd},
            {"label": "Cước nội địa, mua hộ", "amount_vnd": sheet.domestic_shipping_vnd + sheet.agent_fee_vnd},
            {"label": "Cước về Việt Nam", "amount_vnd": sheet.intl_shipping_vnd},
            {
                "label": "Thuế, đóng gói, hao hụt",
                "amount_vnd": sheet.tax_vnd + sheet.packaging_vnd + sheet.loss_vnd + sheet.other_fees_vnd,
            },
        ]
        return {
            "source": "cost_sheet",
            "landed_cost_vnd": sheet.landed_cost_vnd,
            "lines": lines,
            "assumptions": [sheet.assumptions] if sheet.assumptions else [],
            "note": "Theo bảng giá vốn của Nguồn cung.",
        }
    est = estimate_landed(c.price_amount, c.price_currency, weight_grams=_weight(c, a), rates=await _rates(db))
    if est is None:
        return None
    return {
        "source": "estimate",
        "landed_cost_vnd": est.total_vnd,
        "lines": est.lines,
        "assumptions": est.assumptions,
        "note": "Ước tính sơ bộ — chưa có bảng giá vốn của Nguồn cung.",
    }


def market_summary(rows: list[MarketPrice], landed: int | None) -> dict[str, Any] | None:
    good = [r for r in rows if r.match_confidence is None or r.match_confidence >= Decimal(str(MIN_MATCH))]
    if not good:
        return None
    prices = sorted(r.price_vnd for r in good)
    low, high = prices[0], prices[-1]
    q1 = prices[len(prices) // 4] if len(prices) >= 4 else low
    suggested = max(round_vnd(q1 * 0.97, 1000) - 1000, 1000)
    return {
        "count": len(good),
        "low_vnd": low,
        "high_vnd": high,
        "median_vnd": int(statistics.median(prices)),
        "suggested_price_vnd": suggested,
        "margin_pct": margin_pct(suggested, landed) if landed else None,
        "captured_at": max(r.captured_at for r in good).isoformat(),
    }


def warnings_for(a: Assessment | None, c: Candidate, cost: dict[str, Any] | None) -> list[dict[str, str]]:
    """«Cần chị để ý»: an toàn (b6) + nhái/ảo (b7) + chỗ AI chưa chắc + cước."""
    out: list[dict[str, str]] = []
    if a is not None:
        for f in (a.safety or {}).get("findings") or []:
            if f.get("level") in ("warning", "danger"):
                out.append({"level": f["level"], "kind": "safety", "text": f["text"]})
        for n in a.risk_notes or []:
            out.append({"level": n.get("level", "info"), "kind": n.get("kind", "other"), "text": n.get("text", "")})
    w = _weight(c, a)
    if w and w >= 2000:
        out.append(
            {
                "level": "warning",
                "kind": "shipping",
                "text": f"Nặng {w / 1000:.1f} kg nên cước cao.".replace(".", ",", 1),
            }
        )
    if cost and cost.get("source") == "estimate":
        out.append({"level": "info", "kind": "cost", "text": "Giá vốn mới là ước tính sơ bộ, chưa có báo giá thật."})
    order = {"danger": 0, "warning": 1, "info": 2}
    return sorted(out, key=lambda x: order.get(x["level"], 3))


# ---- lượt thẩm định ----------------------------------------------------------------------------------------------


async def request_run(db: AsyncSession, candidate: Candidate, steps: list[str] | None) -> Assessment:
    steps = [s for s in (steps or STEPS) if s in STEPS] or list(STEPS)
    a = await assessment_of(db, candidate.id)
    if a is None:
        prof = await profile_for(db, candidate.category_id)
        a = Assessment(candidate_id=candidate.id, status=AssessmentStatus.PENDING, scoring_profile_id=prof.id)
        db.add(a)
        await db.flush()
    elif a.status == AssessmentStatus.RUNNING and a.updated_at > now_utc() - timedelta(minutes=10):
        return a
    else:
        if set(steps) >= {"reviews", "score"}:
            a.version += 1
        a.status = AssessmentStatus.PENDING
    a.price_overview = {**(a.price_overview or {}), "pending_steps": steps}
    flag_modified(a, "price_overview")
    return a


def _review_dicts(c: Candidate) -> list[dict[str, Any]]:
    r = (c.raw or {}).get("reviews")
    return r if isinstance(r, list) else []


async def _step_details(db: AsyncSession, a: Assessment, c: Candidate) -> list[SourceReview]:
    """Lấy chi tiết + đánh giá từ nguồn (driver). Thông số dịch lưu ở hồ sơ, không sửa bảng ứng viên."""
    reviews = [SourceReview.model_validate(r) for r in _review_dicts(c)]
    if not c.source_url:
        return reviews
    if not c.specs or not reviews:
        product = await sources().fetch_product(c.source_url)
        tr = await ai.run(
            "sourcing.translate_product",
            TranslateIn(
                platform=c.source_platform.value,
                language=product.language.value,
                title=product.title,
                description=product.description,
                specs=product.specs,
                variants=product.variants,
            ),
            TranslateOut,
        )
        # ứng viên đã có thông số tiếng Việt (dán link / chị đo khi thử) thì giữ; chỉ dùng bản dịch khi còn trống
        a.specs = dict(c.specs or {}) or {s.name: s.value for s in tr.output.specs_vi}
        po = dict(a.price_overview or {})
        po.update(
            {"weight_grams": product.weight_grams, "moq": product.moq, "description_vi": tr.output.description_vi}
        )
        a.price_overview = po
        flag_modified(a, "price_overview")
        reviews = reviews or list(product.reviews)
    else:
        a.specs = dict(c.specs)
    if len(reviews) < 30:
        try:
            more = await sources().fetch_reviews(c.source_url, limit=200)
            seen = {r.external_id for r in reviews}
            reviews += [r for r in more if r.external_id not in seen]
        except (IntegrationError, IntegrationNotConfigured):
            pass
    a.buyer_photos = [{"url": p, "review_id": r.external_id} for r in reviews for p in r.photos][:12]
    return reviews


async def _step_reviews(db: AsyncSession, a: Assessment, c: Candidate, reviews: list[SourceReview]) -> None:
    if not reviews:
        return
    sample = reviews[:MAX_REVIEWS_FOR_AI]
    res = await ai.run(
        "assessment.digest_reviews",
        DigestIn(
            product_title=c.title_vi,
            reviews=[
                ReviewIn(id=r.external_id, rating=r.rating, text=r.body, language=r.language.value) for r in sample
            ],
        ),
        DigestOut,
    )
    d = res.output
    hist = Counter(str(r.rating) for r in sample)
    ratings = [r.rating for r in sample]
    payload = {
        "candidate_id": str(c.id),
        "source_url": c.source_url,
        "platform": c.source_platform.value,
        "language": c.original_language.value,
        "digest": d.model_dump(mode="json"),
        "reviews": [r.model_dump(mode="json") for r in sample],
        "histogram": {k: hist.get(k, 0) for k in ("5", "4", "3", "2", "1")},
        "rating_avg": round(sum(ratings) / len(ratings), 2),
        "ai_run_id": str(res.run_id),
    }
    await control.propose(
        "assessment.digest_reviews",
        f"Đọc hộ {len(sample)} đánh giá: {c.title_vi}",
        payload,
        {"praise": [p.point for p in d.praise[:3]], "complaints": [p.point for p in d.complaints[:3]]},
        db=db,
        summary=d.low_star_summary,
        ref_type="candidates",
        ref_id=c.id,
        ai_run_id=res.run_id,
        dedupe_key=f"digest:{c.id}",
    )


def save_digest_row(db: AsyncSession, p: dict[str, Any], ai_run_id: uuid.UUID | None) -> ReviewDigest:
    d = DigestOut.model_validate(p["digest"])
    reviews = {r["external_id"]: r for r in p["reviews"]}
    vi = {t.id: t.vi for t in d.translations}

    def quotes(ids: list[str]) -> list[dict[str, Any]]:
        return [
            {"id": i, "original": reviews[i]["body"], "vi": vi.get(i), "rating": reviews[i]["rating"]}
            for i in ids
            if i in reviews
        ]

    low = [r for r in p["reviews"] if r["rating"] <= 2]
    row = ReviewDigest(
        candidate_id=uuid.UUID(p["candidate_id"]),
        source_url=p.get("source_url"),
        platform=SourcePlatform(p["platform"]) if p.get("platform") else None,
        language=Language(p["language"]) if p.get("language") else None,
        reviews_read=len(p["reviews"]),
        rating_avg=Decimal(str(p["rating_avg"])),
        rating_histogram=p["histogram"],
        praise=[{"point": x.point, "count": x.count, "quotes": quotes(x.review_ids)} for x in d.praise],
        complaints=[{"point": x.point, "count": x.count, "quotes": quotes(x.review_ids)} for x in d.complaints],
        low_star_summary=d.low_star_summary,
        low_star_reviews=[
            {
                "id": r["external_id"],
                "rating": r["rating"],
                "original": r["body"],
                "vi": vi.get(r["external_id"]),
                "created_on": r.get("created_on"),
            }
            for r in low
        ],
        suspicious_ratio=Decimal(str(round(d.suspicious_ratio, 3))),
        suspicious_notes=d.suspicious_notes,
        sample_photos=[ph for r in p["reviews"] for ph in r.get("photos", [])][:8],
        ai_run_id=ai_run_id,
    )
    db.add(row)
    return row


async def _step_market(db: AsyncSession, a: Assessment, c: Candidate) -> None:
    query = c.title_vi
    listings = await sources().market_prices(query, limit=10)
    if not listings:
        return
    refs = {f"l{i}": li for i, li in enumerate(listings)}
    res = await ai.run(
        "assessment.match_market",
        MatchIn(
            product_title=c.title_vi,
            specs={k: str(v) for k, v in (a.specs or c.specs or {}).items()},
            listings=[
                ListingIn(ref=r, title=li.title, shop=li.shop_name, price_vnd=li.price_vnd) for r, li in refs.items()
            ],
        ),
        MatchOut,
    )
    conf = {m.ref: m.confidence for m in res.output.matches}
    rows = [{**li.model_dump(mode="json"), "match_confidence": conf.get(r)} for r, li in refs.items()]
    await control.propose(
        "assessment.market_prices",
        f"Giá ở Việt Nam: {c.title_vi}",
        {"candidate_id": str(c.id), "listings": rows, "ai_run_id": str(res.run_id)},
        {"count": len(rows), "prices": sorted(li.price_vnd for li in listings)},
        db=db,
        sources=[{"url": li.url, "title": li.title} for li in listings],
        ref_type="candidates",
        ref_id=c.id,
        ai_run_id=res.run_id,
        dedupe_key=f"market:{c.id}",
    )


def save_market_rows(db: AsyncSession, p: dict[str, Any], ai_run_id: uuid.UUID | None) -> int:
    now = now_utc()
    for li in p["listings"]:
        db.add(
            MarketPrice(
                candidate_id=uuid.UUID(p["candidate_id"]),
                platform=SourcePlatform(li["platform"]),
                shop_name=li.get("shop_name"),
                title=li["title"],
                url=li["url"],
                price_vnd=int(li["price_vnd"]),
                original_price_vnd=li.get("original_price_vnd"),
                sold_count=li.get("sold_count"),
                rating=Decimal(str(li["rating"])) if li.get("rating") is not None else None,
                match_confidence=Decimal(str(li["match_confidence"]))
                if li.get("match_confidence") is not None
                else None,
                captured_at=now,
                ai_run_id=ai_run_id,
            )
        )
    return len(p["listings"])


async def _category_name(db: AsyncSession, category_id: uuid.UUID | None) -> str | None:
    if not category_id:
        return None
    from app.modules.catalog.models import Category  # chỉ đọc

    cat = await db.get(Category, category_id)
    return cat.name if cat else None


async def _step_safety(db: AsyncSession, a: Assessment, c: Candidate) -> None:
    res = await ai.run(
        "assessment.safety_check",
        SafetyIn(
            title=c.title_vi,
            description=c.description_vi or (a.price_overview or {}).get("description_vi"),
            specs={k: str(v) for k, v in (a.specs or c.specs or {}).items()},
            category=await _category_name(db, c.category_id),
            platform=c.source_platform.value,
        ),
        SafetyOut,
    )
    s = res.output
    await control.propose(
        "assessment.safety_check",
        f"Soát an toàn: {c.title_vi}",
        {"assessment_id": str(a.id), "safety": s.model_dump(mode="json")},
        {"status": s.status, "findings": [f.text for f in s.findings]},
        db=db,
        ref_type="assessments",
        ref_id=a.id,
        ai_run_id=res.run_id,
        dedupe_key=f"safety:{a.id}",
    )


def apply_safety(a: Assessment, s: dict[str, Any]) -> None:
    a.safety = s
    a.safety_status = SafetyStatus(s.get("status", "warning"))
    a.safety_confirmed_at = None
    a.safety_confirmed_by_id = None


async def risk_signals(
    db: AsyncSession, c: Candidate, digest: ReviewDigest | None, reviews: list[dict[str, Any]] | None = None
) -> list[dict[str, str]]:
    """b7 — luật tính: so giá/ảnh giữa các shop cùng mẫu, phân bố đánh giá bất thường."""
    notes: list[dict[str, str]] = []
    offers = [o for o in (c.raw or {}).get("offers", []) if o.get("price_vnd_estimate")]
    mine = next((o for o in offers if o.get("external_id") == c.source_external_id), None)
    if len(offers) >= 2 and mine:
        others = [o["price_vnd_estimate"] for o in offers if o is not mine]
        med = statistics.median(others)
        if med and mine["price_vnd_estimate"] < 0.6 * med:
            pct = round((1 - mine["price_vnd_estimate"] / med) * 100)
            notes.append(
                {
                    "kind": "counterfeit",
                    "level": "warning",
                    "text": f"Giá rẻ hơn {pct}% so với các shop cùng mẫu: dễ là hàng nhái hoặc hàng loại 2.",
                }
            )
        prices = [o["price_vnd_estimate"] for o in offers]
        if max(prices) > 2.5 * min(prices):
            notes.append(
                {
                    "kind": "price",
                    "level": "info",
                    "text": f"Giá cùng mẫu chênh nhiều giữa {len(offers)} shop ({min(prices) // 1000}k–{max(prices) // 1000}k).",
                }
            )
    if c.main_image_url:
        same_img = (
            (
                await db.execute(
                    select(Candidate.seller_name)
                    .where(Candidate.main_image_url == c.main_image_url, Candidate.id != c.id)
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )
        sellers = {s for s in same_img if s and s != c.seller_name}
        if sellers:
            notes.append(
                {
                    "kind": "counterfeit",
                    "level": "warning",
                    "text": f"Ảnh chính trùng với {len(sellers)} shop khác: có thể ảnh lấy lại, cần ảnh thật.",
                }
            )
    if c.review_count and c.sales_count is not None and c.review_count > max(c.sales_count, 1) * 1.2:
        notes.append(
            {
                "kind": "fake_review",
                "level": "danger",
                "text": f"Có {c.review_count} đánh giá nhưng chỉ {c.sales_count} lượt bán.",
            }
        )
    if digest is not None and digest.reviews_read >= 20:
        hist = digest.rating_histogram or {}
        five = int(hist.get("5", 0)) / max(digest.reviews_read, 1)
        if five > 0.92:
            notes.append(
                {
                    "kind": "fake_review",
                    "level": "warning",
                    "text": f"{round(five * 100)}% đánh giá 5 sao, cao bất thường.",
                }
            )
        if digest.suspicious_ratio is not None and digest.suspicious_ratio >= Decimal("0.2"):
            notes.append(
                {
                    "kind": "fake_review",
                    "level": "warning",
                    "text": digest.suspicious_notes or "Nhiều đánh giá có dấu hiệu ảo.",
                }
            )
    reviews = reviews if reviews is not None else _review_dicts(c)
    days = Counter(r.get("created_on") for r in reviews if r.get("created_on"))
    if len(reviews) >= 20 and days and days.most_common(1)[0][1] >= 0.4 * len(reviews):
        day, n = days.most_common(1)[0]
        notes.append({"kind": "fake_review", "level": "warning", "text": f"{n} đánh giá dồn vào cùng ngày {day}."})
    return notes  # fmt: skip


def risk_levels(notes: list[dict[str, str]]) -> tuple[RiskLevel, RiskLevel]:
    rank = {"info": RiskLevel.LOW, "warning": RiskLevel.MEDIUM, "danger": RiskLevel.HIGH}
    order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]

    def level(kind: str) -> RiskLevel:
        lv = [rank.get(n["level"], RiskLevel.LOW) for n in notes if n["kind"] == kind]
        return max(lv, key=order.index) if lv else RiskLevel.LOW

    return level("counterfeit"), level("fake_review")


async def _step_risk(db: AsyncSession, a: Assessment, c: Candidate, reviews: list[SourceReview]) -> None:
    notes = await risk_signals(
        db, c, await latest_digest(db, c.id), [r.model_dump(mode="json") for r in reviews] or None
    )
    cf, fr = risk_levels(notes)
    await control.propose(
        "assessment.risk_flags",
        f"Cảnh báo nhái/đánh giá ảo: {c.title_vi}",
        {"assessment_id": str(a.id), "notes": notes, "counterfeit": cf.value, "fake_review": fr.value},
        {"notes": [n["text"] for n in notes]},
        db=db,
        ref_type="assessments",
        ref_id=a.id,
        dedupe_key=f"risk:{a.id}",
        ai_generated=False,
    )


def apply_risk(a: Assessment, p: dict[str, Any]) -> None:
    keep = [n for n in a.risk_notes or [] if n.get("kind") == "uncertain"]
    a.risk_notes = [*p["notes"], *keep]
    a.counterfeit_risk = RiskLevel(p["counterfeit"])
    a.fake_review_risk = RiskLevel(p["fake_review"])


async def _step_score(db: AsyncSession, a: Assessment, c: Candidate) -> None:
    prof = await db.get(ScoringProfile, a.scoring_profile_id) if a.scoring_profile_id else None
    prof = prof or await profile_for(db, c.category_id)
    a.scoring_profile_id = prof.id
    digest = await latest_digest(db, c.id)
    cost = await cost_view(db, c, a)
    market = market_summary(await latest_market(db, c.id), cost["landed_cost_vnd"] if cost else None)
    brief = await db.get(SourcingBrief, c.brief_id) if c.brief_id else None
    res = await ai.run(
        "assessment.evaluate",
        EvaluateIn(
            product={
                "title": c.title_vi,
                "platform": c.source_platform.value,
                "price": f"{c.price_amount} {c.price_currency}",
                "rating": float(c.rating) if c.rating is not None else None,
                "review_count": c.review_count,
                "sales_count": c.sales_count,
                "seller": c.seller_name,
                "specs": a.specs or c.specs,
                "weight_grams": _weight(c, a),
                "offers_count": max(1, len((c.raw or {}).get("offers", []))),
                "description": c.description_vi or (a.price_overview or {}).get("description_vi"),
            },
            brief={"title": brief.title, **(brief.filters or {})} if brief else {},
            criteria=[
                CriterionIn(**{k: x.get(k) for k in ("key", "label", "weight", "description")}) for x in prof.criteria
            ],
            reviews=(
                {
                    "reviews_read": digest.reviews_read,
                    "rating_avg": float(digest.rating_avg) if digest.rating_avg is not None else None,
                    "praise": [{"point": x["point"], "count": x["count"]} for x in digest.praise],
                    "complaints": [{"point": x["point"], "count": x["count"]} for x in digest.complaints],
                    "low_star_summary": digest.low_star_summary,
                }
                if digest
                else {}
            ),
            market=market or {},
            cost=cost or {},
            safety=a.safety or {},
            risks=[n for n in a.risk_notes or [] if n.get("kind") != "uncertain"],
        ),
        EvaluateOut,
    )
    ev = res.output
    await control.propose(
        "assessment.write_profile",
        f"Hồ sơ thẩm định + chấm nháp: {c.title_vi}",
        {
            "assessment_id": str(a.id),
            "evaluation": ev.model_dump(mode="json"),
            "market": market,
            "ai_run_id": str(res.run_id),
        },
        {"summary": ev.summary, "scores": {s.key: s.score for s in ev.scores}},
        db=db,
        summary=ev.summary,
        ref_type="assessments",
        ref_id=a.id,
        ai_run_id=res.run_id,
        dedupe_key=f"profile:{a.id}",
    )


async def apply_evaluation(db: AsyncSession, a: Assessment, p: dict[str, Any], ai_run_id: uuid.UUID | None) -> None:
    ev = EvaluateOut.model_validate(p["evaluation"])
    prof = (
        await db.get(ScoringProfile, a.scoring_profile_id) if a.scoring_profile_id else await ensure_default_profile(db)
    )
    by_key = {s.key: s for s in ev.scores}
    existing = {s.criterion_key: s for s in a.scores}
    keys = []
    for i, crit in enumerate(prof.criteria):
        key = crit["key"]
        keys.append(key)
        item = by_key.get(key)
        row = existing.get(key)
        if row is None:
            row = AssessmentScore(criterion_key=key, criterion_label=crit["label"], weight=Decimal(str(crit["weight"])))
            a.scores.append(row)
        row.criterion_label = crit["label"]
        row.weight = Decimal(str(crit["weight"]))
        row.position = i
        row.ai_score = Decimal(str(item.score)).quantize(Decimal("0.1")) if item else None
        row.ai_reason = item.reason if item else "AI chưa chấm tiêu chí này."
    for key, row in existing.items():
        if key not in keys:
            a.scores.remove(row)
    recompute_total(a)
    a.summary = ev.summary
    a.strengths = ev.strengths
    a.weaknesses = ev.weaknesses
    a.risk_notes = [n for n in a.risk_notes or [] if n.get("kind") != "uncertain"] + [
        {"kind": "uncertain", "level": "info", "text": t} for t in ev.uncertainties
    ]
    po = dict(a.price_overview or {})
    if p.get("market"):
        po["market"] = p["market"]
    a.price_overview = po
    a.score_status = ScoreStatus.AI_DRAFT
    a.score_confirmed_at = None
    a.score_confirmed_by_id = None
    a.generated_at = now_utc()
    a.ai_run_id = ai_run_id
    a.ai_generated = True


async def execute(db: AsyncSession, candidate_id: uuid.UUID) -> Assessment:
    """Job `assessment.run`: chạy các bước đang chờ, bước lỗi ghi vào `error`, không chặn bước sau."""
    c = await get_candidate(db, candidate_id)
    a = await assessment_of(db, candidate_id)
    if a is None:
        a = await request_run(db, c, None)
    steps = list((a.price_overview or {}).get("pending_steps") or STEPS)
    aid = a.id
    a.status = AssessmentStatus.RUNNING
    a.error = None
    await db.commit()
    errors: list[str] = []
    reviews: list[SourceReview] = []
    labels = {"details": "lấy chi tiết", "reviews": "đọc đánh giá", "market": "giá ở Việt Nam", "safety": "an toàn",
              "risk": "cảnh báo", "score": "chấm điểm"}  # fmt: skip
    if "reviews" in steps and "details" not in steps:
        steps.insert(0, "details")
    for step in STEPS:
        if step not in steps:
            continue
        try:
            async with db.begin_nested():
                if step == "details":
                    reviews = await _step_details(db, a, c)
                elif step == "reviews":
                    await _step_reviews(db, a, c, reviews)
                elif step == "market":
                    await _step_market(db, a, c)
                elif step == "safety":
                    await _step_safety(db, a, c)
                elif step == "risk":
                    await _step_risk(db, a, c, reviews)
                elif step == "score":
                    await _step_score(db, a, c)
            await db.commit()
        except ai.AIBudgetExceeded as e:
            await db.rollback()
            errors.append(e.message)
            break
        except (ai.AIError, IntegrationError, IntegrationNotConfigured) as e:
            await db.rollback()
            errors.append(f"{labels[step]}: {e.message}")
        a = await db.get(Assessment, aid, populate_existing=True)
        c = await db.get(Candidate, candidate_id, populate_existing=True)
        assert a is not None and c is not None
    po = dict(a.price_overview or {})
    po.pop("pending_steps", None)
    a.price_overview = po
    a.status = AssessmentStatus.FAILED if errors and not a.summary else AssessmentStatus.READY
    a.error = "; ".join(errors) or None
    await db.flush()
    if a.score_total is not None and "score" in steps:
        await events.emit("candidate.assessed", {"candidate_id": str(c.id), "assessment_id": str(a.id)}, db=db)
    await db.commit()
    return a


# ---- chị sửa điểm, duyệt an toàn ---------------------------------------------------------------------------------


async def set_owner_score(
    db: AsyncSession, a: Assessment, key: str, score: Decimal | None, note: str | None
) -> Assessment:
    row = next((s for s in a.scores if s.criterion_key == key), None)
    if row is None:
        raise NotFound("Hồ sơ này không có tiêu chí đó.")
    row.owner_score = score
    row.owner_note = note
    recompute_total(a)
    if a.score_status == ScoreStatus.CONFIRMED:
        a.score_status = ScoreStatus.AI_DRAFT
    return a


async def confirm_score(db: AsyncSession, a: Assessment, user_id: uuid.UUID) -> Assessment:
    if not a.scores:
        raise BadRequest("Hồ sơ chưa có điểm để duyệt.")
    recompute_total(a)
    a.score_status = ScoreStatus.CONFIRMED
    a.score_confirmed_at = now_utc()
    a.score_confirmed_by_id = user_id
    await db.flush()
    await events.emit("candidate.assessed", {"candidate_id": str(a.candidate_id), "assessment_id": str(a.id)}, db=db)
    return a


def confirm_safety(a: Assessment, status: SafetyStatus | None, note: str | None, user_id: uuid.UUID) -> Assessment:
    if a.safety_status == SafetyStatus.UNCHECKED and status is None:
        raise BadRequest("AI chưa soát an toàn cho món này.")
    if status is not None:
        a.safety_status = status
    if note:
        a.safety = {**(a.safety or {}), "owner_note": note}
    a.safety_confirmed_at = now_utc()
    a.safety_confirmed_by_id = user_id
    return a


# ---- b3: so sánh -------------------------------------------------------------------------------------------------


def _fmt_k(v: int | None) -> str:
    return f"{round(v / 1000)}k" if v else "—"


async def comparison_values(db: AsyncSession, cands: list[Candidate]) -> tuple[list[dict[str, str]], dict[uuid.UUID, dict[str, Any]], dict[uuid.UUID, int | None]]:  # fmt: skip
    prof = await profile_for(db, cands[0].category_id)
    criteria = [{"key": "score_total", "label": "Điểm tổng"}]
    criteria += [{"key": c["key"], "label": f"{c['label']} ({c['weight']})"} for c in prof.criteria]
    criteria += [
        {"key": "landed", "label": "Giá vốn về tay"},
        {"key": "vn_price", "label": "Giá ở Việt Nam"},
        {"key": "margin", "label": "Biên dự kiến"},
        {"key": "rating", "label": "Đánh giá"},
        {"key": "weight", "label": "Cân nặng"},
        {"key": "safety", "label": "An toàn"},
        {"key": "risk", "label": "Rủi ro nhái/ảo"},
    ]
    values: dict[uuid.UUID, dict[str, Any]] = {}
    landed_of: dict[uuid.UUID, int | None] = {}
    for c in cands:
        a = await assessment_of(db, c.id)
        cost = await cost_view(db, c, a)
        landed = cost["landed_cost_vnd"] if cost else None
        landed_of[c.id] = landed
        mk = market_summary(await latest_market(db, c.id), landed)
        v: dict[str, Any] = {}
        total = a.score_total if a else None
        v["score_total"] = {"value": f"{float(total):.0f}/100" if total is not None else "chưa chấm",
                            "raw": float(total) if total is not None else None}  # fmt: skip
        scores = {s.criterion_key: s for s in (a.scores if a else [])}
        for crit in prof.criteria:
            s = scores.get(crit["key"])
            e = effective(s) if s else None
            pts = float(e) * float(crit["weight"]) / 10 if e is not None else None
            v[crit["key"]] = {"value": f"{pts:.0f}/{crit['weight']}" if pts is not None else "—", "raw": pts,
                              "note": (s.owner_note or s.ai_reason) if s else None}  # fmt: skip
        v["landed"] = {
            "value": _fmt_k(landed) + (" (ước tính)" if cost and cost["source"] == "estimate" else ""),
            "raw": landed,
        }
        v["vn_price"] = {
            "value": f"{_fmt_k(mk['low_vnd'])}–{_fmt_k(mk['high_vnd'])}" if mk else "—",
            "raw": mk["median_vnd"] if mk else None,
        }
        v["margin"] = {"value": f"{mk['margin_pct']:.0f}%" if mk and mk.get("margin_pct") is not None else "—",
                       "raw": mk.get("margin_pct") if mk else None}  # fmt: skip
        v["rating"] = {"value": f"{float(c.rating):.1f}★ · {c.review_count or 0}".replace(".", ",", 1) if c.rating else "—",
                       "raw": float(c.rating) if c.rating else None}  # fmt: skip
        w = _weight(c, a)
        v["weight"] = {"value": f"{w / 1000:.1f} kg".replace(".", ",") if w else "—", "raw": w}
        safety_label = {"ok": "Ổn", "warning": "Cần lưu ý", "blocked": "Chưa bán được", "unchecked": "Chưa soát"}
        v["safety"] = {"value": safety_label[(a.safety_status if a else SafetyStatus.UNCHECKED).value], "raw": None}
        risk_label = {"unknown": "Chưa xét", "low": "Thấp", "medium": "Vừa", "high": "Cao"}
        worst = max(
            [a.counterfeit_risk, a.fake_review_risk] if a else [RiskLevel.UNKNOWN],
            key=[RiskLevel.UNKNOWN, RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH].index,
        )
        v["risk"] = {"value": risk_label[worst.value], "raw": None}
        values[c.id] = v
    higher_better = {"score_total", "margin", "rating", *[c["key"] for c in prof.criteria]}
    lower_better = {"landed", "weight"}
    for crit in criteria:
        k = crit["key"]
        raws = [(cid, v[k]["raw"]) for cid, v in values.items() if v[k].get("raw") is not None]
        if len(raws) < 2 or k not in higher_better | lower_better:
            continue
        best = max(r for _, r in raws) if k in higher_better else min(r for _, r in raws)
        for cid, r in raws:
            values[cid][k]["best"] = r == best
    return criteria, values, landed_of


async def create_comparison(db: AsyncSession, candidate_ids: list[uuid.UUID], title: str | None) -> Comparison:
    ids = list(dict.fromkeys(candidate_ids))
    if not 2 <= len(ids) <= 5:
        raise BadRequest("Chọn từ 2 đến 5 ứng viên để so sánh.")
    cands = []
    for cid in ids:
        cands.append(await get_candidate(db, cid))
    briefs = {c.brief_id for c in cands}
    if len(briefs) != 1 or None in briefs:
        raise BadRequest("Chỉ so sánh các ứng viên cùng một đề tìm.")
    brief = await db.get(SourcingBrief, cands[0].brief_id)
    criteria, values, landed = await comparison_values(db, cands)
    res = await ai.run(
        "assessment.compare",
        CompareIn(
            criteria=criteria,
            candidates=[
                CompareCandidate(
                    id=str(c.id), title=c.title_vi, values={k: str(v["value"]) for k, v in values[c.id].items()}
                )
                for c in cands
            ],
        ),
        CompareOut,
    )
    out = res.output
    notes = {(n.candidate_id, n.key): n.note for n in out.notes}
    payload = {
        "title": title or f"So sánh {len(cands)} món: {brief.title if brief else ''}".strip(),
        "brief_id": str(brief.id) if brief else None,
        "criteria": criteria,
        "conclusion": out.conclusion,
        "recommended_id": out.recommended_id if out.recommended_id in {str(i) for i in ids} else None,
        "ai_run_id": str(res.run_id),
        "items": [
            {
                "candidate_id": str(c.id),
                "values": {k: {**v, **({"note": notes[(str(c.id), k)]} if (str(c.id), k) in notes else {})}
                           for k, v in values[c.id].items()},
                "landed_cost_vnd": landed[c.id],
            }
            for c in cands
        ],
    }  # fmt: skip
    outcome = await control.propose(
        "assessment.compare",
        payload["title"],
        payload,
        {"conclusion": out.conclusion},
        db=db,
        summary=out.conclusion,
        ref_type="sourcing_briefs",
        ref_id=brief.id if brief else None,
        ai_run_id=res.run_id,
    )
    if outcome.status != "applied":
        raise BadRequest(
            "Việc so sánh đang chờ chị duyệt ở Chờ duyệt."
            if outcome.status == "pending"
            else "Việc so sánh đang tắt trong Mức tự chủ."
            if outcome.status == "blocked"
            else f"So sánh bị lỗi: {outcome.error}",
            code=f"comparison_{outcome.status}",
        )
    comp = await db.get(Comparison, uuid.UUID(outcome.result["comparison_id"]))
    assert comp is not None
    return comp


def save_comparison(db: AsyncSession, p: dict[str, Any], ai_run_id: uuid.UUID | None) -> Comparison:
    comp = Comparison(
        title=p["title"][:200],
        brief_id=uuid.UUID(p["brief_id"]) if p.get("brief_id") else None,
        criteria=p["criteria"],
        conclusion=p.get("conclusion"),
        recommended_candidate_id=uuid.UUID(p["recommended_id"]) if p.get("recommended_id") else None,
        ai_run_id=ai_run_id,
    )
    for i, it in enumerate(p["items"]):
        comp.items.append(
            ComparisonItem(
                candidate_id=uuid.UUID(it["candidate_id"]),
                position=i,
                values=it["values"],
                landed_cost_vnd=it.get("landed_cost_vnd"),
            )
        )
    db.add(comp)
    return comp


async def ensure_seeded_profile(db: AsyncSession) -> ScoringProfile:
    """Khung mặc định theo bản thiết kế; nếu nền móng đã tạo bộ tiêu chí cũ (chưa ai sửa) thì đổi sang bộ mới."""
    prof = await ensure_default_profile(db)
    keys = {c.get("key") for c in prof.criteria or []}
    if keys == LEGACY_KEYS:
        prof.criteria = list(DEFAULT_CRITERIA)
        prof.pass_score = DEFAULT_PASS_SCORE
    return prof
