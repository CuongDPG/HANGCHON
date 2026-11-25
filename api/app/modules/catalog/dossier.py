"""Hồ sơ chọn (e1, e2): đọc bảng của sourcing / assessment / selection / supply (CHỈ ĐỌC) để dựng
ảnh chụp cho sản phẩm: con dấu n/m, dải số sàng lọc, các món đã loại (không nêu thương hiệu), nhóm lý do loại,
và danh sách «dữ kiện» có mã nguồn để AI viết trang mà không thêm điều không có trong dữ liệu."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SourcePlatform
from app.core.timeutil import now_utc
from app.modules.assessment.models import Assessment, AssessmentStatus, ComparisonItem, ReviewDigest
from app.modules.catalog.models import Product
from app.modules.catalog.textutil import normalize_vi
from app.modules.selection.models import Decision, SelectionDecision, TrialNote
from app.modules.sourcing.models import Candidate, CandidateStage
from app.modules.supply.models import PriceProposal, ProposalStatus

ORIGIN_BY_PLATFORM: dict[str, str] = {
    SourcePlatform.ALIBABA_1688: "CN",
    SourcePlatform.TAOBAO: "CN",
    SourcePlatform.TMALL: "CN",
    SourcePlatform.PINDUODUO: "CN",
    SourcePlatform.XIAOHONGSHU: "CN",
    SourcePlatform.RAKUTEN: "JP",
    SourcePlatform.AMAZON_JP: "JP",
    SourcePlatform.COSME: "JP",
    SourcePlatform.TIKTOK_SHOP_VN: "VN",
    SourcePlatform.SHOPEE_VN: "VN",
    SourcePlatform.LAZADA_VN: "VN",
    SourcePlatform.TIKI: "VN",
}

COUNTRY_LABELS = {"JP": "Nhật", "CN": "Trung Quốc", "KR": "Hàn Quốc", "VN": "Việt Nam", "US": "Mỹ", "TW": "Đài Loan"}

LANGUAGE_LABELS = {"zh": "tiếng Trung", "ja": "tiếng Nhật", "en": "tiếng Anh", "ko": "tiếng Hàn", "vi": "tiếng Việt"}

# Nhãn tiếng Việt cho thẻ lý do loại (c4). Thẻ lạ thì đổi gạch dưới thành khoảng trắng.
REJECT_TAG_LABELS = {
    "ro_nuoc": "Rò nước",
    "bong_son": "Bong sơn",
    "hang_nhai": "Nghi hàng nhái",
    "danh_gia_ao": "Đánh giá ảo",
    "chat_lieu": "Chất liệu",
    "mui": "Ám mùi",
    "am_mui": "Ám mùi",
    "do_ben": "Kém bền",
    "gia": "Giá cao",
    "nang": "Nặng",
    "kho_dung": "Khó dùng",
    "kho_ve_sinh": "Khó vệ sinh",
    "an_toan": "An toàn",
    "van_chuyen": "Khó vận chuyển",
    "tham_my": "Thẩm mỹ",
    "kich_thuoc": "Kích thước",
}

_BRAND_KEYS = ("thuong hieu", "hang sx", "hang san xuat", "nha san xuat", "brand", "nhan hieu", "xuat xu thuong hieu")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def country_of(candidate: Candidate) -> str | None:
    return ORIGIN_BY_PLATFORM.get(candidate.source_platform)


def tag_label(tag: str) -> str:
    return REJECT_TAG_LABELS.get(tag, tag.replace("_", " ").strip().capitalize() or "Lý do khác")


def _flat(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return ", ".join(f"{k}: {_flat(v)}" for k, v in value.items())
    if isinstance(value, list):
        return ", ".join(_flat(v) for v in value)
    return str(value).strip()


def _is_brand_key(key: str) -> bool:
    k = normalize_vi(key)
    return any(b in k for b in _BRAND_KEYS)


def brand_terms(candidate: Candidate, assessment: Assessment | None) -> list[str]:
    """Những chữ có thể là tên thương hiệu / shop: không được hiện ở món bị loại."""
    terms: list[str] = []
    for specs in (candidate.specs or {}, (assessment.specs if assessment else None) or {}):
        for k, v in specs.items():
            if _is_brand_key(str(k)) and _flat(v):
                terms.append(_flat(v))
    if candidate.seller_name:
        terms.append(candidate.seller_name)
    return [t for t in terms if len(t) >= 2]


def scrub(text: str | None, terms: list[str]) -> str | None:
    if not text:
        return text
    out = text
    for t in sorted(terms, key=len, reverse=True):
        out = re.sub(re.escape(t), "mẫu này", out, flags=re.IGNORECASE)
    return out


def spec_pairs(candidate: Candidate, assessment: Assessment | None) -> list[tuple[str, str, str]]:
    """(nhãn, giá trị, mã nguồn) — ưu tiên thông số đã chuẩn hoá của hồ sơ thẩm định; bỏ dòng thương hiệu."""
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for source, specs in (("assessment.specs", (assessment.specs if assessment else None) or {}),
                          ("candidate.specs", candidate.specs or {})):  # fmt: skip
        for k, v in specs.items():
            label, value = str(k).strip(), _flat(v)
            if not label or not value or _is_brand_key(label) or normalize_vi(label) in seen:
                continue
            seen.add(normalize_vi(label))
            out.append((label, value, f"{source}:{label}"))
    return out


async def latest_decisions(db: AsyncSession, candidate_ids: list[uuid.UUID]) -> dict[uuid.UUID, SelectionDecision]:
    if not candidate_ids:
        return {}
    rows = (
        await db.execute(
            select(SelectionDecision)
            .where(SelectionDecision.candidate_id.in_(candidate_ids))
            .order_by(SelectionDecision.candidate_id, SelectionDecision.decided_at.desc())
        )
    ).scalars()
    out: dict[uuid.UUID, SelectionDecision] = {}
    for d in rows:
        out.setdefault(d.candidate_id, d)
    return out


async def approved_price(db: AsyncSession, candidate_id: uuid.UUID) -> PriceProposal | None:
    return (
        await db.execute(
            select(PriceProposal)
            .where(PriceProposal.candidate_id == candidate_id, PriceProposal.status == ProposalStatus.APPROVED)
            .order_by(PriceProposal.decided_at.desc().nulls_last(), PriceProposal.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


@dataclass
class Fact:
    ref: str
    label: str
    text: str

    def as_dict(self) -> dict[str, str]:
        return {"ref": self.ref, "label": self.label, "text": self.text}


@dataclass
class Snapshot:
    candidate: Candidate
    assessment: Assessment | None
    decision: SelectionDecision | None
    considered_count: int
    selected_count: int
    trial_days: int | None
    reason_selected: str | None
    not_satisfied: str | None
    origin_country: str | None
    rejected_alternatives: list[dict[str, Any]]
    dossier: dict[str, Any]
    facts: list[Fact] = field(default_factory=list)
    price: PriceProposal | None = None


async def build_snapshot(db: AsyncSession, candidate: Candidate, decision_id: uuid.UUID | None = None) -> Snapshot:
    assessment = (
        await db.execute(select(Assessment).where(Assessment.candidate_id == candidate.id))
    ).scalar_one_or_none()
    decision: SelectionDecision | None = None
    if decision_id:
        decision = await db.get(SelectionDecision, decision_id)
    if decision is None:
        decision = (await latest_decisions(db, [candidate.id])).get(candidate.id)

    # cùng đề săn hàng → mẫu số của con dấu
    if candidate.brief_id:
        peers = list(
            (
                await db.execute(
                    select(Candidate).where(Candidate.brief_id == candidate.brief_id).order_by(Candidate.created_at)
                )
            ).scalars()
        )
    else:
        peers = [candidate]
    if candidate not in peers:
        peers.append(candidate)
    ids = [c.id for c in peers]
    assessments = {
        a.candidate_id: a
        for a in (await db.execute(select(Assessment).where(Assessment.candidate_id.in_(ids)))).scalars()
    }
    compared_ids = {cid for cid, a in assessments.items() if a.status == AssessmentStatus.READY}
    compared_ids |= set(
        (await db.execute(select(ComparisonItem.candidate_id).where(ComparisonItem.candidate_id.in_(ids)))).scalars()
    )
    noted_ids = set(
        (
            await db.execute(
                select(TrialNote.candidate_id).where(TrialNote.candidate_id.in_(ids)).group_by(TrialNote.candidate_id)
            )
        ).scalars()
    )
    decisions = await latest_decisions(db, ids)
    tried_ids = {
        c.id for c in peers if c.stage in (CandidateStage.SAMPLE, CandidateStage.TRIAL, CandidateStage.SELECTED)
    }
    tried_ids |= noted_ids
    tried_ids |= {cid for cid, d in decisions.items() if d.trial_days}
    selected_count = max(1, sum(1 for c in peers if c.stage == CandidateStage.SELECTED or c.id == candidate.id))
    compared_ids |= tried_ids

    digests = list((await db.execute(select(ReviewDigest).where(ReviewDigest.candidate_id.in_(ids)))).scalars())
    reviews_read = sum(d.reviews_read or 0 for d in digests)
    languages = sorted({LANGUAGE_LABELS.get(str(d.language), str(d.language)) for d in digests if d.language})

    # các món đã loại: tried trước, rồi so kỹ, rồi vòng đọc đánh giá
    rejected = [c for c in peers if c.stage == CandidateStage.REJECTED and c.id != candidate.id]
    groups: Counter[str] = Counter()
    alternatives: list[dict[str, Any]] = []
    letters = iter("BCDEFGHIJKLMNOPQRSTUVWXYZ")
    order = sorted(rejected, key=lambda c: (c.id not in tried_ids, c.id not in compared_ids, c.created_at))
    for c in order:
        d = decisions.get(c.id)
        tags = [str(t) for t in (d.rejection_tags if d else [])] or ["khac"]
        groups[tags[0]] += 1
        if d is None or not d.show_on_profile:
            continue
        if c.id not in tried_ids and c.id not in compared_ids:
            continue  # loại từ vòng đọc đánh giá: chỉ đếm vào nhóm lý do
        a = assessments.get(c.id)
        terms = brand_terms(c, a)
        letter = next(letters, None)
        if letter is None:
            break
        alternatives.append(
            {
                "label": f"Mẫu {letter}",
                "origin": COUNTRY_LABELS.get(country_of(c) or "", None),
                "price_vnd": c.price_vnd_estimate,
                "summary": " · ".join(f"{k} {v}" for k, v, _ in spec_pairs(c, a)[:3]) or None,
                "reason": scrub(d.rejection_reason, terms),
                "tags": [tag_label(t) for t in tags if t != "khac"],
                "stage": "tried" if c.id in tried_ids else "compared",
            }
        )
    screened_out = sum(1 for c in rejected if c.id not in tried_ids and c.id not in compared_ids)
    reject_groups = [
        {"key": k, "label": "Lý do khác" if k == "khac" else tag_label(k), "count": n}
        for k, n in sorted(groups.items(), key=lambda kv: (kv[0] == "khac", -kv[1]))
    ]

    reason = (decision.reason_selected or decision.draft_reason_selected) if decision else None
    not_ok = (decision.not_satisfied or decision.draft_not_satisfied) if decision else None
    snap = Snapshot(
        candidate=candidate,
        assessment=assessment,
        decision=decision,
        considered_count=len(peers),
        selected_count=selected_count,
        trial_days=decision.trial_days if decision else None,
        reason_selected=reason,
        not_satisfied=not_ok,
        origin_country=country_of(candidate),
        rejected_alternatives=alternatives,
        dossier={
            "funnel": {
                "viewed": len(peers),
                "compared": len(compared_ids),
                "tried": len(tried_ids),
                "selected": selected_count,
            },
            "reject_groups": reject_groups,
            "screened_out": screened_out,
            "reviews_read": reviews_read,
            "review_languages": languages,
            "built_at": now_utc().isoformat(),
        },
        price=await approved_price(db, candidate.id),
    )
    snap.facts = await collect_facts(db, snap)
    return snap


async def collect_facts(db: AsyncSession, snap: Snapshot) -> list[Fact]:
    """Dữ kiện có mã nguồn — thứ duy nhất AI được dùng để viết trang sản phẩm."""
    c, a, d = snap.candidate, snap.assessment, snap.decision
    facts: list[Fact] = [Fact("candidate.title", "Tên món (bản dịch)", c.title_vi)]
    if c.description_vi:
        facts.append(Fact("candidate.description", "Mô tả từ nguồn (đã dịch)", c.description_vi[:2000]))
    for label, value, _ref in spec_pairs(c, a):
        facts.append(Fact(f"spec:{label}", f"Thông số · {label}", value))
    if c.weight_grams:
        facts.append(Fact("spec:Khối lượng", "Thông số · Khối lượng", f"{c.weight_grams} g"))
    if a:
        if a.summary:
            facts.append(Fact("assessment.summary", "Hồ sơ thẩm định · Tóm tắt", a.summary))
        for i, s in enumerate(a.strengths or []):
            facts.append(Fact(f"assessment.strengths:{i}", "Hồ sơ thẩm định · Điểm mạnh", _flat(s)))
        for i, s in enumerate(a.weaknesses or []):
            facts.append(Fact(f"assessment.weaknesses:{i}", "Hồ sơ thẩm định · Điểm yếu", _flat(s)))
        for k, v in (a.safety or {}).items():
            if _flat(v):
                facts.append(Fact(f"assessment.safety:{k}", f"An toàn · {k}", _flat(v)))
    if snap.reason_selected:
        facts.append(Fact("decision.reason_selected", "Vì sao mình chọn", snap.reason_selected))
    if snap.not_satisfied:
        facts.append(Fact("decision.not_satisfied", "Điều mình chưa ưng", snap.not_satisfied))
    if snap.trial_days:
        facts.append(Fact("decision.trial_days", "Thời gian thử", f"{snap.trial_days} ngày"))
    if d is not None and d.decision == Decision.SELECTED and snap.considered_count:
        facts.append(Fact("decision.seal", "Con dấu", f"Chọn {snap.selected_count} trong {snap.considered_count} mẫu"))
    digests = (await db.execute(select(ReviewDigest).where(ReviewDigest.candidate_id == c.id))).scalars()
    for dg in digests:
        for i, p in enumerate(dg.praise or []):
            point = p.get("point") if isinstance(p, dict) else _flat(p)
            if point:
                facts.append(Fact(f"reviews.praise:{dg.id}:{i}", "Người mua khen", str(point)))
        for i, p in enumerate(dg.complaints or []):
            point = p.get("point") if isinstance(p, dict) else _flat(p)
            if point:
                facts.append(Fact(f"reviews.complaints:{dg.id}:{i}", "Người mua chê", str(point)))
    notes = (
        await db.execute(
            select(TrialNote.text)
            .where(TrialNote.candidate_id == c.id, TrialNote.text.is_not(None))
            .order_by(TrialNote.recorded_at)
            .limit(12)
        )
    ).scalars()
    for i, t in enumerate(notes):
        if t:
            facts.append(Fact(f"trial_notes:{i}", "Ghi chú thử hàng của người chọn", t[:600]))
    return facts


# ---- kiểm chứng nội dung AI viết ---------------------------------------------------------------------------------

OVERCLAIM_WORDS = (
    "tot nhat", "so 1", "so mot", "than thanh", "chua benh", "chua khoi", "tri benh", "diet khuan",
    "khang khuan", "cam ket 100", "vinh vien", "tuyet doi an toan", "dieu tri",
)  # fmt: skip


def numbers_in(text: str | None) -> set[str]:
    return {n.replace(",", ".") for n in _NUMBER.findall(text or "")}


def unsupported_numbers(text: str | None, sources: list[str]) -> set[str]:
    """Số có trong `text` mà không có trong nguồn (dấu hiệu AI bịa số liệu)."""
    have: set[str] = set()
    for s in sources:
        have |= numbers_in(s)
    return {n for n in numbers_in(text) if n not in have}


def overclaims(text: str | None) -> list[str]:
    t = normalize_vi(text)
    return [w for w in OVERCLAIM_WORDS if w in t]


async def count_candidates(db: AsyncSession) -> tuple[int, int]:
    """(số ứng viên đã xem, số được chọn) — cho trang Về người chọn."""
    total = (await db.execute(select(func.count()).select_from(Candidate))).scalar_one()
    chosen = (await db.execute(select(func.count()).where(Candidate.stage == CandidateStage.SELECTED))).scalar_one()
    return total, chosen


async def dossier_view(db: AsyncSession, p: Product) -> dict[str, Any]:
    """Hồ sơ chọn đầy đủ cho desk (e2): dải số sàng lọc, món được chọn cạnh các món đã loại, nhóm lý do loại.
    Là dữ liệu theo dõi nội bộ — không có route công khai nào trả về."""
    # nhập muộn: products/public cùng nhập module này
    from app.modules.catalog.products import image_set, primary_image
    from app.modules.catalog.public import bullets, setting

    d = p.dossier or {}
    img = primary_image(p)
    return {
        "product": {
            "slug": p.slug,
            "name": p.name,
            "price_vnd": p.price_vnd,
            "origin": COUNTRY_LABELS.get(p.origin_country or "", p.origin_country),
            "summary": " · ".join(f"{s.get('label')} {s.get('value')}" for s in p.specs[:3] if isinstance(s, dict)),
            "image": image_set(img) if img else None,
            "seal": {"chosen": p.selected_count, "total": p.considered_count},
            "trial_days": p.trial_days,
            "reason_selected": bullets(p.reason_selected),
            "not_satisfied": p.not_satisfied,
        },
        "funnel": d.get("funnel") or {"viewed": p.considered_count, "selected": p.selected_count},
        "alternatives": p.rejected_alternatives,
        "reject_groups": d.get("reject_groups", []),
        "screened_out": d.get("screened_out", 0),
        "reviews_read": d.get("reviews_read", 0),
        "review_languages": d.get("review_languages", []),
        "picker_name": await setting(db, "store.picker_name"),
    }
