"""Dữ liệu mẫu cho bàn chọn (ví dụ, không phải dữ liệu thật). Chạy lại không sinh trùng.

uv run python -m app.modules.supply.seed     # chạy cả bàn chọn lẫn nguồn cung
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Language, SourcePlatform
from app.core.timeutil import now_utc
from app.modules.catalog.models import Category
from app.modules.selection import service
from app.modules.selection.models import Decision, DraftStatus, SelectionDecision, TrialNote
from app.modules.sourcing.models import Candidate, CandidateOrigin, CandidateStage, SourcingBrief

MARK = "demo-sel"

BRIEFS = {
    "phoi": ("Đồ phơi, đồ treo gọn cho căn hộ nhỏ", "Tìm giúp chị đồ phơi đồ gấp gọn được, chịu được chăn mùa đông"),
    "mang": ("Hộp cơm, bình nước mang đi làm", "Hộp cơm, bình nước không mùi nhựa, rửa dễ, dưới 300 nghìn"),
}

# (khoá, đề, nhóm hàng, tên, tên gốc, nguồn, giá, tiền tệ, cân nặng g, điểm AI, giai đoạn, số ngày ở giai đoạn)
CANDIDATES: list[tuple[Any, ...]] = [
    (
        "ke-cua",
        "phoi",
        "sap-xep-luu-tru",
        "Kệ treo sau cửa 3 tầng",
        "门后挂架三层",
        SourcePlatform.TAOBAO,
        "42",
        "CNY",
        900,
        78,
        "candidate",
        0,
    ),
    (
        "gia-vi",
        "phoi",
        "nha-bep",
        "Hộp đựng gia vị nam châm",
        "磁吸调料盒",
        SourcePlatform.ALIBABA_1688,
        "9.5",
        "CNY",
        320,
        72,
        "candidate",
        0,
    ),
    (
        "moc-dan",
        "phoi",
        "sap-xep-luu-tru",
        "Móc dán tường chịu lực 10 cái",
        "强力粘钩10个",
        SourcePlatform.TAOBAO,
        "6.8",
        "CNY",
        150,
        64,
        "candidate",
        0,
    ),
    (
        "binh-500",
        "mang",
        "mang-theo",
        "Bình giữ nhiệt 500ml nắp bật",
        "保温杯500ml弹盖",
        SourcePlatform.ALIBABA_1688,
        "26",
        "CNY",
        380,
        70,
        "candidate",
        0,
    ),
    (
        "gio-giat",
        "phoi",
        "phong-tam",
        "Giỏ đựng đồ giặt gấp gọn",
        "折叠脏衣篮",
        SourcePlatform.TAOBAO,
        "19",
        "CNY",
        700,
        81,
        "sample",
        2,
    ),
    (
        "hop-com-3",
        "mang",
        "mang-theo",
        "Hộp cơm inox 3 ngăn",
        "ステンレス弁当箱 3段",
        SourcePlatform.RAKUTEN,
        "2480",
        "JPY",
        520,
        83,
        "sample",
        5,
    ),
    (
        "gia-x",
        "phoi",
        "sap-xep-luu-tru",
        "Giá phơi chữ X",
        "X型晾衣架",
        SourcePlatform.ALIBABA_1688,
        "31",
        "CNY",
        2100,
        86,
        "trial",
        8.4,
    ),
    (
        "khan-be",
        "phoi",
        "phong-tam",
        "Khăn tắm cho bé, mẫu 4",
        "今治 ベビーバスタオル",
        SourcePlatform.AMAZON_JP,
        "1280",
        "JPY",
        180,
        84,
        "trial",
        11.3,
    ),
    (
        "kep-inox",
        "phoi",
        "sap-xep-luu-tru",
        "Kẹp phơi inox 20 cái",
        "不锈钢晾衣夹20个",
        SourcePlatform.ALIBABA_1688,
        "18",
        "CNY",
        600,
        88,
        "selected",
        6,
    ),
    (
        "binh-tt",
        "mang",
        "mang-theo",
        "Bình nước thuỷ tinh vỏ silicon",
        "硅胶套玻璃水杯",
        SourcePlatform.ALIBABA_1688,
        "24",
        "CNY",
        450,
        80,
        "selected",
        1,
    ),
    (
        "binh-tt2",
        "mang",
        "mang-theo",
        "Bình nước thể thao nắp bật",
        "运动水杯弹盖",
        SourcePlatform.PINDUODUO,
        "12",
        "CNY",
        260,
        61,
        "rejected",
        9,
    ),
    (
        "hop-nhua",
        "mang",
        "mang-theo",
        "Hộp cơm nhựa giữ nhiệt",
        "塑料保温饭盒",
        SourcePlatform.TAOBAO,
        "22",
        "CNY",
        600,
        58,
        "rejected",
        12,
    ),
    (
        "gia-bc",
        "phoi",
        "sap-xep-luu-tru",
        "Giá phơi treo ban công",
        "阳台晾衣架",
        SourcePlatform.ALIBABA_1688,
        "36",
        "CNY",
        1800,
        66,
        "rejected",
        15,
    ),
    (
        "thot",
        "mang",
        "nha-bep",
        "Thớt nhựa kháng khuẩn 3 cái",
        "抗菌砧板三件套",
        SourcePlatform.ALIBABA_1688,
        "48",
        "CNY",
        1500,
        63,
        "rejected",
        20,
    ),
]

NOTES: dict[str, list[tuple[float, str]]] = {
    "gia-x": [
        (7.5, "Lắp không cần dụng cụ, chưa tới năm phút. Phơi được hai cái chăn mỏng cùng lúc."),
        (4.2, "Phơi chăn mùa đông không võng. Gấp lại dày 6 cm, dựng sau cửa vừa khít."),
        (1.1, "Chân hơi trượt trên sàn gạch men ướt. Ốc chưa lỏng sau một tuần."),
    ],
    "khan-be": [
        (10.0, "Giặt lần đầu ra ít xơ. Thấm nước nhanh, bé không kêu rát."),
        (6.0, "Sau tám lần giặt vẫn mềm, màu không bạc. Khổ 80 x 80 cm, quấn bé vừa."),
        (2.0, "Phơi trong nhà mùa nồm hơi lâu khô, mất khoảng một ngày."),
    ],
    "kep-inox": [
        (5.5, "Kẹp chắc, gió to không rơi áo. Inox không gỉ sau một tuần để ngoài ban công."),
        (3.0, "Lò xo khoẻ, kẹp được cả chăn dày. Đầu kẹp hơi sắc, phải cẩn thận với áo len."),
    ],
    "binh-tt": [
        (0.8, "Vỏ silicon cầm không trơn, rơi một lần không vỡ. Không có mùi khi đựng nước nóng."),
        (0.3, "Nắp vặn hơi chặt, phải dùng hai tay. Dung tích 450 ml đo thật."),
    ],
    "gio-giat": [(1.0, "Mẫu vừa về: vải dày hơn mình nghĩ, khung gấp gọn được.")],
    "binh-tt2": [(8.0, "Rò nước ở nắp sau ba ngày dùng, ướt cả túi.")],
    "hop-nhua": [(11.0, "Mùi nhựa còn rõ sau ba lần rửa, hâm nóng còn nặng mùi hơn.")],
}

REJECTED = {
    "binh-tt2": ("Rò nước ở nắp sau ba ngày dùng", ["ro_ri"]),
    "hop-nhua": ("Mùi nhựa còn rõ sau nhiều lần rửa", ["mui"]),
    "gia-bc": ("Ốc lỏng, giá lung lay sau một tuần phơi chăn", ["do_ben"]),
    "thot": ("Giá về tay 186 nghìn, đắt hơn hàng trong nước", ["gia"]),
}

SELECTED_APPROVED = {
    "kep-inox": (
        [
            "Kẹp chắc, gió to không rơi áo.",
            "Inox không gỉ sau một tuần để ngoài ban công.",
            "Lò xo khoẻ, kẹp được cả chăn dày.",
        ],
        ["Đầu kẹp hơi sắc, phải cẩn thận với áo len."],
    )
}


async def seed_demo(db: AsyncSession) -> dict[str, int]:
    counts = {"candidates": 0, "notes": 0, "decisions": 0}
    if await db.scalar(select(Candidate.id).where(Candidate.source_external_id.like(f"{MARK}-%")).limit(1)):
        return counts
    cats = dict((await db.execute(select(Category.slug, Category.id))).all())
    briefs: dict[str, SourcingBrief] = {}
    for key, (title, raw) in BRIEFS.items():
        b = SourcingBrief(title=title, raw_text=raw, interpretation=raw)
        db.add(b)
        briefs[key] = b
    await db.flush()

    now = now_utc()
    cands: dict[str, Candidate] = {}
    for i, (key, brief, cat, title, orig, platform, price, cur, weight, score, stage, days) in enumerate(CANDIDATES):
        fx = 172 if cur == "JPY" else 3650
        c = Candidate(
            brief_id=briefs[brief].id, origin=CandidateOrigin.BRIEF_SCAN, stage=CandidateStage(stage),
            stage_changed_at=(now - timedelta(days=days)) if stage != "candidate" else None, board_position=i,
            category_id=cats.get(cat), source_platform=platform, source_external_id=f"{MARK}-{key}",
            source_url=f"https://example.com/{platform.value}/{key}", seller_name="Shop ví dụ",
            original_language=Language.JA if cur == "JPY" else Language.ZH, title_original=orig, title_vi=title,
            price_amount=Decimal(price), price_currency=cur, price_vnd_estimate=int(Decimal(price) * fx),
            weight_grams=weight, ai_score=score, rank_reason="Khớp đề và các nguyên tắc của chị (dữ liệu mẫu).",
        )  # fmt: skip
        db.add(c)
        cands[key] = c
        counts["candidates"] += 1
    await db.flush()

    for key, notes in NOTES.items():
        c = cands[key]
        for ago, text in notes:
            n = await service.create_note(
                db, candidate=c, text=text, kind="voice", user=None, recorded_at=now - timedelta(days=ago)
            )
            if c.stage == CandidateStage.TRIAL and c.stage_changed_at:
                n.trial_day = max(1, int((n.recorded_at - c.stage_changed_at).total_seconds() // 86400) + 1)
            counts["notes"] += 1

    for key, (reason, tags) in REJECTED.items():
        c = cands[key]
        db.add(
            SelectionDecision(
                candidate_id=c.id, brief_id=c.brief_id, decision=Decision.REJECTED, decided_at=c.stage_changed_at,
                rejection_reason=reason, rejection_tags=tags, trial_days=7,
            )
        )  # fmt: skip
        counts["decisions"] += 1
    for key, (reasons, not_ok) in SELECTED_APPROVED.items():
        c = cands[key]
        db.add(
            SelectionDecision(
                candidate_id=c.id, brief_id=c.brief_id, decision=Decision.SELECTED, decided_at=c.stage_changed_at,
                trial_days=14, reason_selected=service.join_lines(reasons), not_satisfied=service.join_lines(not_ok),
                draft_reason_selected=service.join_lines(reasons), draft_not_satisfied=service.join_lines(not_ok),
                draft_status=DraftStatus.APPROVED,
            )
        )  # fmt: skip
        counts["decisions"] += 1
    pending = SelectionDecision(
        candidate_id=cands["binh-tt"].id, brief_id=cands["binh-tt"].brief_id, decision=Decision.SELECTED,
        decided_at=cands["binh-tt"].stage_changed_at, trial_days=12,
    )  # fmt: skip
    db.add(pending)
    await db.flush()
    await service.draft_reasons(db, pending)  # bản nháp chờ chị sửa lời (c3)
    counts["decisions"] += 1

    # c6: học gu từ các quyết định mẫu
    for key in (*REJECTED, *SELECTED_APPROVED, "binh-tt"):
        await service.mark_taste_pending(db, cands[key].id)
    for cat in await service.taste_categories(db):
        await service.retrain_taste(db, cat)
    # một ghi chú nhanh AI chưa xếp được vào món
    db.add(
        TrialNote(kind="voice", text="Hôm nay mưa, chưa thử được món nào.", recorded_at=now, processing_status="done")
    )
    await db.flush()
    return counts
