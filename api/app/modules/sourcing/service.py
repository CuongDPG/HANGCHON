"""Nghiệp vụ săn hàng (a1–a7).

Mọi việc AI làm đi theo một mẫu: gọi model qua `ai.run(...)` → đưa kết quả qua `control.propose(...)` với action đã
khai báo trong `actions.py`; handler của action mới ghi CSDL. Mức tự chủ mặc định của các action nội bộ là `auto`, nên
thường được ghi ngay; chị đặt `ask` thì kết quả nằm ở hàng chờ duyệt.

Các lượt chạy dài (quét đề, lấy link, tìm ảnh, radar) là job nền: route tạo `sourcing_runs` (queued), commit, rồi
`enqueue`. Job chạy `execute_*` trong phiên riêng và commit tiến độ sau từng bước (`input.progress`) để web hỏi lại."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app import ai, control
from app.core import events
from app.core.config import settings
from app.core.enums import Channel, Language, SourcePlatform
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.money import format_vnd
from app.core.timeutil import local_today, now_utc
from app.integrations import IntegrationError, IntegrationNotConfigured, get_driver
from app.integrations.sources import SourceItem, SourceProduct, SourceQuery, SourcesDriver
from app.modules.sourcing import guidance, imagehash, vocab
from app.modules.sourcing.ai_io import (
    BriefParse,
    DescribeImageIn,
    DescribeImageOut,
    ExistingDemand,
    ExtractDemandIn,
    ExtractDemandOut,
    ParseBriefIn,
    RankBrief,
    RankIn,
    RankItemIn,
    RankItemOut,
    RankOut,
    TranslateIn,
    TranslateOut,
    TrendIn,
    TrendItemIn,
    TrendOut,
)
from app.modules.sourcing.estimate import (
    DEFAULT_FX,
    FX_SETTING_KEY,
    landed_total,
    source_price_ceiling,
    to_vnd_estimate,
)
from app.modules.sourcing.models import (
    BriefInputMode,
    BriefStatus,
    Candidate,
    CandidateOrigin,
    CandidateStage,
    DemandMention,
    DemandSignal,
    DemandSource,
    DemandStatus,
    RunKind,
    RunStatus,
    SourcingBrief,
    SourcingRun,
    TrendSignal,
    TrendStatus,
)

log = logging.getLogger("app.sourcing")

DEFAULT_ALERT_SCORE = 75
DEFAULT_INTERVAL_DAYS = 7
PER_PLATFORM_LIMIT = 8
RANK_BATCH = 30

# nền tảng → (tên hiển thị, tiền tệ, ngôn ngữ từ khoá)
PLATFORMS: dict[SourcePlatform, tuple[str, str, str]] = {
    SourcePlatform.ALIBABA_1688: ("1688", "CNY", "zh"),
    SourcePlatform.TAOBAO: ("Taobao", "CNY", "zh"),
    SourcePlatform.TMALL: ("Tmall", "CNY", "zh"),
    SourcePlatform.PINDUODUO: ("Pinduoduo", "CNY", "zh"),
    SourcePlatform.ALIBABA: ("Alibaba.com", "USD", "en"),
    SourcePlatform.RAKUTEN: ("Rakuten", "JPY", "ja"),
    SourcePlatform.AMAZON_JP: ("Amazon Nhật", "JPY", "ja"),
    SourcePlatform.AMAZON: ("Amazon", "USD", "en"),
    SourcePlatform.XIAOHONGSHU: ("Tiểu Hồng Thư", "CNY", "zh"),
    SourcePlatform.COSME: ("@cosme", "JPY", "ja"),
    SourcePlatform.TIKTOK_SHOP_VN: ("TikTok Shop", "VND", "vi"),
    SourcePlatform.SHOPEE_VN: ("Shopee", "VND", "vi"),
    SourcePlatform.LAZADA_VN: ("Lazada", "VND", "vi"),
    SourcePlatform.TIKI: ("Tiki", "VND", "vi"),
    SourcePlatform.WEB: ("Trang web", "USD", "en"),
}
ORIGIN_PLATFORMS: dict[str, list[SourcePlatform]] = {
    "cn": [SourcePlatform.ALIBABA_1688, SourcePlatform.TAOBAO],
    "jp": [SourcePlatform.RAKUTEN, SourcePlatform.AMAZON_JP],
}
DEFAULT_PLATFORMS = [*ORIGIN_PLATFORMS["cn"], *ORIGIN_PLATFORMS["jp"]]
_ORIGIN_OF_LANG = {Language.ZH: "cn", Language.JA: "jp"}


def platform_label(p: SourcePlatform | str) -> str:
    try:
        return PLATFORMS[SourcePlatform(p)][0]
    except (KeyError, ValueError):
        return str(p)


def sources() -> SourcesDriver:
    from app.integrations.sources._profiled import wrap

    return wrap(get_driver("sources"))  # link chuẩn + ảnh cỡ lớn theo hồ sơ nguồn (Cài đặt → Nguồn hàng)


async def fx_rates(db: AsyncSession) -> dict[str, Any]:
    value = await control.get_setting(db, FX_SETTING_KEY, None)
    return value if isinstance(value, dict) else dict(DEFAULT_FX)


def normalize_key(title: str) -> str:
    return slugify(vocab.plain(title), max_length=200) or "khong-ro"


# ---- đọc ---------------------------------------------------------------------------------------------------------


async def get_brief(db: AsyncSession, brief_id: uuid.UUID) -> SourcingBrief:
    brief = await db.get(SourcingBrief, brief_id)
    if brief is None:
        raise NotFound("Không tìm thấy đề tìm này.")
    return brief


async def get_run(db: AsyncSession, run_id: uuid.UUID) -> SourcingRun:
    run = await db.get(SourcingRun, run_id)
    if run is None:
        raise NotFound("Không tìm thấy lượt tìm này.")
    return run


async def get_candidate(db: AsyncSession, candidate_id: uuid.UUID) -> Candidate:
    c = await db.get(Candidate, candidate_id)
    if c is None:
        raise NotFound("Không tìm thấy ứng viên này.")
    return c


async def _categories(db: AsyncSession) -> dict[str, uuid.UUID]:
    from app.modules.catalog.models import Category  # chỉ đọc

    rows = (await db.execute(select(Category.name, Category.id))).all()
    return {name: cid for name, cid in rows}


def run_progress(run: SourcingRun) -> dict[str, Any]:
    p = (run.input or {}).get("progress")
    return p if isinstance(p, dict) else {}


async def _set_progress(db: AsyncSession, run: SourcingRun, **fields: Any) -> None:
    data = dict(run.input or {})
    data["progress"] = {**run_progress(run), **fields}
    run.input = data
    flag_modified(run, "input")
    await db.commit()


# ---- a1: ra đề bằng lời ------------------------------------------------------------------------------------------


def _platforms_for(origins: list[str]) -> list[str]:
    out: list[SourcePlatform] = []
    for o in origins:
        out += [p for p in ORIGIN_PLATFORMS.get(o, []) if p not in out]
    return [p.value for p in (out or DEFAULT_PLATFORMS)]


def apply_parse(brief: SourcingBrief, parse: BriefParse, categories: dict[str, uuid.UUID]) -> None:
    """Ghi cách AI hiểu đề vào đề (dùng trong handler `sourcing.interpret_brief`)."""
    brief.title = parse.title[:200] or brief.title
    brief.interpretation = parse.interpretation
    keep = {k: v for k, v in (brief.filters or {}).items() if k == "trend_signal_id"}
    brief.filters = {
        **keep,
        "product_type": parse.product_type,
        "category": parse.category,
        "materials": parse.materials,
        "must": parse.must,
        "must_not": parse.must_not,
        "prefer": parse.prefer,
        "origins": list(parse.origins),
        "min_rating": parse.min_rating,
        "min_reviews": parse.min_reviews,
        "unclear": parse.unclear,
    }
    brief.keywords_vi = parse.keywords_vi or [parse.product_type]
    brief.keywords_translated = {"zh": parse.keywords_zh, "ja": parse.keywords_ja, "en": parse.keywords_en}
    brief.platforms = _platforms_for(list(parse.origins))
    brief.target_landed_cost_max_vnd = parse.landed_cost_max_vnd
    brief.price_max_vnd = parse.price_max_vnd
    brief.category_id = categories.get(parse.category or "") or brief.category_id


async def interpret(db: AsyncSession, brief: SourcingBrief, text: str) -> control.ProposeOutcome:
    cats = await _categories(db)
    res = await ai.run(
        "sourcing.parse_brief",
        ParseBriefIn(text=text, categories=list(cats), today=local_today().isoformat()),
        BriefParse,
    )
    parse = res.output
    return await control.propose(
        "sourcing.interpret_brief",
        f"Hiểu đề: {parse.title}",
        {"brief_id": str(brief.id), "parse": parse.model_dump(mode="json"), "ai_run_id": str(res.run_id)},
        {"interpretation": parse.interpretation, "title": parse.title},
        db=db,
        summary=parse.interpretation,
        ref_type="sourcing_briefs",
        ref_id=brief.id,
        ai_run_id=res.run_id,
        dedupe_key=f"brief:{brief.id}",
    )


async def create_brief(
    db: AsyncSession,
    text: str,
    *,
    input_mode: BriefInputMode = BriefInputMode.TEXT,
    user_id: uuid.UUID | None = None,
    demand_signal_id: uuid.UUID | None = None,
    find_request_id: uuid.UUID | None = None,
    filters: dict[str, Any] | None = None,
) -> SourcingBrief:
    text = text.strip()
    brief = SourcingBrief(
        title=(text[:60] + "…") if len(text) > 60 else text,
        raw_text=text,
        input_mode=input_mode,
        status=BriefStatus.DRAFT,
        created_by_id=user_id,
        demand_signal_id=demand_signal_id,
        find_request_id=find_request_id,
        filters=filters or {},
    )
    db.add(brief)
    await db.flush()
    await interpret(db, brief, text)
    await events.emit(
        "brief.created",
        {
            "brief_id": str(brief.id),
            "find_request_id": str(find_request_id) if find_request_id else None,
            "demand_signal_id": str(demand_signal_id) if demand_signal_id else None,
        },
        db=db,
    )
    return brief


async def reinterpret(db: AsyncSession, brief: SourcingBrief, text: str) -> SourcingBrief:
    brief.raw_text = text.strip()
    if brief.status != BriefStatus.DRAFT:
        brief.status = BriefStatus.DRAFT
    await interpret(db, brief, brief.raw_text)
    return brief


def apply_patch(brief: SourcingBrief, patch: Any) -> None:
    data = patch.model_dump(exclude_unset=True)
    if "title" in data:
        brief.title = data["title"]
    if patch.filters is not None:
        brief.filters = {**(brief.filters or {}), **patch.filters.model_dump(exclude_unset=True)}
        if "origins" in patch.filters.model_fields_set and patch.platforms is None:
            brief.platforms = _platforms_for(list(patch.filters.origins))
    if patch.keywords_vi is not None:
        brief.keywords_vi = [k.strip() for k in patch.keywords_vi if k.strip()]
    if patch.keywords_translated is not None:
        brief.keywords_translated = {**(brief.keywords_translated or {}), **patch.keywords_translated}
    if patch.platforms is not None:
        brief.platforms = [p.value for p in patch.platforms]
    if "target_landed_cost_max_vnd" in data:
        brief.target_landed_cost_max_vnd = data["target_landed_cost_max_vnd"]
    if patch.clear_landed_cost:
        brief.target_landed_cost_max_vnd = None
    if "price_max_vnd" in data:
        brief.price_max_vnd = data["price_max_vnd"]
    if "alert_min_score" in data:
        brief.alert_min_score = data["alert_min_score"]
    if "schedule_interval_days" in data:
        brief.schedule_interval_days = data["schedule_interval_days"]
    if patch.is_scheduled is not None:
        brief.is_scheduled = patch.is_scheduled
        if patch.is_scheduled:
            brief.schedule_interval_days = brief.schedule_interval_days or DEFAULT_INTERVAL_DAYS
            brief.alert_min_score = brief.alert_min_score or DEFAULT_ALERT_SCORE
            brief.next_run_at = brief.next_run_at or now_utc() + timedelta(days=brief.schedule_interval_days)
            if brief.status == BriefStatus.DRAFT:
                raise BadRequest("Chị xác nhận cách hiểu đề và chạy một lần trước khi lưu lịch.")
        else:
            brief.next_run_at = None
    if patch.status is not None:
        if patch.status == BriefStatus.DRAFT:
            raise BadRequest("Không đưa đề về nháp được.")
        if brief.status == BriefStatus.DRAFT and patch.status == BriefStatus.ACTIVE:
            raise BadRequest("Bấm «Tìm» để xác nhận đề.")
        brief.status = patch.status
        if patch.status != BriefStatus.ACTIVE:
            brief.next_run_at = None if patch.status in (BriefStatus.DONE, BriefStatus.ARCHIVED) else brief.next_run_at


# ---- a4 / a7: quét nhiều nguồn -----------------------------------------------------------------------------------


async def start_run(
    db: AsyncSession, kind: RunKind, *, brief: SourcingBrief | None = None, input: dict[str, Any] | None = None
) -> SourcingRun:
    run = SourcingRun(
        brief_id=brief.id if brief else None,
        kind=kind,
        status=RunStatus.QUEUED,
        platforms=list(brief.platforms) if brief else [],
        input={**(input or {}), "progress": {"step": "queued", "done": 0, "total": 0, "note": "Đang xếp hàng"}},
    )
    db.add(run)
    await db.flush()
    return run


async def start_scan(db: AsyncSession, brief: SourcingBrief, kind: RunKind = RunKind.BRIEF_SCAN) -> SourcingRun:
    if brief.status in (BriefStatus.ARCHIVED, BriefStatus.DONE):
        raise BadRequest("Đề này đã đóng. Chị mở lại đề trước khi tìm.")
    if brief.status == BriefStatus.PAUSED and kind == RunKind.SCHEDULED_SCAN:
        raise BadRequest("Đề đang tạm dừng.")
    if not (brief.keywords_vi or any((brief.keywords_translated or {}).values())):
        raise BadRequest("Đề chưa có từ khoá. Chị sửa đề hoặc nói lại tiêu chí.")
    running = (
        await db.execute(
            select(SourcingRun).where(
                SourcingRun.brief_id == brief.id,
                SourcingRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
                SourcingRun.created_at > now_utc() - timedelta(minutes=30),
            )
        )
    ).scalar_one_or_none()
    if running is not None:
        return running
    if brief.status in (BriefStatus.DRAFT, BriefStatus.PAUSED):
        brief.status = BriefStatus.ACTIVE
        brief.confirmed_at = brief.confirmed_at or now_utc()
    if not brief.platforms:
        brief.platforms = [p.value for p in DEFAULT_PLATFORMS]
    return await start_run(db, kind, brief=brief)


def _keywords_for(brief: SourcingBrief, platform: SourcePlatform) -> list[str]:
    lang = PLATFORMS.get(platform, ("", "USD", "en"))[2]
    kw = list((brief.keywords_translated or {}).get(lang) or [])
    if not kw:
        kw = list((brief.keywords_translated or {}).get("en") or []) or list(brief.keywords_vi or [])
    return kw[:5]


def _rank_brief(brief: SourcingBrief) -> RankBrief:
    f = brief.filters or {}
    return RankBrief(
        title=brief.title,
        product_type=f.get("product_type") or brief.title,
        materials=f.get("materials") or [],
        must=f.get("must") or [],
        must_not=f.get("must_not") or [],
        prefer=f.get("prefer") or [],
        landed_cost_max_vnd=brief.target_landed_cost_max_vnd,
        price_max_vnd=brief.price_max_vnd,
        min_rating=f.get("min_rating"),
        min_reviews=f.get("min_reviews"),
    )


async def _rank(
    brief: RankBrief, items: list[SourceItem], rates: dict[str, Any]
) -> tuple[dict[str, RankItemOut], uuid.UUID | None, list[dict[str, str]]]:
    ranked: dict[str, RankItemOut] = {}
    run_id: uuid.UUID | None = None
    srcs: list[dict[str, str]] = []
    for start in range(0, len(items), RANK_BATCH):
        batch = items[start : start + RANK_BATCH]
        res = await ai.run(
            "sourcing.rank_candidates",
            RankIn(
                brief=brief,
                items=[
                    RankItemIn(
                        ref=_ref(i),
                        platform=platform_label(i.platform),
                        title=i.title,
                        price=f"{i.price_amount} {i.currency}",
                        landed_estimate_vnd=landed_total(i.price_amount, i.currency, rates=rates),
                        rating=i.rating,
                        review_count=i.review_count,
                        sales_count=i.sales_count,
                        seller_name=i.seller_name,
                    )
                    for i in batch
                ],
            ),
            RankOut,
        )
        run_id = run_id or res.run_id
        srcs += res.sources
        ranked.update({r.ref: r for r in res.output.items})
    return ranked, run_id, srcs


def _ref(item: SourceItem) -> str:
    return f"{item.platform.value}:{item.external_id}"


def _offer(item: SourceItem, rates: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": item.platform.value,
        "url": item.url,
        "external_id": item.external_id,
        "seller_name": item.seller_name,
        "price_amount": str(item.price_amount),
        "currency": item.currency,
        "price_vnd_estimate": to_vnd_estimate(item.price_amount, item.currency, rates),
        "rating": item.rating,
        "review_count": item.review_count,
        "image_url": item.image_url,
    }


def _candidate_fields(
    item: SourceItem | SourceProduct,
    *,
    brief: SourcingBrief | None,
    origin: CandidateOrigin,
    title_vi: str,
    rates: dict[str, Any],
    score: int | None = None,
    reason: str | None = None,
    group: str | None = None,
    offers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    images = [item.image_url] if item.image_url else []
    fields: dict[str, Any] = {
        "brief_id": str(brief.id) if brief else None,
        "category_id": str(brief.category_id) if brief and brief.category_id else None,
        "origin": origin.value,
        "source_platform": item.platform.value,
        "source_url": item.url,
        "source_external_id": item.external_id,
        "seller_name": item.seller_name,
        "seller_url": item.seller_url,
        "original_language": item.language.value,
        "title_original": item.title,
        "title_vi": title_vi[:300],
        "images": images,
        "main_image_url": item.image_url,
        "price_amount": str(item.price_amount),
        "price_currency": item.currency,
        "price_vnd_estimate": to_vnd_estimate(item.price_amount, item.currency, rates),
        "rating": item.rating,
        "review_count": item.review_count,
        "sales_count": item.sales_count,
        "ai_score": score,
        "rank_reason": reason,
        "same_model_group": group,
        "raw": {"offers": offers or [], "source": item.model_dump(mode="json", exclude={"reviews"})},
    }
    if isinstance(item, SourceProduct):
        fields["images"] = item.images or images
        fields["main_image_url"] = (item.images or images or [None])[0]
        fields["moq"] = item.moq
        fields["weight_grams"] = item.weight_grams
        fields["description_original"] = item.description
        fields["raw"]["reviews"] = [r.model_dump(mode="json") for r in item.reviews]
    return fields


def build_results(
    brief: SourcingBrief,
    items: list[SourceItem],
    ranked: dict[str, RankItemOut],
    rates: dict[str, Any],
    origin: CandidateOrigin,
    guide: guidance.Guidance | None = None,
) -> list[dict[str, Any]]:
    """Gom cùng mẫu (same_model_key), giữ tin rao tốt nhất mỗi mẫu, lọc theo đề, xếp theo điểm.

    `guide` (c5 + c6): nguyên tắc của chị và gu đã học chỉnh điểm; món trái nguyên tắc «không chấp nhận» xuống cuối."""
    ceiling = brief.target_landed_cost_max_vnd
    groups: dict[str, list[tuple[SourceItem, RankItemOut, int | None]]] = {}
    for it in items:
        r = ranked.get(_ref(it))
        if r is None or not r.keep:
            continue
        landed = landed_total(it.price_amount, it.currency, rates=rates)
        if ceiling and landed and landed > ceiling:  # chốt chặn cứng, không phụ thuộc AI
            continue
        key = r.same_model_key or _ref(it)
        groups.setdefault(key, []).append((it, r, landed))
    out: list[dict[str, Any]] = []
    prefix = brief.id.hex[:8]
    for key, members in groups.items():
        members.sort(key=lambda m: (-m[1].score, m[2] or 10**12))
        best, r, landed = members[0]
        reason = r.reason
        if len(members) > 1:
            reason = f"{reason} Cùng mẫu có ở {len(members)} shop."
        score = r.score
        over = price_over_range(landed, brief.price_max_vnd)
        if over:  # giá về tay đã vượt giá bán tối đa của đề → khó có lãi: hạ điểm và nói rõ
            score = max(0, score - OVER_PRICE_PENALTY)
            reason = f"{reason} {over}"
        fields = _candidate_fields(
            best,
            brief=brief,
            origin=origin,
            title_vi=r.title_vi,
            rates=rates,
            score=score,
            reason=reason,
            group=f"{prefix}:{slugify(key, max_length=50)}",
            offers=[_offer(m[0], rates) for m in members],
        )
        if over:
            fields["raw"]["price_flag"] = {"landed_vnd": landed, "price_max_vnd": brief.price_max_vnd}
        out.append(fields)
    if guide:
        out = [guidance.apply(guide, c) for c in out]
    out.sort(key=lambda c: (bool((c["raw"].get("guidance") or {}).get("violates")), -(c["ai_score"] or 0)))
    return out


OVER_PRICE_PENALTY = 40


def price_over_range(landed: int | None, price_max_vnd: int | None) -> str | None:
    """Giá về tay ≥ giá bán tối đa chị đặt cho đề (bán không có lãi) → câu cảnh báo; không thì None."""
    if not landed or not price_max_vnd or landed < price_max_vnd:
        return None
    return f"Lưu ý: giá về tay ước {format_vnd(landed)} đã vượt giá bán tối đa {format_vnd(price_max_vnd)} của đề."


def image_hashing_enabled() -> bool:
    """Chỉ băm ảnh thật. Dữ liệu giả lập (driver mock, AI fake) dùng ảnh giữ chỗ giống hệt nhau trừ dòng chữ → băm
    theo hình sẽ báo trùng sai; test không tải ảnh qua mạng (test tự bật bằng monkeypatch)."""
    return not settings.is_test and settings.ai_provider != "fake" and sources().name != "mock"


async def attach_image_hashes(results: list[dict[str, Any]]) -> None:
    """b7: băm theo hình ảnh chính của ứng viên và ảnh của từng shop cùng mẫu (lưu vào `image_hash` / offer)."""
    if not results or not image_hashing_enabled():
        return
    urls = [r.get("main_image_url") for r in results]
    urls += [o.get("image_url") for r in results for o in (r.get("raw") or {}).get("offers", [])]
    hashes = await imagehash.hash_urls([u for u in urls if u])
    for r in results:
        if h := hashes.get(r.get("main_image_url") or ""):
            r["image_hash"] = h
        for o in (r.get("raw") or {}).get("offers", []):
            if hashes.get(o.get("image_url") or ""):
                o["image_hash"] = hashes[o["image_url"]]


async def _search_all(
    db: AsyncSession, run: SourcingRun, brief: SourcingBrief, rates: dict[str, Any]
) -> tuple[list[SourceItem], list[str]]:
    platforms = [SourcePlatform(p) for p in (run.platforms or brief.platforms or [])] or DEFAULT_PLATFORMS
    found: dict[str, SourceItem] = {}
    errors: list[str] = []
    for i, p in enumerate(platforms):
        label, currency, _ = PLATFORMS.get(p, (p.value, "USD", "en"))
        ceiling = (
            source_price_ceiling(int(brief.target_landed_cost_max_vnd * 1.1), currency, rates)
            if brief.target_landed_cost_max_vnd and currency != "VND"
            else None
        )
        query = SourceQuery(
            keywords=_keywords_for(brief, p),
            platforms=[p],
            price_max=ceiling,
            currency=currency,
            limit=PER_PLATFORM_LIMIT,
        )
        try:
            items = await sources().search(query)
        except (IntegrationError, IntegrationNotConfigured, ai.AIError) as e:
            errors.append(f"{label}: {getattr(e, 'message', str(e))}")
            items = []
        for it in items:
            found.setdefault(_ref(it), it)
        await _set_progress(
            db, run, step="search", done=i + 1, total=len(platforms), note=f"Đã quét {label}: {len(items)} món"
        )
    return list(found.values()), errors


async def _save(
    db: AsyncSession,
    run: SourcingRun,
    brief: SourcingBrief,
    results: list[dict[str, Any]],
    *,
    ai_run_id: uuid.UUID | None,
    sources_: list[dict[str, str]],
) -> control.ProposeOutcome:
    top = [{"title": c["title_vi"], "score": c["ai_score"], "reason": c["rank_reason"]} for c in results[:5]]
    return await control.propose(
        "sourcing.save_candidates",
        f"Lưu {len(results)} ứng viên cho đề «{brief.title}»",
        {"run_id": str(run.id), "brief_id": str(brief.id), "candidates": results},
        {"count": len(results), "top": top, "href": f"/desk/san-hang/de/{brief.id}"},
        db=db,
        summary=f"Quét {run.found_count} món, {len(results)} món đạt tiêu chí.",
        sources=sources_,
        ref_type="sourcing_runs",
        ref_id=run.id,
        ai_run_id=ai_run_id,
        dedupe_key=f"run:{run.id}",
    )


async def _finish(db: AsyncSession, run: SourcingRun, out: control.ProposeOutcome, errors: list[str]) -> None:
    note_err = (" · Lỗi: " + "; ".join(errors)) if errors else ""
    if out.status == "applied":
        result = out.result or {}
        run.status = RunStatus.SUCCEEDED
        await _set_progress(
            db,
            run,
            step="done",
            candidate_ids=result.get("candidate_ids", []),
            note=f"Xong: {run.above_threshold_count} món đạt tiêu chí, {run.new_count} món mới"
            + (f", {len(result['elsewhere_ids'])} món đã có ở đề khác" if result.get("elsewhere_ids") else "")
            + note_err,
            elsewhere_ids=result.get("elsewhere_ids", []),
        )
    elif out.status == "pending":
        run.status = RunStatus.SUCCEEDED
        await _set_progress(
            db, run, step="pending", approval_item_id=str(out.item_id), note="Kết quả đang chờ chị duyệt ở Chờ duyệt."
        )
    elif out.status == "blocked":
        run.status = RunStatus.CANCELLED
        await _set_progress(db, run, step="blocked", note="Việc lưu ứng viên đang tắt trong Mức tự chủ.")
    else:
        run.status = RunStatus.FAILED
        run.error = out.error
        await _set_progress(db, run, step="failed", note="Lưu ứng viên bị lỗi.")


async def _fail(db: AsyncSession, run: SourcingRun, message: str) -> None:
    run_id = run.id  # đọc trước khi rollback (rollback làm hết hạn mọi đối tượng)
    await db.rollback()
    run = await get_run(db, run_id)
    run.status = RunStatus.FAILED
    run.error = message[:2000]
    run.finished_at = now_utc()
    await _set_progress(db, run, step="failed", note=message[:300])


async def execute_scan(db: AsyncSession, run_id: uuid.UUID) -> SourcingRun:
    """Job a4 / a7: quét từng nguồn → AI xếp hạng → gom cùng mẫu, lọc, xếp → lưu (qua control)."""
    run = await get_run(db, run_id)
    if run.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
        return run
    brief = await get_brief(db, run.brief_id) if run.brief_id else None
    if brief is None:
        await _fail(db, run, "Lượt tìm không gắn với đề nào.")
        return run
    run.status = RunStatus.RUNNING
    run.started_at = now_utc()
    await _set_progress(db, run, step="search", done=0, total=len(run.platforms or []), note="Bắt đầu quét")
    try:
        rates = await fx_rates(db)
        items, errors = await _search_all(db, run, brief, rates)
        run.found_count = len(items)
        await _set_progress(db, run, step="rank", note=f"AI đang đọc {len(items)} món")
        if not items:
            run.status = RunStatus.SUCCEEDED if not errors else RunStatus.FAILED
            run.error = "; ".join(errors) or None
            run.finished_at = now_utc()
            brief.last_run_at = now_utc()
            await _set_progress(
                db, run, step="done", note="Không tìm thấy món nào." + ("" if not errors else " Nguồn lỗi.")
            )
            return run
        ranked, ai_run_id, srcs = await _rank(_rank_brief(brief), items, rates)
        run.ai_run_id = ai_run_id
        origin = CandidateOrigin.IMAGE if run.kind == RunKind.IMAGE_SEARCH else CandidateOrigin.BRIEF_SCAN
        results = build_results(brief, items, ranked, rates, origin, await guidance.load(db, brief.category_id))
        await attach_image_hashes(results)
        run.above_threshold_count = len(results)
        out = await _save(db, run, brief, results, ai_run_id=ai_run_id, sources_=srcs)
        run.finished_at = now_utc()
        brief.last_run_at = now_utc()
        if run.kind == RunKind.SCHEDULED_SCAN:
            brief.next_run_at = now_utc() + timedelta(days=brief.schedule_interval_days or DEFAULT_INTERVAL_DAYS)
        await _finish(db, run, out, errors)
        if run.kind == RunKind.SCHEDULED_SCAN and out.status == "applied":
            await _alert_new(db, brief, (out.result or {}).get("new_ids", []))
            await db.commit()
    except ai.AIError as e:
        await _fail(db, run, e.message)
    return run


async def _alert_new(db: AsyncSession, brief: SourcingBrief, new_ids: list[str]) -> control.ProposeOutcome | None:
    """a7: chỉ tạo việc chờ chị khi có ứng viên MỚI đạt ngưỡng."""
    if not new_ids:
        return None
    threshold = brief.alert_min_score or DEFAULT_ALERT_SCORE
    rows = (
        (
            await db.execute(
                select(Candidate)
                .where(Candidate.id.in_([uuid.UUID(i) for i in new_ids]), Candidate.ai_score >= threshold)
                .order_by(Candidate.ai_score.desc())
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    best = rows[0]
    return await control.propose(
        "sourcing.scheduled_alert",
        f"{len(rows)} ứng viên mới đạt {threshold} điểm: {brief.title}",
        {"brief_id": str(brief.id), "candidate_ids": [str(c.id) for c in rows]},
        {
            "items": [
                {"id": str(c.id), "title": c.title_vi, "score": c.ai_score, "reason": c.rank_reason} for c in rows
            ],
            "href": f"/desk/san-hang/de/{brief.id}",
        },
        db=db,
        summary=f"Cao nhất: {best.title_vi} ({best.ai_score} điểm).",
        rationale=best.rank_reason,
        ref_type="sourcing_briefs",
        ref_id=brief.id,
        dedupe_key=f"alert:{brief.id}",
        priority=5,
    )


async def save_candidates(db: AsyncSession, run_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Handler `sourcing.save_candidates`: ghi ứng viên, khử trùng theo nguồn và theo «cùng mẫu» trong đề."""
    run = await db.get(SourcingRun, uuid.UUID(run_id))
    created: list[str] = []
    all_ids: list[str] = []
    elsewhere: list[str] = []
    trend_id: uuid.UUID | None = None
    for data in items:
        existing = (
            await db.execute(
                select(Candidate).where(
                    Candidate.source_platform == SourcePlatform(data["source_platform"]),
                    Candidate.source_external_id == data["source_external_id"],
                )
            )
        ).scalar_one_or_none()
        if existing is None and data.get("same_model_group") and data.get("brief_id"):
            existing = (
                await db.execute(
                    select(Candidate)
                    .where(
                        Candidate.brief_id == uuid.UUID(data["brief_id"]),
                        Candidate.same_model_group == data["same_model_group"],
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
        if existing is not None and data.get("brief_id") and existing.brief_id != uuid.UUID(data["brief_id"]):
            elsewhere.append(str(existing.id))  # cùng món đã nằm ở đề khác — không chuyển đề
            continue
        if existing is not None:
            # đã có: cập nhật giá/điểm nguồn, không đụng giai đoạn trên bảng chọn
            existing.raw = {
                **(existing.raw or {}),
                "offers": data["raw"].get("offers") or existing.raw.get("offers", []),
            }
            if data.get("image_hash") and not existing.image_hash:
                existing.image_hash = data["image_hash"]
            if existing.stage == CandidateStage.CANDIDATE and data.get("ai_score") is not None:
                existing.rank_reason = data.get("rank_reason") or existing.rank_reason
                gd = data["raw"].get("guidance")
                if gd or existing.raw.get("guidance"):  # nguyên tắc/gu đổi từ lần trước → chấm lại theo lần này
                    existing.raw = {k: v for k, v in existing.raw.items() if k != "guidance"} | (
                        {"guidance": gd} if gd else {}
                    )
                    existing.ai_score = data["ai_score"]
            all_ids.append(str(existing.id))
            continue
        cand = Candidate(**_coerce(data))
        if run is not None:
            cand.run_id = run.id
        if cand.brief_id and trend_id is None:
            brief = await db.get(SourcingBrief, cand.brief_id)
            tid = (brief.filters or {}).get("trend_signal_id") if brief else None
            trend_id = uuid.UUID(tid) if tid else None
        cand.trend_signal_id = trend_id
        db.add(cand)
        await db.flush()
        created.append(str(cand.id))
        all_ids.append(str(cand.id))
    if trend_id and created:
        trend = await db.get(TrendSignal, trend_id)
        if trend is not None and trend.candidate_id is None:
            trend.candidate_id = uuid.UUID(created[0])
            trend.status = TrendStatus.CONVERTED
    if run is not None:
        run.new_count = len(created)
    return {"candidate_ids": all_ids, "new_ids": created, "new_count": len(created), "elsewhere_ids": elsewhere}


def _coerce(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    for k in ("brief_id", "category_id"):
        out[k] = uuid.UUID(out[k]) if out.get(k) else None
    out["origin"] = CandidateOrigin(out["origin"])
    out["source_platform"] = SourcePlatform(out["source_platform"])
    out["original_language"] = Language(out.get("original_language") or "zh")
    for k in ("price_amount", "rating"):
        out[k] = Decimal(str(out[k])) if out.get(k) is not None else None
    return out


async def undo_candidates(db: AsyncSession, ids: list[str]) -> int:
    """Hoàn tác lưu ứng viên: xoá những món vẫn còn ở cột Ứng viên (chưa đụng tới trên bảng chọn)."""
    n = 0
    for cid in ids:
        c = await db.get(Candidate, uuid.UUID(cid))
        if c is not None and c.stage == CandidateStage.CANDIDATE:
            await db.delete(c)
            n += 1
    return n


# ---- a2: dán link ------------------------------------------------------------------------------------------------


async def execute_import(db: AsyncSession, run_id: uuid.UUID) -> SourcingRun:
    run = await get_run(db, run_id)
    if run.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
        return run
    run.status = RunStatus.RUNNING
    run.started_at = now_utc()
    await _set_progress(db, run, step="fetch", done=0, total=2, note="Đang đọc trang sản phẩm")
    url = str(run.input.get("url"))
    try:
        product = await sources().fetch_product(url)
        run.found_count = 1
        await _set_progress(db, run, step="translate", done=1, total=2, note="Đang dịch sang tiếng Việt")
        tr = await ai.run(
            "sourcing.translate_product",
            TranslateIn(
                platform=platform_label(product.platform),
                language=product.language.value,
                title=product.title,
                description=product.description,
                specs=product.specs,
                variants=product.variants,
            ),
            TranslateOut,
        )
    except (IntegrationError, IntegrationNotConfigured) as e:
        await _fail(db, run, f"Không lấy được hồ sơ từ link: {e.message}")
        return run
    except ai.AIError as e:
        await _fail(db, run, e.message)
        return run
    brief = await db.get(SourcingBrief, run.brief_id) if run.brief_id else None
    rates = await fx_rates(db)
    t = tr.output
    fields = _candidate_fields(product, brief=brief, origin=CandidateOrigin.LINK, title_vi=t.title_vi, rates=rates)
    fields["description_vi"] = t.description_vi
    fields["specs"] = {s.name: s.value for s in t.specs_vi}
    fields["variants"] = [{"name": v} for v in t.variants_vi]
    fields["rank_reason"] = "Chị dán link món này."
    await attach_image_hashes([fields])
    run.ai_run_id = tr.run_id
    out = await control.propose(
        "sourcing.import_link",
        f"Lấy hồ sơ từ link: {t.title_vi}",
        {"run_id": str(run.id), "candidate": fields},
        {"title": t.title_vi, "url": url, "platform": platform_label(product.platform)},
        db=db,
        summary=t.description_vi[:300],
        sources=[{"url": url, "title": product.title}],
        ref_type="sourcing_runs",
        ref_id=run.id,
        ai_run_id=tr.run_id,
        dedupe_key=f"run:{run.id}",
    )
    run.finished_at = now_utc()
    run.above_threshold_count = 1
    await _finish(db, run, out, [])
    return run


async def save_imported(db: AsyncSession, run_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Handler `sourcing.import_link`: tạo hoặc cập nhật ứng viên theo (nguồn, mã ở nguồn)."""
    existing = (
        await db.execute(
            select(Candidate).where(
                Candidate.source_platform == SourcePlatform(data["source_platform"]),
                Candidate.source_external_id == data["source_external_id"],
            )
        )
    ).scalar_one_or_none()
    fields = _coerce(data)
    if existing is not None:
        for k, v in fields.items():
            if k in ("brief_id", "origin", "category_id") and getattr(existing, k) is not None:
                continue
            setattr(existing, k, v)
        await db.flush()
        return {"candidate_ids": [str(existing.id)], "new_ids": [], "created": False}
    cand = Candidate(**fields, run_id=uuid.UUID(run_id))
    db.add(cand)
    await db.flush()
    run = await db.get(SourcingRun, uuid.UUID(run_id))
    if run is not None:
        run.new_count = 1
    return {"candidate_ids": [str(cand.id)], "new_ids": [str(cand.id)], "created": True}


# ---- a3: tìm bằng ảnh --------------------------------------------------------------------------------------------


async def execute_image_search(db: AsyncSession, run_id: uuid.UUID) -> SourcingRun:
    from app.core.storage import get_storage

    run = await get_run(db, run_id)
    if run.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
        return run
    run.status = RunStatus.RUNNING
    run.started_at = now_utc()
    await _set_progress(db, run, step="describe", done=0, total=3, note="AI đang xem ảnh")
    try:
        data = await get_storage().get(run.input["storage_key"])
        sha = hashlib.sha256(data).hexdigest()[:16]
        res = await ai.run(
            "sourcing.describe_image",
            DescribeImageIn(note=run.input.get("note"), image_sha=sha),
            DescribeImageOut,
            images=[ai.AIImage(data=data, media_type=run.input.get("content_type") or None)],
        )
        d = res.output
        run.ai_run_id = res.run_id
        cats = await _categories(db)
        t = vocab.find_type(d.product_type)
        brief = SourcingBrief(
            title=d.title[:200],
            raw_text=run.input.get("note") or d.description_vi,
            input_mode=BriefInputMode.IMAGE,
            status=BriefStatus.ACTIVE,
            confirmed_at=now_utc(),
            interpretation=d.description_vi,
            filters={"product_type": d.product_type, "materials": d.materials, "image_key": run.input["storage_key"]},
            keywords_vi=d.keywords_vi or [d.product_type],
            keywords_translated={"zh": d.keywords_zh, "ja": d.keywords_ja, "en": d.keywords_en},
            platforms=[p.value for p in DEFAULT_PLATFORMS],
            category_id=cats.get(t.category) if t else None,
            created_by_id=uuid.UUID(run.input["user_id"]) if run.input.get("user_id") else None,
            ai_run_id=res.run_id,
        )
        db.add(brief)
        await db.flush()
        run.brief_id = brief.id
        run.platforms = brief.platforms
        await _set_progress(db, run, step="search", done=1, total=3, brief_id=str(brief.id), note=f"AI thấy: {d.title}")
        await events.emit("brief.created", {"brief_id": str(brief.id)}, db=db)
        rates = await fx_rates(db)
        found: dict[str, SourceItem] = {}
        errors: list[str] = []
        try:
            for it in await sources().search_by_image(data, platforms=DEFAULT_PLATFORMS[:2], limit=12):
                found.setdefault(_ref(it), it)
        except (IntegrationError, IntegrationNotConfigured) as e:
            errors.append(f"Tìm bằng ảnh: {e.message}")
        items, errs = await _search_all(db, run, brief, rates)
        errors += errs
        for it in items:
            found.setdefault(_ref(it), it)
        run.found_count = len(found)
        await _set_progress(db, run, step="rank", done=2, total=3, note=f"AI đang đọc {len(found)} món")
        ranked, rank_run, srcs = await _rank(_rank_brief(brief), list(found.values()), rates)
        guide = await guidance.load(db, brief.category_id)
        results = build_results(brief, list(found.values()), ranked, rates, CandidateOrigin.IMAGE, guide)
        await attach_image_hashes(results)
        run.above_threshold_count = len(results)
        out = await _save(db, run, brief, results, ai_run_id=rank_run, sources_=srcs)
        run.finished_at = now_utc()
        brief.last_run_at = now_utc()
        await _finish(db, run, out, errors)
    except ai.AIError as e:
        await _fail(db, run, e.message)
    return run


# ---- a5: radar xu hướng ------------------------------------------------------------------------------------------

SHOP_FOCUS = "Gia dụng nhỏ, đồ tiện ích không điện: bếp, phòng tắm, sắp xếp lưu trữ, đồ mang theo"


async def execute_trends(db: AsyncSession, run_id: uuid.UUID) -> SourcingRun:
    run = await get_run(db, run_id)
    if run.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
        return run
    run.status = RunStatus.RUNNING
    run.started_at = now_utc()
    await _set_progress(db, run, step="collect", note="Đang thu tín hiệu")
    try:
        items = await sources().trends(limit=12)
        run.found_count = len(items)
        refs = {f"t{i}": it for i, it in enumerate(items)}
        res = await ai.run(
            "sourcing.trend_reasons",
            TrendIn(
                shop_focus=SHOP_FOCUS,
                items=[
                    TrendItemIn(
                        ref=ref,
                        platform=it.platform.value,
                        title=it.title,
                        language=it.language.value,
                        metrics=it.metrics,
                        snippet=it.snippet,
                    )
                    for ref, it in refs.items()
                ],
            ),
            TrendOut,
        )
    except (IntegrationError, IntegrationNotConfigured) as e:
        await _fail(db, run, f"Không thu được tín hiệu: {e.message}")
        return run
    except ai.AIError as e:
        await _fail(db, run, e.message)
        return run
    run.ai_run_id = res.run_id
    signals = []
    for r in res.output.items:
        it = refs.get(r.ref)
        if it is None or not r.keep:
            continue
        signals.append(
            {
                "platform": it.platform.value,
                "title": it.title,
                "title_vi": r.title_vi,
                "url": it.url,
                "image_url": it.image_url,
                "reason": r.reason,
                "metrics": it.metrics,
                "score": r.score,
            }
        )
    signals.sort(key=lambda s: -s["score"])
    run.above_threshold_count = len(signals)
    out = await control.propose(
        "sourcing.save_trends",
        f"Radar xu hướng: {len(signals)} món đáng xem",
        {"run_id": str(run.id), "detected_on": local_today().isoformat(), "signals": signals},
        {
            "items": [{"title": s["title_vi"], "reason": s["reason"]} for s in signals[:5]],
            "href": "/desk/san-hang?tab=xu-huong",
        },
        db=db,
        sources=[{"url": s["url"], "title": s["title_vi"]} for s in signals],
        ref_type="sourcing_runs",
        ref_id=run.id,
        ai_run_id=res.run_id,
        dedupe_key=f"run:{run.id}",
    )
    run.finished_at = now_utc()
    await _finish(db, run, out, [])
    return run


async def save_trends(db: AsyncSession, run_id: str, detected_on: str, signals: list[dict[str, Any]]) -> dict[str, Any]:
    from datetime import date

    day = date.fromisoformat(detected_on)
    ids, new = [], 0
    created: list[str] = []
    before: dict[str, dict[str, Any]] = {}  # tín hiệu đã có trong ngày: giá trị cũ để hoàn tác
    for s in signals:
        row = (
            await db.execute(
                select(TrendSignal).where(
                    TrendSignal.platform == SourcePlatform(s["platform"]),
                    TrendSignal.url == s["url"],
                    TrendSignal.detected_on == day,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = TrendSignal(
                platform=SourcePlatform(s["platform"]), url=s["url"], detected_on=day, run_id=uuid.UUID(run_id)
            )
            db.add(row)
            new += 1
        elif str(row.id) not in before:
            before[str(row.id)] = {k: getattr(row, k) for k in _TREND_FIELDS}
        row.title = s["title"]
        row.title_vi = s["title_vi"][:300]
        row.image_url = s.get("image_url")
        row.reason = s.get("reason")
        row.metrics = s.get("metrics") or {}
        row.score = s.get("score")
        await db.flush()
        ids.append(str(row.id))
        if row.id and str(row.id) not in before and str(row.id) not in created:
            created.append(str(row.id))
    run = await db.get(SourcingRun, uuid.UUID(run_id))
    if run is not None:
        run.new_count = new
    return {"trend_ids": ids, "new_count": new, "created_ids": created, "before": before}


_TREND_FIELDS = ("title", "title_vi", "image_url", "reason", "metrics", "score")


async def undo_trends(db: AsyncSession, created: list[str], before: dict[str, dict[str, Any]]) -> None:
    """Hoàn tác lưu xu hướng: xoá tín hiệu mới mà chị chưa đụng tới, trả lại nội dung cũ cho tín hiệu đã có."""
    for tid in created:
        row = await db.get(TrendSignal, uuid.UUID(tid))
        if row is not None and row.status == TrendStatus.NEW and row.candidate_id is None:
            await db.delete(row)
    for tid, old in before.items():
        row = await db.get(TrendSignal, uuid.UUID(tid))
        if row is not None:
            for k in _TREND_FIELDS:
                setattr(row, k, old.get(k))


async def brief_from_trend(db: AsyncSession, trend: TrendSignal, user_id: uuid.UUID | None) -> SourcingBrief:
    text = (
        f"Tìm {trend.title_vi.lower()} (đang lên trên {platform_label(trend.platform)}). {trend.reason or ''}".strip()
    )
    brief = await create_brief(
        db, text, input_mode=BriefInputMode.TREND, user_id=user_id, filters={"trend_signal_id": str(trend.id)}
    )
    if trend.status == TrendStatus.NEW:
        trend.status = TrendStatus.WATCHING
    return brief


# ---- a6: nghe khách muốn gì --------------------------------------------------------------------------------------

_SKIP_INTENTS = {"ask_price", "ask_stock", "ask_shipping", "order_status", "complaint", "small_talk"}


async def _mention_exists(db: AsyncSession, source_type: str, source_id: uuid.UUID) -> bool:
    q = select(DemandMention.id).where(DemandMention.source_type == source_type, DemandMention.source_id == source_id)
    return (await db.execute(q.limit(1))).first() is not None


async def record_demand(
    db: AsyncSession,
    text: str,
    *,
    source: DemandSource,
    source_type: str,
    source_id: uuid.UUID,
    channel: Channel | None = None,
    customer_id: uuid.UUID | None = None,
    find_request_id: uuid.UUID | None = None,
) -> control.ProposeOutcome | None:
    """AI đọc lời khách → nếu là nhu cầu một món hàng thì ghi `demand_signals` + `demand_mentions` (qua control)."""
    if await _mention_exists(db, source_type, source_id):
        return None
    existing = (
        await db.execute(
            select(DemandSignal.normalized_key, DemandSignal.title)
            .where(DemandSignal.status.in_([DemandStatus.OPEN, DemandStatus.SEARCHING]))
            .order_by(DemandSignal.last_asked_at.desc().nulls_last())
            .limit(50)
        )
    ).all()
    res = await ai.run(
        "sourcing.extract_demand",
        ExtractDemandIn(
            text=text[:2000], source=source.value, existing=[ExistingDemand(key=k, title=t) for k, t in existing]
        ),
        ExtractDemandOut,
    )
    d = res.output
    if not d.is_demand or not d.title:
        return None
    keys = {k for k, _ in existing}
    key = d.match_key if d.match_key in keys else normalize_key(d.title)
    return await control.propose(
        "sourcing.record_demand",
        f"Ghi nhu cầu khách: {d.title}",
        {
            "key": key,
            "title": d.title[:300],
            "detail": d.detail,
            "text": text[:2000],
            "source": source.value,
            "source_type": source_type,
            "source_id": str(source_id),
            "channel": channel.value if channel else None,
            "customer_id": str(customer_id) if customer_id else None,
            "find_request_id": str(find_request_id) if find_request_id else None,
        },
        {"title": d.title, "text": text[:300]},
        db=db,
        ref_type="demand_signals",
        ai_run_id=res.run_id,
    )


async def save_demand(db: AsyncSession, p: dict[str, Any]) -> dict[str, Any]:
    """Handler `sourcing.record_demand` (idempotent theo nguồn)."""
    source_id = uuid.UUID(p["source_id"])
    signal = (
        await db.execute(select(DemandSignal).where(DemandSignal.normalized_key == p["key"]))
    ).scalar_one_or_none()
    now = now_utc()
    created = signal is None
    prev = (
        {}
        if signal is None
        else {
            "find_request_id": str(signal.find_request_id) if signal.find_request_id else None,
            "last_asked_at": signal.last_asked_at.isoformat() if signal.last_asked_at else None,
            "status": signal.status.value,
        }
    )
    mention_id: str | None = None
    if signal is None:
        signal = DemandSignal(
            title=p["title"], normalized_key=p["key"], description=p.get("detail"), first_asked_at=now
        )
        db.add(signal)
        await db.flush()
    if p.get("find_request_id") and signal.find_request_id is None:
        signal.find_request_id = uuid.UUID(p["find_request_id"])
    if not await _mention_exists(db, p["source_type"], source_id):
        mention = DemandMention(
            signal_id=signal.id,
            source=DemandSource(p["source"]),
            channel=Channel(p["channel"]) if p.get("channel") else None,
            customer_id=uuid.UUID(p["customer_id"]) if p.get("customer_id") else None,
            source_type=p["source_type"],
            source_id=source_id,
            text=p["text"],
        )
        db.add(mention)
        await db.flush()
        mention_id = str(mention.id)
    signal.last_asked_at = now
    if signal.status == DemandStatus.DISMISSED:
        signal.status = DemandStatus.OPEN
    await recount_demand(db, signal)
    return {
        "signal_id": str(signal.id),
        "ask_count": signal.ask_count,
        "undo": {"signal_id": str(signal.id), "created": created, "mention_id": mention_id, "prev": prev},
    }


async def undo_demand(db: AsyncSession, u: dict[str, Any]) -> None:
    """Hoàn tác ghi nhu cầu: bỏ lượt nhắc vừa ghi; nhu cầu mới tạo mà không còn lượt nhắc nào (và chưa mở đề) thì xoá."""
    from datetime import datetime

    signal = await db.get(DemandSignal, uuid.UUID(u["signal_id"]))
    if signal is None:
        return
    if u.get("mention_id"):
        m = await db.get(DemandMention, uuid.UUID(u["mention_id"]))
        if m is not None:
            await db.delete(m)
            await db.flush()
    left = (await db.execute(select(func.count()).where(DemandMention.signal_id == signal.id))).scalar_one()
    if u.get("created") and not left and signal.status == DemandStatus.OPEN:
        await db.delete(signal)
        return
    prev = u.get("prev") or {}
    if prev:
        signal.find_request_id = uuid.UUID(prev["find_request_id"]) if prev.get("find_request_id") else None
        signal.last_asked_at = datetime.fromisoformat(prev["last_asked_at"]) if prev.get("last_asked_at") else None
        if signal.status == DemandStatus.OPEN and prev.get("status"):
            signal.status = DemandStatus(prev["status"])
    await recount_demand(db, signal)


async def recount_demand(db: AsyncSession, signal: DemandSignal) -> None:
    """Số người khác nhau đã hỏi: theo khách (nếu biết), theo hội thoại, cộng số người bấm «cùng cần» ở Nhờ tìm."""
    from app.modules.catalog.models import FindRequest  # chỉ đọc
    from app.modules.inbox.models import Message  # chỉ đọc

    mentions = (await db.execute(select(DemandMention).where(DemandMention.signal_id == signal.id))).scalars().all()
    people: set[str] = set()
    votes = 0
    msg_ids = [m.source_id for m in mentions if m.source_type == "messages" and m.source_id and not m.customer_id]
    threads = (
        dict((await db.execute(select(Message.id, Message.thread_id).where(Message.id.in_(msg_ids)))).all())
        if msg_ids
        else {}
    )
    for m in mentions:
        if m.customer_id:
            people.add(f"c:{m.customer_id}")
        elif m.source_type == "messages" and m.source_id in threads:
            people.add(f"t:{threads[m.source_id]}")
        elif m.source_type == "find_requests" and m.source_id:
            fr = await db.get(FindRequest, m.source_id)
            people.add(f"fr:{m.source_id}")
            votes += max(0, (fr.vote_count if fr else 0) - 1)  # người gửi + những người bấm cùng cần
        else:
            people.add(f"m:{m.source_type}:{m.source_id or m.id}")
    signal.mention_count = len(mentions)
    signal.ask_count = len(people) + votes


async def on_message(db: AsyncSession, thread_id: str, message_id: str) -> control.ProposeOutcome | None:
    from app.modules.inbox.models import Message, Thread  # chỉ đọc

    msg = await db.get(Message, uuid.UUID(message_id))
    if msg is None or msg.direction.value != "inbound" or msg.sender.value != "customer":
        return None
    if msg.intent is not None and msg.intent.value in _SKIP_INTENTS:
        return None
    thread = await db.get(Thread, uuid.UUID(thread_id)) or await db.get(Thread, msg.thread_id)
    kind = getattr(getattr(thread, "kind", None), "value", "")
    return await record_demand(
        db,
        msg.body,
        source=DemandSource.COMMENT if kind == "comment" else DemandSource.MESSAGE,
        source_type="messages",
        source_id=msg.id,
        channel=thread.channel if thread else None,
        customer_id=thread.customer_id if thread else None,
    )


async def on_find_request(db: AsyncSession, find_request_id: str) -> DemandSignal | None:
    from app.modules.catalog.models import FindRequest  # chỉ đọc

    fr = await db.get(FindRequest, uuid.UUID(find_request_id))
    if fr is None:
        return None
    text = fr.title + (f". {fr.description}" if fr.description else "")
    await record_demand(
        db,
        text,
        source=DemandSource.FIND_REQUEST,
        source_type="find_requests",
        source_id=fr.id,
        customer_id=fr.customer_id,
        find_request_id=fr.id,
    )
    return await signal_for_source(db, "find_requests", fr.id)


async def signal_for_source(db: AsyncSession, source_type: str, source_id: uuid.UUID) -> DemandSignal | None:
    q = (
        select(DemandSignal)
        .join(DemandMention, DemandMention.signal_id == DemandSignal.id)
        .where(DemandMention.source_type == source_type, DemandMention.source_id == source_id)
    )
    return (await db.execute(q.limit(1))).scalar_one_or_none()


async def on_find_request_threshold(db: AsyncSession, find_request_id: str) -> control.ProposeOutcome | None:
    from app.modules.catalog.models import FindRequest  # chỉ đọc

    fr = await db.get(FindRequest, uuid.UUID(find_request_id))
    if fr is None:
        return None
    signal = await signal_for_source(db, "find_requests", fr.id) or await on_find_request(db, find_request_id)
    if signal is None:
        return None
    signal.find_request_id = signal.find_request_id or fr.id
    await recount_demand(db, signal)
    if signal.status != DemandStatus.OPEN:
        return None
    return await control.propose(
        "sourcing.suggest_demand_brief",
        f"Đủ {fr.vote_count} người cùng cần «{fr.title}»: mở đề tìm?",
        {"signal_id": str(signal.id), "find_request_id": str(fr.id)},
        {
            "title": fr.title,
            "votes": fr.vote_count,
            "ask_count": signal.ask_count,
            "href": "/desk/san-hang?tab=khach-hoi",
        },
        db=db,
        summary=f"{signal.ask_count} người đã hỏi món này.",
        ref_type="demand_signals",
        ref_id=signal.id,
        dedupe_key=f"demand:{signal.id}",
        priority=3,
        ai_generated=False,
    )


async def brief_from_demand(db: AsyncSession, signal: DemandSignal, user_id: uuid.UUID | None) -> SourcingBrief:
    existing = (
        await db.execute(
            select(SourcingBrief)
            .where(SourcingBrief.demand_signal_id == signal.id, SourcingBrief.status != BriefStatus.ARCHIVED)
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    text = f"Tìm {signal.title}" + (f". Khách nói: {signal.description}" if signal.description else "")
    text += f" ({signal.ask_count} người đã hỏi)."
    brief = await create_brief(
        db,
        text,
        input_mode=BriefInputMode.DEMAND,
        user_id=user_id,
        demand_signal_id=signal.id,
        find_request_id=signal.find_request_id,
    )
    signal.status = DemandStatus.SEARCHING
    return brief


async def execute_demand_digest(db: AsyncSession, run_id: uuid.UUID) -> SourcingRun:
    """Gom lại: rà tin nhắn hỏi món 14 ngày qua và lời nhờ tìm chưa được ghi nhận (lưới an toàn cho người nghe sự kiện)."""
    from app.core.enums import Actor
    from app.modules.catalog.models import FindRequest, FindRequestStatus  # chỉ đọc
    from app.modules.inbox.models import Direction, Intent, Message  # chỉ đọc

    run = await get_run(db, run_id)
    run.status = RunStatus.RUNNING
    run.started_at = now_utc()
    await _set_progress(db, run, step="collect", note="Đang rà tin nhắn và lời nhờ tìm")
    recorded = (select(DemandMention.source_id).where(DemandMention.source_id.is_not(None))).scalar_subquery()
    msgs = (
        (
            await db.execute(
                select(Message)
                .where(
                    Message.direction == Direction.INBOUND,
                    Message.sender == Actor.CUSTOMER,
                    Message.intent.in_([Intent.FIND_REQUEST, Intent.ASK_PRODUCT]),
                    Message.sent_at > now_utc() - timedelta(days=14),
                    Message.id.not_in(recorded),
                )
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    frs = (
        (
            await db.execute(
                select(FindRequest)
                .where(
                    FindRequest.status.in_([FindRequestStatus.OPEN, FindRequestStatus.THRESHOLD_REACHED]),
                    FindRequest.id.not_in(recorded),
                )
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    run.found_count = len(msgs) + len(frs)
    n = 0
    try:
        for m in msgs:
            out = await on_message(db, str(m.thread_id), str(m.id))
            n += 1 if out and out.status == "applied" else 0
        for fr in frs:
            await on_find_request(db, str(fr.id))
            n += 1
    except ai.AIError as e:
        await _fail(db, run, e.message)
        return run
    run.new_count = n
    run.status = RunStatus.SUCCEEDED
    run.finished_at = now_utc()
    await _set_progress(db, run, step="done", note=f"Đã rà {run.found_count} lời khách, ghi {n} nhu cầu")
    return run


# ---- a7: săn theo lịch -------------------------------------------------------------------------------------------


async def due_briefs(db: AsyncSession) -> list[SourcingBrief]:
    q = select(SourcingBrief).where(
        SourcingBrief.is_scheduled.is_(True),
        SourcingBrief.status == BriefStatus.ACTIVE,
        SourcingBrief.next_run_at.is_not(None),
        SourcingBrief.next_run_at <= now_utc(),
    )
    return list((await db.execute(q)).scalars().all())


async def run_due_scheduled(db: AsyncSession) -> list[SourcingRun]:
    runs = []
    for brief in await due_briefs(db):
        try:
            run = await start_scan(db, brief, RunKind.SCHEDULED_SCAN)
        except (BadRequest, Conflict) as e:
            log.info("Bỏ qua đề theo lịch %s: %s", brief.id, e.message)
            continue
        await db.commit()
        runs.append(await execute_scan(db, run.id))
    return runs


# ---- số liệu cho thẻ / danh sách ---------------------------------------------------------------------------------


async def brief_counts(db: AsyncSession, brief_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    if not brief_ids:
        return {}
    rows = (
        await db.execute(
            select(
                Candidate.brief_id,
                func.count(),
                func.count().filter(Candidate.stage == CandidateStage.SELECTED),
            )
            .where(Candidate.brief_id.in_(brief_ids), Candidate.is_archived.is_(False))
            .group_by(Candidate.brief_id)
        )
    ).all()
    return {b: (int(n), int(s)) for b, n, s in rows}


async def last_runs(db: AsyncSession, brief_ids: list[uuid.UUID]) -> dict[uuid.UUID, SourcingRun]:
    if not brief_ids:
        return {}
    ranked = (
        select(
            SourcingRun.id,
            func.row_number()
            .over(partition_by=SourcingRun.brief_id, order_by=SourcingRun.created_at.desc())
            .label("rn"),
        )
        .where(SourcingRun.brief_id.in_(brief_ids))
        .subquery()
    )
    rows = (
        (await db.execute(select(SourcingRun).join(ranked, ranked.c.id == SourcingRun.id).where(ranked.c.rn == 1)))
        .scalars()
        .all()
    )
    return {r.brief_id: r for r in rows if r.brief_id}


def offers_of(c: Candidate) -> list[dict[str, Any]]:
    offers = (c.raw or {}).get("offers")
    return offers if isinstance(offers, list) else []


# ---- ảnh và chi tiết nhà cung cấp (chỉ desk) ---------------------------------------------------------------------
#
# Mỗi ứng viên ở phía chọn hàng phải có ảnh của nhà cung cấp để chị hình dung món hàng. Ảnh lấy từ kết quả tìm (nếu
# nguồn trả ảnh) và từ trang chi tiết (`fetch_product`: ảnh, thông số gốc, đánh giá); bản sao lưu vào kho riêng
# (`gallery.cache_images`). Lấy chi tiết bằng driver `web` tốn một lượt AI có web fetch (~8.000–11.000đ), nên tự lấy
# chỉ cho `AUTO_DETAIL_SETTING` món điểm cao nhất mỗi lượt quét; món khác chị bấm «Lấy ảnh và chi tiết».

AUTO_DETAIL_SETTING = "sourcing.auto_detail_top_n"
DEFAULT_AUTO_DETAIL_TOP_N = 5
DETAIL_STALE = timedelta(minutes=15)


def auto_followups_enabled() -> bool:
    """Việc nối sau lượt quét (lưu ảnh, tự lấy chi tiết). Tắt trong test (test gọi trực tiếp) và khi nguồn là giả lập
    (dữ liệu mẫu, e2e: tự lấy chi tiết giả chỉ làm đầy nhật ký AI)."""
    return not settings.is_test and sources().name != "mock"


def detail_state(c: Candidate) -> dict[str, Any] | None:
    st = (c.raw or {}).get("detail_fetch")
    return st if isinstance(st, dict) else None


def _set_detail_state(c: Candidate, **fields: Any) -> None:
    c.raw = {**(c.raw or {}), "detail_fetch": {**(detail_state(c) or {}), **fields}}
    flag_modified(c, "raw")


def detail_busy(c: Candidate) -> bool:
    st = detail_state(c) or {}
    if st.get("status") not in ("queued", "running"):
        return False
    try:
        from datetime import datetime

        return now_utc() - datetime.fromisoformat(st["at"]) < DETAIL_STALE
    except (KeyError, ValueError, TypeError):
        return False


def request_details(c: Candidate) -> bool:
    """Chị bấm «Lấy ảnh và chi tiết». Trả False nếu lượt trước còn đang chạy (không xếp thêm)."""
    if not c.source_url:
        raise BadRequest("Ứng viên này không có link nguồn để lấy ảnh và chi tiết.", code="no_source_url")
    if detail_busy(c):
        return False
    _set_detail_state(c, status="queued", at=now_utc().isoformat(), error=None)
    return True


def details_payload(product: SourceProduct) -> dict[str, Any]:
    return {
        "images": [u for u in (product.images or ([product.image_url] if product.image_url else [])) if u],
        "description_original": product.description,
        "moq": product.moq,
        "weight_grams": product.weight_grams,
        "rating": product.rating,
        "review_count": product.review_count,
        "specs_original": product.specs,
        "reviews": [r.model_dump(mode="json") for r in product.reviews[:30]],
    }


def merge_images(c: Candidate, urls: list[str]) -> int:
    """Thêm ảnh nguồn mới vào ứng viên (giữ ảnh cũ, khử trùng). Trả số ảnh mới thêm."""
    new = [u for u in urls if isinstance(u, str) and u.startswith(("http://", "https://"))]
    before = [u for u in (c.images or []) if isinstance(u, str)]
    merged = list(dict.fromkeys([*before, *new]))
    added = len(merged) - len(before)
    if added:
        c.images = merged
    if not c.main_image_url and merged:
        c.main_image_url = merged[0]
    return added


async def apply_details(db: AsyncSession, candidate_id: str, d: dict[str, Any]) -> dict[str, Any]:
    """Handler `sourcing.fetch_details`: ghi ảnh + chi tiết còn trống. Không đè thứ chị/AI đã có."""
    c = await get_candidate(db, uuid.UUID(candidate_id))
    added = merge_images(c, d.get("images") or [])
    for k in ("description_original", "moq", "weight_grams", "review_count"):
        if getattr(c, k) is None and d.get(k) is not None:
            setattr(c, k, d[k])
    if c.rating is None and d.get("rating") is not None:
        c.rating = Decimal(str(d["rating"]))
    raw = dict(c.raw or {})
    if not raw.get("reviews") and d.get("reviews"):
        raw["reviews"] = d["reviews"]
    raw["detail"] = {"specs_original": d.get("specs_original") or {}, "fetched_at": now_utc().isoformat()}
    c.raw = raw
    flag_modified(c, "raw")
    await db.flush()
    return {"candidate_id": candidate_id, "images_added": added, "image_count": len(c.images or [])}


async def execute_fetch_details(db: AsyncSession, candidate_id: uuid.UUID) -> Candidate:
    """Job «Lấy ảnh và chi tiết»: đọc trang nguồn → ghi qua control → lưu ảnh về kho riêng."""
    from app.modules.sourcing import gallery

    c = await get_candidate(db, candidate_id)
    if not c.source_url:
        return c
    _set_detail_state(c, status="running", at=now_utc().isoformat())
    await db.commit()
    error: str | None = None
    note: str | None = None
    try:
        product = await sources().fetch_product(c.source_url)
    except (IntegrationError, IntegrationNotConfigured, ai.AIError) as e:
        error = f"Không đọc được trang nguồn: {getattr(e, 'message', str(e))}"
    else:
        d = details_payload(product)
        out = await control.propose(
            "sourcing.fetch_details",
            f"Lấy ảnh và chi tiết: {c.title_vi}",
            {"candidate_id": str(c.id), "details": d},
            {"title": c.title_vi, "url": c.source_url, "image_count": len(d["images"]),
             "review_count": len(d["reviews"])},
            db=db,
            summary=f"{len(d['images'])} ảnh, {len(d['reviews'])} đánh giá từ trang nguồn.",
            sources=[{"url": c.source_url, "title": product.title}],
            ref_type="candidates",
            ref_id=c.id,
            dedupe_key=f"details:{c.id}",
        )  # fmt: skip
        if out.status == "pending":
            note = "Chi tiết đang chờ chị duyệt ở Chờ duyệt."
        elif out.status == "blocked":
            error = "Việc lấy ảnh và chi tiết đang tắt trong Mức tự chủ."
        elif out.status == "failed":
            error = out.error or "Ghi chi tiết bị lỗi."
    counts = await gallery.cache_images(c, retry_failed=True)
    n = len(gallery.source_urls(c))
    _set_detail_state(
        c,
        status="failed" if error else "done",
        at=now_utc().isoformat(),
        error=error,
        note=note,
        image_count=n,
        cached=sum(1 for g in gallery.display(c) if g["cached"]),
        failed_images=counts["failed"],
    )
    await db.commit()
    return c


async def cache_candidate_images(db: AsyncSession, ids: list[uuid.UUID]) -> int:
    """Lưu ảnh nguồn của nhiều ứng viên về kho riêng (sau lượt quét / dán link / thẩm định). Trả số ảnh lưu được."""
    from app.modules.sourcing import gallery

    if not gallery.caching_enabled():
        return 0
    n = 0
    for cid in ids:
        c = await db.get(Candidate, cid)
        if c is not None:
            n += (await gallery.cache_images(c))["cached"]
            await db.commit()
    return n


async def auto_detail_ids(db: AsyncSession, candidate_ids: list[str]) -> list[uuid.UUID]:
    """Món điểm cao nhất của lượt quét còn thiếu ảnh (< 2 ảnh) và chưa từng lấy chi tiết — tối đa N (cài đặt)."""
    n = await control.get_setting(db, AUTO_DETAIL_SETTING, DEFAULT_AUTO_DETAIL_TOP_N)
    n = max(0, min(int(n or 0), 20))
    if not n or not candidate_ids:
        return []
    from app.modules.sourcing import gallery

    rows = (
        (
            await db.execute(
                select(Candidate)
                .where(
                    Candidate.id.in_([uuid.UUID(i) for i in candidate_ids]),
                    Candidate.stage == CandidateStage.CANDIDATE,
                    Candidate.source_url.is_not(None),
                )
                .order_by(Candidate.ai_score.desc().nulls_last())
            )
        )
        .scalars()
        .all()
    )
    out = [c.id for c in rows if detail_state(c) is None and len(gallery.source_urls(c)) < 2]
    return out[:n]


async def after_save(db: AsyncSession, run: SourcingRun) -> None:
    """Sau khi lượt quét / dán link đã commit: lưu ảnh nguồn về kho, tự lấy chi tiết cho vài món điểm cao."""
    from app.core.jobs import enqueue

    if not auto_followups_enabled():
        return
    ids = [str(i) for i in run_progress(run).get("candidate_ids") or []]
    if not ids:
        return
    if run.kind in (RunKind.BRIEF_SCAN, RunKind.SCHEDULED_SCAN, RunKind.IMAGE_SEARCH):
        for cid in await auto_detail_ids(db, ids):
            c = await db.get(Candidate, cid)
            if c is not None and request_details(c):
                await db.commit()
                await enqueue("sourcing.fetch_details", candidate_id=str(cid))
    await cache_candidate_images(db, [uuid.UUID(i) for i in ids])
