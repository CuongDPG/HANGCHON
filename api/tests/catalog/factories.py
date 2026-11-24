"""Dựng nhanh dữ liệu của module khác (chỉ trong test): đề săn hàng, ứng viên, hồ sơ thẩm định, quyết định chọn."""

from __future__ import annotations

import io
import uuid
from datetime import timedelta
from typing import Any

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Language, SourcePlatform
from app.core.timeutil import now_utc
from app.modules.assessment.models import Assessment, AssessmentStatus, ReviewDigest
from app.modules.catalog.models import Category, Product, ProductStatus
from app.modules.selection.models import Decision, SelectionDecision, TrialNote, TrialNoteKind
from app.modules.sourcing.models import BriefStatus, Candidate, CandidateStage, SourcingBrief


def jpeg(w: int = 600, h: int = 800, color: tuple[int, int, int] = (90, 110, 140), *, orientation: int | None = None,
         subject: tuple[int, int, int, int] | None = None) -> bytes:  # fmt: skip
    img = Image.new("RGB", (w, h), (235, 235, 230))
    box = subject or (w // 4, h // 4, 3 * w // 4, 3 * h // 4)
    img.paste(Image.new("RGB", (box[2] - box[0], box[3] - box[1]), color), box[:2])
    buf = io.BytesIO()
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    exif[0x010F] = "Máy ảnh thử"
    img.save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


async def selected_candidate(
    db: AsyncSession,
    *,
    title: str = "Bình giữ nhiệt 480 ml",
    rejected: int = 5,
    tried: int = 2,
    brand: str = "HãngBíMật",
    trial_days: int = 21,
) -> dict[str, Any]:
    """Một đề + 1 ứng viên được chọn + `rejected` ứng viên bị loại (`tried` món đã mua thử). Đã flush."""
    brief = SourcingBrief(title=f"Đề {title} {uuid.uuid4().hex[:4]}", raw_text=title, status=BriefStatus.DONE)
    db.add(brief)
    await db.flush()
    chosen = Candidate(
        brief_id=brief.id, stage=CandidateStage.SELECTED, source_platform=SourcePlatform.RAKUTEN,
        source_external_id=uuid.uuid4().hex, title_vi=title, original_language=Language.JA,
        specs={"Dung tích": "480 ml", "Thương hiệu": brand, "Giữ nóng": "9 giờ"}, weight_grams=310,
        price_vnd_estimate=290_000,
    )  # fmt: skip
    db.add(chosen)
    rej: list[Candidate] = []
    for i in range(rejected):
        c = Candidate(
            brief_id=brief.id, stage=CandidateStage.REJECTED, source_platform=SourcePlatform.TAOBAO,
            source_external_id=uuid.uuid4().hex, title_vi=f"{brand} mẫu {i}",
            specs={"Thương hiệu": f"{brand}{i}", "Giữ nóng": f"{6 + i} giờ"}, seller_name=f"Shop{brand}{i}",
            price_vnd_estimate=200_000 + i * 10_000,
        )  # fmt: skip
        db.add(c)
        rej.append(c)
    await db.flush()
    db.add(Assessment(candidate_id=chosen.id, status=AssessmentStatus.READY, summary="Bình inox giữ nóng 9 giờ.",
                      strengths=["Nắp tháo rời"], weaknesses=["Miệng hẹp"],
                      specs={"Chất liệu": "inox 316"}))  # fmt: skip
    db.add(ReviewDigest(candidate_id=chosen.id, reviews_read=412, language=Language.JA,
                        complaints=[{"point": "Miệng bình hẹp"}], praise=[{"point": "Giữ nóng lâu"}]))  # fmt: skip
    decision = SelectionDecision(
        candidate_id=chosen.id, brief_id=brief.id, decision=Decision.SELECTED, decided_at=now_utc(),
        trial_days=trial_days, reason_selected="Giữ nóng 9 tiếng\nNắp tháo rời", not_satisfied="Miệng hẹp.",
    )  # fmt: skip
    db.add(decision)
    tags = ["ro_nuoc", "ro_nuoc", "bong_son", "hang_nhai", "gia"]
    for i, c in enumerate(rej):
        if i < tried:
            db.add(TrialNote(candidate_id=c.id, kind=TrialNoteKind.TEXT, text=f"{brand}{i} gioăng ám mùi",
                             recorded_at=now_utc() - timedelta(days=3)))  # fmt: skip
        db.add(
            SelectionDecision(
                candidate_id=c.id, brief_id=brief.id, decision=Decision.REJECTED, decided_at=now_utc(),
                rejection_reason=f"Mẫu của {brand}{i} bị rò nước", rejection_tags=[tags[i % len(tags)]],
            )
        )  # fmt: skip
    await db.flush()
    return {"brief": brief, "candidate": chosen, "rejected": rej, "decision": decision}


async def published_product(db: AsyncSession, *, name: str = "Bình giữ nhiệt 480 ml", price: int = 385_000,
                            category: Category | None = None, **kw: Any) -> Product:  # fmt: skip
    from app.modules.catalog import products as svc

    data = await selected_candidate(db, title=name, **kw)
    p = await svc.draft_from_candidate(db, data["candidate"].id, data["decision"].id)
    assert p is not None
    p.price_vnd = price
    p.specs = [{"label": "Dung tích", "value": "480 ml"}]
    p.faq = [{"q": "Giữ lạnh được không?", "a": "Có, 12 tiếng còn lạnh.", "source": "Ghi chú"}]
    if category is not None:
        p.category_id = category.id
    p.status = ProductStatus.PENDING_REVIEW
    await svc.publish(db, p)
    return p


async def category(db: AsyncSession, slug: str = "nha-bep", name: str = "Nhà bếp") -> Category:
    c = Category(slug=slug, name=name)
    db.add(c)
    await db.flush()
    return c
