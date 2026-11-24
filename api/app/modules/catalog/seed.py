"""Dữ liệu mẫu cho website: `uv run python -m app.modules.catalog.seed` (chạy lại không sinh trùng).

7 món gia dụng nhỏ, mỗi món có đề săn hàng + ứng viên bị loại (kèm lý do) + quyết định chọn + hồ sơ thẩm định,
một đợt đang mở, một đợt sắp mở, một đợt đã về (kèm đơn và đánh giá), vài yêu cầu Nhờ chị tìm.
Tên món, tên người, số liệu đều là VÍ DỤ. Ảnh mẫu sinh bằng Pillow (khối màu có tên món), không tải từ mạng.

Ghi chú: để có hồ sơ chọn thật, seed này ghi cả vào bảng của sourcing / assessment / selection / orders —
chỉ dùng cho dữ liệu demo, không phải luồng chạy thật (luồng thật đi qua sự kiện)."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Language, SourcePlatform
from app.core.timeutil import now_utc
from app.modules.assessment.models import Assessment, AssessmentStatus, ReviewDigest
from app.modules.catalog import images as img_lib
from app.modules.catalog import products as product_svc
from app.modules.catalog.models import (
    Category,
    Drop,
    DropItem,
    DropReminder,
    DropStatus,
    FindRequest,
    FindRequestStatus,
    Product,
    ProductStatus,
    Review,
    ReviewStatus,
)
from app.modules.catalog.textutil import hash_key
from app.modules.selection.models import (
    Decision,
    PrincipleKind,
    SelectionDecision,
    SelectionPrinciple,
    TrialNote,
    TrialNoteKind,
)
from app.modules.sourcing.models import BriefStatus, Candidate, CandidateStage, SourcingBrief

log = logging.getLogger("app.catalog.seed")

EXTRA_CATEGORIES = [("cho-be", "Cho bé", 5), ("ban-lam-viec", "Bàn làm việc", 6)]

EXTRA_PRINCIPLES = [
    ("prefer", "Đọc đánh giá xấu trước, rồi mới đọc lời khen"),
    ("must", "Mua mẫu bằng tiền của mình, dùng thật ít nhất 2 tuần"),
    ("must", "Nói rõ điều chưa ưng trên trang sản phẩm"),
]

# (tag, lý do) cho các mẫu bị loại từ vòng đọc đánh giá
SCREEN_REASONS = [
    ("ro_nuoc", "Nhiều đánh giá 1 sao kể rò nước ở nắp"),
    ("bong_son", "Ảnh người mua thấy bong sơn sau vài tuần"),
    ("hang_nhai", "Cùng ảnh với shop khác nhưng giá thấp bất thường"),
    ("danh_gia_ao", "Đánh giá dồn trong vài ngày, câu chữ giống nhau"),
    ("do_ben", "Người mua kể hỏng sau 1–2 tháng"),
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "key": "binh-giu-nhiet",
        "brief": "Bình giữ nhiệt nhẹ, giữ nóng lâu, nắp tháo rửa được",
        "category": "mang-theo",
        "platform": SourcePlatform.RAKUTEN,
        "title": "Bình giữ nhiệt 480 ml",
        "color": (74, 98, 120),
        "considered": 24,
        "trial_days": 21,
        "price": 385_000,
        "price_src": 290_000,
        "weight": 310,
        "specs": {"Dung tích": "480 ml", "Chất liệu thân": "inox 316", "Khối lượng": "310 g", "Giữ nóng": "9 giờ"},
        "reason": "Giữ nóng 9 tiếng, mình đo 3 lần\nNắp tháo rời từng phần, rửa xong không ám mùi\n"
        "Nhẹ hơn 60 g so với mẫu bán chạy nhất mình mua thử",
        "not_ok": "Chỉ có 2 màu. Miệng bình hẹp, khó cho đá viên to.",
        "summary": "Bình inox 316 hai lớp, giữ nóng khoảng 9 giờ theo lần đo của chị, nắp tháo rời được.",
        "strengths": ["Giữ nhiệt ổn định qua 3 lần đo", "Nắp tháo rời, gioăng silicon thay được"],
        "weaknesses": ["Miệng hẹp, khó cho đá viên to", "Chỉ 2 màu"],
        "subtitle": "Nhật Bản · inox 316 · 310 g",
        "faq": [
            ("Bình có giữ lạnh được không?", "Có. Chị thử nước đá, sau 12 tiếng vẫn còn lạnh, đá tan gần hết."),
            ("Có đựng đồ uống có ga được không?", "Hướng dẫn của nhà sản xuất ghi không dùng cho đồ uống có ga."),
        ],
        "tried": [
            ("Giữ nóng 7 giờ", "340 g", 210_000, "Gioăng ám mùi sau 1 tuần dùng.", ["am_mui"]),
            ("Giữ nóng 10 giờ", "420 g", 520_000, "Nặng, đắt hơn 35% mà chỉ giữ nóng hơn 1 giờ.", ["nang", "gia"]),
        ],
        "compared": [("Giữ nóng 8 giờ", "360 g", 260_000, "Nắp liền, không tháo ra rửa được.", ["kho_ve_sinh"])],
        "reviews_read": 412,
    },
    {
        "key": "hop-com-inox",
        "brief": "Hộp cơm inox nhiều ngăn, kín, không ám mùi, cho dân văn phòng",
        "category": "nha-bep",
        "platform": SourcePlatform.TAOBAO,
        "title": "Hộp cơm inox 3 ngăn",
        "color": (150, 140, 120),
        "considered": 17,
        "trial_days": 14,
        "price": 245_000,
        "price_src": 160_000,
        "weight": 520,
        "specs": {
            "Dung tích": "1,1 lít (3 ngăn)",
            "Chất liệu": "inox 304",
            "Khối lượng": "520 g",
            "Nắp": "gioăng silicon",
        },
        "reason": "Ba ngăn tách rời, canh không tràn sang cơm\nInox 304 dày, hai tuần không ám mùi cá\n"
        "Gài nắp bốn phía, lắc mạnh không đổ",
        "not_ok": "Hơi nặng khi mang cả ba ngăn. Không dùng được lò vi sóng (là inox).",
        "summary": "Hộp inox 304 ba ngăn tách rời, nắp gài bốn phía kín nước.",
        "strengths": ["Kín nước khi lắc", "Ba ngăn tách rời"],
        "weaknesses": ["Không dùng lò vi sóng", "Khá nặng"],
        "subtitle": "Trung Quốc · inox 304 · 520 g",
        "faq": [("Có cho vào lò vi sóng được không?", "Không, vì là inox. Bạn hâm bằng nồi hấp hoặc đổ ra bát.")],
        "tried": [("4 ngăn", "690 g", 190_000, "Bốn ngăn thì ngăn nào cũng nhỏ, nắp giữa hay kênh.", ["kho_dung"])],
        "compared": [("2 ngăn nhựa", "300 g", 120_000, "Nhựa ám mùi sau vài lần đựng cá kho.", ["am_mui"])],
        "reviews_read": 268,
    },
    {
        "key": "khan-tam-be",
        "brief": "Khăn tắm cho bé mềm, thấm nhanh, giặt nhiều lần không xơ",
        "category": "cho-be",
        "platform": SourcePlatform.AMAZON_JP,
        "title": "Khăn tắm cho bé",
        "color": (210, 196, 170),
        "considered": 31,
        "trial_days": 35,
        "price": 168_000,
        "price_src": 110_000,
        "weight": 240,
        "specs": {"Kích thước": "60 x 120 cm", "Chất liệu": "cotton sợi xoắn", "Khối lượng": "240 g"},
        "reason": "Qua 30 lần giặt máy vẫn mềm, không xơ\nThấm nước nhanh hơn hai mẫu cùng giá\nMép may kép, không bung chỉ",
        "not_ok": "Phơi lâu khô hơn khăn mỏng vào ngày nồm.",
        "summary": "Khăn cotton sợi xoắn, chị giặt máy 30 lần để kiểm độ bền.",
        "strengths": ["Giữ mềm sau 30 lần giặt", "Mép may kép"],
        "weaknesses": ["Lâu khô ngày nồm"],
        "subtitle": "Nhật Bản · cotton · 60 x 120 cm",
        "faq": [("Giặt máy được không?", "Được. Chị giặt máy 30 lần, chế độ thường, nước ấm.")],
        "tried": [("60 x 120 cm", "260 g", 150_000, "Xơ sợi sau 10 lần giặt.", ["do_ben"])],
        "compared": [("70 x 140 cm", "300 g", 230_000, "Mùi hoá chất còn sau lần giặt đầu.", ["chat_lieu"])],
        "reviews_read": 530,
    },
    {
        "key": "den-kep",
        "brief": "Đèn kẹp đọc sách gọn, ánh sáng dịu, kẹp chắc vào bàn mỏng",
        "category": "ban-lam-viec",
        "platform": SourcePlatform.ALIBABA_1688,
        "title": "Đèn kẹp đọc sách",
        "color": (60, 64, 76),
        "considered": 12,
        "trial_days": 14,
        "price": 219_000,
        "price_src": 130_000,
        "weight": 280,
        "specs": {"Nguồn": "cắm USB", "Nhiệt độ màu": "3 mức", "Độ mở kẹp": "tối đa 5 cm", "Khối lượng": "280 g"},
        "reason": "Kẹp chắc vào mép bàn 2 cm, không trượt\nÁnh sáng 3 mức, mức dịu không chói mắt\nCổ đèn uốn được, giữ nguyên vị trí",
        "not_ok": "Dây USB ngắn (1,2 m). Không có pin, phải cắm điện.",
        "summary": "Đèn kẹp cắm USB, 3 mức sáng, cổ uốn giữ vị trí.",
        "strengths": ["Kẹp chắc", "Ánh sáng dịu"],
        "weaknesses": ["Dây ngắn"],
        "subtitle": "Trung Quốc · cắm USB · 280 g",
        "faq": [("Đèn có pin không?", "Không. Đèn cắm USB, dây dài 1,2 m.")],
        "tried": [("có pin", "310 g", 180_000, "Có pin sạc, chưa nhập được ở giai đoạn này.", ["van_chuyen"])],
        "compared": [],
        "reviews_read": 190,
    },
    {
        "key": "gia-phoi",
        "brief": "Giá phơi gấp gọn cho ban công nhỏ, chắc, không gỉ",
        "category": "sap-xep-luu-tru",
        "platform": SourcePlatform.TAOBAO,
        "title": "Giá phơi gấp gọn",
        "color": (176, 180, 186),
        "considered": 15,
        "trial_days": 21,
        "price": 329_000,
        "price_src": 210_000,
        "weight": 1900,
        "specs": {
            "Kích thước mở": "90 x 55 cm",
            "Chất liệu": "thép sơn tĩnh điện",
            "Khối lượng": "1,9 kg",
            "Tải": "15 kg",
        },
        "reason": "Gấp lại dày 6 cm, nhét được sau cửa\nPhơi đủ một mẻ máy giặt 7 kg\nSau 3 tuần ngoài ban công chưa thấy gỉ",
        "not_ok": "Chân hơi trơn trên gạch men ướt, mình phải lót miếng cao su.",
        "summary": "Giá thép sơn tĩnh điện, gấp gọn, chịu tải khoảng 15 kg.",
        "strengths": ["Gấp mỏng", "Chưa gỉ sau 3 tuần"],
        "weaknesses": ["Chân trơn trên gạch ướt"],
        "subtitle": "Trung Quốc · thép sơn · 1,9 kg",
        "faq": [("Để ngoài mưa được không?", "Chị để ban công có mái 3 tuần chưa gỉ; chưa thử để dầm mưa.")],
        "tried": [("inox mỏng", "1,4 kg", 190_000, "Ống mỏng, phơi chăn bị võng.", ["do_ben"])],
        "compared": [("nhôm", "1,2 kg", 420_000, "Đắt gần gấp đôi mà không gấp gọn hơn.", ["gia"])],
        "reviews_read": 240,
    },
    {
        "key": "hop-gia-vi",
        "brief": "Hộp gia vị nắp lật, một tay mở được, không vón ẩm",
        "category": "nha-bep",
        "platform": SourcePlatform.RAKUTEN,
        "title": "Hộp gia vị nắp lật",
        "color": (196, 204, 190),
        "considered": 19,
        "trial_days": 14,
        "price": 129_000,
        "price_src": 80_000,
        "weight": 150,
        "specs": {"Dung tích": "350 ml", "Chất liệu": "nhựa PP, nắp có gioăng", "Khối lượng": "150 g"},
        "reason": "Nắp lật một tay, rắc hoặc múc đều được\nGioăng kín, hai tuần mùa nồm đường không vón",
        "not_ok": "Thìa kèm theo hơi nhỏ.",
        "summary": "Hộp PP nắp lật có gioăng, hai chế độ rắc và múc.",
        "strengths": ["Một tay mở được", "Kín ẩm"],
        "weaknesses": ["Thìa nhỏ"],
        "subtitle": "Nhật Bản · nhựa PP · 350 ml",
        "faq": [("Rửa máy rửa bát được không?", "Thân hộp được, nắp có gioăng nên rửa tay sẽ bền hơn.")],
        "tried": [("thuỷ tinh", "380 g", 150_000, "Nắp vặn, phải dùng hai tay.", ["kho_dung"])],
        "compared": [],
        "reviews_read": 156,
    },
    {
        "key": "tui-luoi-giat",
        "brief": "Túi lưới giặt đồ bền khoá kéo, giữ form áo",
        "category": "phong-tam",
        "platform": SourcePlatform.AMAZON_JP,
        "title": "Túi lưới giặt đồ (bộ 3)",
        "color": (226, 228, 232),
        "considered": 9,
        "trial_days": 21,
        "price": 99_000,
        "price_src": 60_000,
        "weight": 120,
        "specs": {"Bộ": "3 cỡ (S, M, L)", "Chất liệu": "lưới polyester dày", "Khoá": "có nắp che đầu khoá"},
        "reason": "Đầu khoá có nắp che, không móc vào áo len\nLưới dày, giặt 3 tuần chưa rách",
        "not_ok": "Cỡ L hơi chật cho chăn mỏng.",
        "summary": "Bộ 3 túi lưới dày, đầu khoá có nắp che.",
        "strengths": ["Nắp che đầu khoá"],
        "weaknesses": ["Cỡ L chật cho chăn"],
        "subtitle": "Nhật Bản · polyester · bộ 3 cỡ",
        "faq": [],
        "tried": [("lưới mỏng", "90 g", 45_000, "Khoá kéo bung sau 5 lần giặt.", ["do_ben"])],
        "compared": [],
        "reviews_read": 98,
    },
]


async def _categories(db: AsyncSession) -> dict[str, Category]:
    cats = {c.slug: c for c in (await db.execute(select(Category))).scalars()}
    base = [("nha-bep", "Nhà bếp"), ("phong-tam", "Phòng tắm"), ("sap-xep-luu-tru", "Sắp xếp, lưu trữ"),
            ("mang-theo", "Đồ mang theo")]  # fmt: skip
    for i, (slug, name) in enumerate(base):
        if slug not in cats:
            cats[slug] = Category(slug=slug, name=name, position=i)
            db.add(cats[slug])
    for slug, name, pos in EXTRA_CATEGORIES:
        if slug not in cats:
            cats[slug] = Category(slug=slug, name=name, position=pos)
            db.add(cats[slug])
    await db.flush()
    return cats


def _cand(
    brief: SourcingBrief, spec: dict[str, Any], n: int, *, title: str, stage: CandidateStage, **kw: Any
) -> Candidate:
    return Candidate(
        brief_id=brief.id,
        stage=stage,
        stage_changed_at=now_utc(),
        category_id=brief.category_id,
        source_platform=spec["platform"],
        source_external_id=f"demo-{spec['key']}-{n}",
        source_url=f"https://example.com/demo/{spec['key']}/{n}",
        original_language=Language.JA
        if spec["platform"] in (SourcePlatform.RAKUTEN, SourcePlatform.AMAZON_JP)
        else Language.ZH,
        title_vi=title,
        **kw,
    )


async def _seed_product(
    db: AsyncSession, spec: dict[str, Any], cats: dict[str, Category], rng: random.Random
) -> Product | None:
    exists = (await db.execute(select(SourcingBrief).where(SourcingBrief.title == spec["brief"]))).scalar_one_or_none()
    if exists:
        return None
    cat = cats[spec["category"]]
    brief = SourcingBrief(title=spec["brief"], raw_text=spec["brief"], status=BriefStatus.DONE, category_id=cat.id)
    db.add(brief)
    await db.flush()
    now = now_utc()
    chosen = _cand(brief, spec, 0, title=spec["title"], stage=CandidateStage.SELECTED, specs=spec["specs"],
                   weight_grams=spec["weight"], price_vnd_estimate=spec["price_src"],
                   seller_name="Cửa hàng ví dụ A")  # fmt: skip
    db.add(chosen)
    rejected: list[tuple[Candidate, str, list[str], bool]] = []
    n = 1
    for k, (s1, s2, price, reason, tags) in enumerate(spec["tried"]):
        c = _cand(brief, spec, n, title=f"{spec['title']} mẫu thử {k + 1}", stage=CandidateStage.REJECTED,
                  specs={"Thương hiệu": f"Hãng ví dụ {k + 1}", "Đặc điểm": s1, "Khối lượng": s2},
                  price_vnd_estimate=price, seller_name=f"Hãng ví dụ {k + 1}")  # fmt: skip
        db.add(c)
        rejected.append((c, reason, tags, True))
        n += 1
    for s1, s2, price, reason, tags in spec["compared"]:
        c = _cand(brief, spec, n, title=f"{spec['title']} so kỹ {n}", stage=CandidateStage.REJECTED,
                  specs={"Đặc điểm": s1, "Khối lượng": s2}, price_vnd_estimate=price)  # fmt: skip
        db.add(c)
        rejected.append((c, reason, tags, False))
        n += 1
    while n < spec["considered"]:
        tag, reason = SCREEN_REASONS[rng.randrange(len(SCREEN_REASONS))]
        c = _cand(brief, spec, n, title=f"{spec['title']} ứng viên {n}", stage=CandidateStage.REJECTED,
                  specs={"Thương hiệu": f"Hãng ví dụ {n}"})  # fmt: skip
        db.add(c)
        rejected.append((c, reason, [tag], False))
        n += 1
    await db.flush()

    db.add(
        Assessment(
            candidate_id=chosen.id, status=AssessmentStatus.READY, summary=spec["summary"], strengths=spec["strengths"],
            weaknesses=spec["weaknesses"], specs=spec["specs"], generated_at=now,
        )
    )  # fmt: skip
    db.add(
        ReviewDigest(
            candidate_id=chosen.id, language=Language.JA if "Nhật" in spec["subtitle"] else Language.ZH,
            reviews_read=spec["reviews_read"], rating_avg=Decimal("4.5"),
            praise=[{"point": spec["strengths"][0], "count": 40}],
            complaints=[{"point": spec["weaknesses"][0], "count": 12}],
        )
    )  # fmt: skip
    trial_ids = {c.id for c, _, _, tried in rejected if tried}
    for c, _, _, _ in rejected:
        if c.id in trial_ids or c.specs.get("Đặc điểm"):
            db.add(Assessment(candidate_id=c.id, status=AssessmentStatus.READY, summary="Hồ sơ thẩm định mẫu"))
    for i, line in enumerate(spec["reason"].splitlines()):
        db.add(TrialNote(candidate_id=chosen.id, kind=TrialNoteKind.TEXT, text=line, recorded_at=now - timedelta(days=10 - i),
                         trial_day=i + 1))  # fmt: skip
    for c, reason, _, tried in rejected:
        if tried:
            db.add(
                TrialNote(candidate_id=c.id, kind=TrialNoteKind.TEXT, text=reason, recorded_at=now - timedelta(days=12))
            )
    decision = SelectionDecision(
        candidate_id=chosen.id, brief_id=brief.id, decision=Decision.SELECTED, decided_at=now - timedelta(days=3),
        trial_days=spec["trial_days"], reason_selected=spec["reason"], not_satisfied=spec["not_ok"],
    )  # fmt: skip
    db.add(decision)
    for c, reason, tags, tried in rejected:
        db.add(
            SelectionDecision(
                candidate_id=c.id, brief_id=brief.id, decision=Decision.REJECTED, decided_at=now - timedelta(days=5),
                rejection_reason=reason, rejection_tags=tags, trial_days=14 if tried else None,
            )
        )  # fmt: skip
    await db.flush()

    p = await product_svc.draft_from_candidate(db, chosen.id, decision.id)
    assert p is not None
    p.name = spec["title"]
    p.subtitle = spec["subtitle"]
    p.short_description = spec["summary"]
    p.description = (
        f"{spec['summary']}\n\nMình dùng thử {spec['trial_days']} ngày trước khi chọn. "
        f"Điều chưa ưng mình cũng ghi rõ bên dưới."
    )
    p.faq = [{"q": q, "a": a, "source": "Ghi chú thử hàng của chị"} for q, a in spec["faq"]]
    p.price_vnd = spec["price"]
    p.landed_cost_vnd = int(spec["price_src"] * 1.25)
    p.seo_title = f"{spec['title']} — đã dùng thử {spec['trial_days']} ngày"
    p.seo_description = spec["summary"][:160]
    p.ai_generated = True
    p.status = ProductStatus.PENDING_REVIEW
    decision.product_id = p.id
    await db.flush()
    for i, note in enumerate(("Ảnh mẫu", "Ảnh mẫu · chi tiết")):
        color = spec["color"] if i == 0 else tuple(min(255, v + 30) for v in spec["color"])
        await product_svc.upload_image(db, p, img_lib.sample_photo(spec["title"], color, note=note), alt=spec["title"])  # type: ignore[arg-type]
    await product_svc.publish(db, p)
    p.published_at = now - timedelta(days=rng.randrange(1, 20))
    await db.flush()
    return p


async def _seed_principles(db: AsyncSession) -> int:
    have = set((await db.execute(select(SelectionPrinciple.text))).scalars())
    added = 0
    for i, (kind, text) in enumerate(EXTRA_PRINCIPLES):
        if text not in have:
            db.add(SelectionPrinciple(kind=PrincipleKind(kind), text=text, priority=10 + i))
            added += 1
    await db.flush()
    return added


async def _drop(db: AsyncSession, code: str, **kw: Any) -> Drop | None:
    if (await db.execute(select(Drop.id).where(Drop.code == code))).scalar_one_or_none():
        return None
    d = Drop(code=code, **kw)
    db.add(d)
    await db.flush()
    return d


async def _seed_drops(db: AsyncSession, products: dict[str, Product]) -> int:
    now = now_utc()
    created = 0
    d = await _drop(db, "D12", slug="dot-12-do-bep-gon", title="Đồ bếp gọn cho nhà nhỏ", status=DropStatus.OPEN,
                    description="Bốn món bếp mình dùng hằng ngày. Gom đủ suất thì đặt một lô, hàng về là gửi ngay.",
                    opens_at=now - timedelta(days=4), closes_at=now + timedelta(days=2, hours=14),
                    expected_arrival_date=(now + timedelta(days=17)).date(), deposit_pct=50,
                    announced_at=now - timedelta(days=4))  # fmt: skip
    if d:
        created += 1
        for pos, (key, slots, reserved) in enumerate((("binh-giu-nhiet", 50, 34), ("hop-com-inox", 40, 31),
                                                     ("hop-gia-vi", 30, 21))):  # fmt: skip
            p = products[key]
            db.add(DropItem(drop_id=d.id, product_id=p.id, price_vnd=p.price_vnd, slots_total=slots,
                            slots_reserved=reserved, max_per_order=3, position=pos))  # fmt: skip
    d = await _drop(db, "D13", slug="dot-13-do-cho-be-di-hoc", title="Đồ cho bé đi học", status=DropStatus.SCHEDULED,
                    description="Khăn, túi giặt cho bé đi học bán trú. Bấm «Nhắc mình» để được báo khi mở.",
                    opens_at=now + timedelta(days=7), closes_at=now + timedelta(days=12),
                    expected_arrival_date=(now + timedelta(days=28)).date())  # fmt: skip
    if d:
        created += 1
        for pos, key in enumerate(("khan-tam-be", "tui-luoi-giat")):
            p = products[key]
            db.add(DropItem(drop_id=d.id, product_id=p.id, price_vnd=p.price_vnd, slots_total=60, position=pos))
        db.add(DropReminder(drop_id=d.id, contact="0000000001", contact_key=hash_key("drop-remind", "0000000001")))
    d = await _drop(db, "D11", slug="dot-11-do-di-xa", title="Đồ đi xa", status=DropStatus.FULFILLING,
                    description="Đợt trước: đồ gọn cho chuyến đi dài.", opens_at=now - timedelta(days=40),
                    closes_at=now - timedelta(days=30), expected_arrival_date=(now - timedelta(days=12)).date(),
                    actual_arrival_date=(now - timedelta(days=11)).date())  # fmt: skip
    if d:
        created += 1
        for pos, key in enumerate(("gia-phoi", "den-kep")):
            p = products[key]
            db.add(DropItem(drop_id=d.id, product_id=p.id, price_vnd=p.price_vnd, slots_total=80, slots_reserved=72,
                            position=pos))  # fmt: skip
        await db.flush()
        await _seed_orders_and_reviews(db, d, [products["gia-phoi"], products["den-kep"]])
    await db.flush()
    return created


REVIEW_TEXTS = [
    (5, "Gấp lại mỏng thật, nhà mình để sau cánh cửa vừa khít.", "Hà"),
    (5, "Đúng như chị tả, chân hơi trơn nên mình lót thêm miếng cao su.", "Minh"),
    (4, "Dùng ổn, giao hơi lâu vì phải chờ đợt nhưng chị báo trước rồi.", "Trang"),
    (5, "Đèn dịu mắt, kẹp chắc. Dây ngắn như chị nói.", "Quân"),
    (5, "Con mình đọc truyện buổi tối không bị chói nữa.", "Lan"),
]


async def _seed_orders_and_reviews(db: AsyncSession, drop: Drop, products: list[Product]) -> None:
    from app.modules.orders.models import Order, OrderItem, OrderStatus, PaymentState

    now = now_utc()
    for i, (rating, body, name) in enumerate(REVIEW_TEXTS):
        p = products[i % len(products)]
        o = Order(
            code=f"HCDEMO{i + 1:04d}", drop_id=drop.id, status=OrderStatus.DELIVERED, payment_state=PaymentState.PAID,
            recipient_name=f"Khách ví dụ {name}", recipient_phone=f"00000000{i + 10:02d}", placed_at=now - timedelta(days=35),
            subtotal_vnd=p.price_vnd, total_vnd=p.price_vnd, paid_vnd=p.price_vnd, delivered_at=now - timedelta(days=9),
        )  # fmt: skip
        db.add(o)
        await db.flush()
        it = OrderItem(order_id=o.id, product_id=p.id, name=p.name, quantity=1, unit_price_vnd=p.price_vnd,
                       line_total_vnd=p.price_vnd)  # fmt: skip
        db.add(it)
        await db.flush()
        db.add(
            Review(
                product_id=p.id, order_id=o.id, order_item_id=it.id, token=f"demo-review-{drop.code}-{i}",
                status=ReviewStatus.PUBLISHED, display_name=name, rating=rating, body=body,
                requested_at=now - timedelta(days=9), submitted_at=now - timedelta(days=7),
                published_at=now - timedelta(days=6), ai_flags={"recommend": "publish"},
            )
        )  # fmt: skip


async def _seed_more_reviews(db: AsyncSession, products: dict[str, Product]) -> int:
    from app.modules.catalog.reviews import recompute_rating

    rows = [
        ("binh-giu-nhiet", 5, "Sáng pha trà, chiều vẫn còn ấm. Nắp tháo rửa tiện thật.", "Thu", True),
        ("binh-giu-nhiet", 4, "Miệng hẹp đúng như chị nói, bỏ đá viên phải đập nhỏ.", "Nam", True),
        ("binh-giu-nhiet", 5, "Nhẹ, bỏ túi xách không nặng vai.", "Ngọc", True),
        ("hop-com-inox", 5, "Canh không tràn sang cơm, đồng nghiệp hỏi mua ở đâu.", "Vy", True),
        ("hop-com-inox", 4, "Hơi nặng nhưng chắc chắn.", "Dũng", True),
        ("hop-gia-vi", 2, "Thìa nhỏ quá, mình phải dùng thìa khác.", "Hoa", False),
    ]
    now = now_utc()
    added = 0
    for i, (key, rating, body, name, published) in enumerate(rows):
        token = f"demo-shelf-review-{i}"
        if (await db.execute(select(Review.id).where(Review.token == token))).scalar_one_or_none():
            continue
        p = products[key]
        photos = []
        if i < 2:
            processed = img_lib.process_photo(img_lib.sample_photo(p.name, (120, 120, 110), note="Ảnh khách gửi"),
                                              enhance=False)  # fmt: skip
            photos = [{"files": await img_lib.store_renditions(f"public/reviews/demo-{i}", processed)}]
        db.add(
            Review(
                product_id=p.id, token=token, display_name=name, rating=rating, body=body, photos=photos,
                status=ReviewStatus.PUBLISHED if published else ReviewStatus.PENDING_REVIEW,
                requested_at=now - timedelta(days=8), submitted_at=now - timedelta(days=6 - i % 3),
                published_at=now - timedelta(days=5 - i % 3) if published else None,
                ai_flags={"recommend": "publish", "spam": False, "offensive": False},
                ai_summary="Nội dung bình thường, có thể hiển thị.",
            )
        )  # fmt: skip
        added += 1
    await db.flush()
    for p in products.values():
        await recompute_rating(db, p.id)
    return added


async def _seed_finds(db: AsyncSession) -> int:
    now = now_utc()
    rows = [
        ("binh-sua-thuy-tinh-demo", "Bình sữa thuỷ tinh cho bé 6 tháng, núm mềm", 47, FindRequestStatus.SEARCHING, 3),
        ("gia-phoi-ban-cong-demo", "Giá phơi đồ gấp gọn cho ban công 1 m²", 31, FindRequestStatus.SEARCHING, 0),
        ("may-xay-cam-tay-demo", "Máy xay cầm tay không ồn", 12, FindRequestStatus.CLOSED, 0),
        ("thot-go-khong-moc-demo", "Thớt gỗ không mốc cho nhà ẩm", 8, FindRequestStatus.OPEN, 0),
        ("ke-giay-hep-demo", "Kệ giày hẹp cho hành lang chung cư", 4, FindRequestStatus.PENDING_REVIEW, 0),
    ]
    added = 0
    for i, (slug, title, votes, st, trying) in enumerate(rows):
        if (await db.execute(select(FindRequest.id).where(FindRequest.public_slug == slug))).scalar_one_or_none():
            continue
        brief_id = None
        if st == FindRequestStatus.SEARCHING:
            brief = SourcingBrief(title=f"Nhờ tìm: {title}", raw_text=title, status=BriefStatus.ACTIVE)
            db.add(brief)
            await db.flush()
            brief_id = brief.id
            for k in range(trying):
                db.add(Candidate(brief_id=brief.id, stage=CandidateStage.TRIAL, source_platform=SourcePlatform.TAOBAO,
                                 source_external_id=f"demo-find-{slug}-{k}", title_vi=f"{title} — mẫu {k + 1}"))  # fmt: skip
        db.add(
            FindRequest(
                public_slug=slug, title=title, status=st, vote_count=votes, vote_threshold=30, brief_id=brief_id,
                threshold_reached_at=now - timedelta(days=3) if votes >= 30 else None,
                moderation_note="Nội dung bình thường, có thể hiển thị.",
                created_at=now - timedelta(days=20 - i * 3),
            )
        )  # fmt: skip
        added += 1
    await db.flush()
    return added


async def seed_demo(db: AsyncSession) -> dict[str, int]:
    rng = random.Random(48)
    cats = await _categories(db)
    counts = {"principles": await _seed_principles(db), "products": 0}
    for spec in PRODUCTS:
        if await _seed_product(db, spec, cats, rng):
            counts["products"] += 1
    by_key: dict[str, Product] = {}
    for spec in PRODUCTS:
        c = (
            await db.execute(select(Candidate).where(Candidate.source_external_id == f"demo-{spec['key']}-0"))
        ).scalar_one()
        by_key[spec["key"]] = (await db.execute(select(Product).where(Product.candidate_id == c.id))).scalar_one()
    counts["drops"] = await _seed_drops(db, by_key)
    counts["reviews"] = await _seed_more_reviews(db, by_key)
    counts["finds"] = await _seed_finds(db)
    await db.flush()
    return counts


async def main() -> None:
    from app.core.db import SessionLocal
    from app.core.discovery import discover_modules
    from app.seed import seed

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    discover_modules()
    async with SessionLocal() as db:
        await seed(db)
        counts = await seed_demo(db)
        await db.commit()
    log.info("Dữ liệu mẫu website: %s", ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    asyncio.run(main())
