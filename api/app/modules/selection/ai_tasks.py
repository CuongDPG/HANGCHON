"""Tác vụ AI của bàn chọn (c2, c3, c6) và hàm giả tiếng Việt cho provider `fake`."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field
from unidecode import unidecode

from app import ai

# ---- c2: sắp ghi chú thô thành ý gọn ------------------------------------------------------------------------------


class NoteCandidateRef(BaseModel):
    id: str
    title: str


class OrganizeNoteIn(BaseModel):
    text: str
    candidate_title: str | None = None
    trial_day: int | None = None
    candidates: list[NoteCandidateRef] = Field(
        default_factory=list, description="Các món đang mua mẫu/đang thử, khi ghi chú chưa gắn món"
    )


class OrganizedPoint(BaseModel):
    kind: Literal["good", "bad", "measure"] = Field(description="good = điểm tốt, bad = điểm chưa ưng, measure = số đo")
    text: str = Field(description="Một ý gọn, giữ nguyên ý của chị, không thêm điều chị không nói")


class OrganizeNoteOut(BaseModel):
    points: list[OrganizedPoint]
    sentiment: Literal["positive", "negative", "mixed", "neutral"]
    candidate_id: str | None = Field(default=None, description="Id món trong danh sách nếu ghi chú chưa gắn món")
    confidence: float = Field(ge=0, le=1, description="Độ chắc chắn khi xếp vào món")


ai.task(
    "selection.organize_note",
    tier="fast",
    description="Sắp ghi chú thử hàng thành ý gọn, gắn nhãn, xếp vào đúng món",
    system=(
        "Bạn giúp chị ghi nhật ký thử hàng. Đầu vào là lời chị nói hoặc gõ khi đang dùng thử một món đồ gia dụng.\n"
        "Việc của bạn: tách lời thành từng ý ngắn (mỗi ý một câu), gắn nhãn cho từng ý:\n"
        "- good: điều chị thấy tốt, hài lòng;\n"
        "- bad: điều chị chưa ưng, lỗi, phiền;\n"
        "- measure: con số chị đo hoặc đếm (kích thước, cân nặng, thời gian, số lần...).\n"
        "Giữ nguyên ý và cách nói của chị, sửa lỗi chép lời rõ ràng. KHÔNG thêm ý chị không nói, KHÔNG suy diễn công dụng, "
        "KHÔNG bịa con số. Lời chị nói lan man hoặc không có ý nào rõ thì trả danh sách ý rỗng.\n"
        "Nếu có danh sách `candidates` (ghi chú chưa gắn món): chọn id món khớp nhất với nội dung; không chắc thì để null "
        "và độ chắc chắn thấp."
    ),
)

# Từ (không dấu) cho hàm giả: chê / khen / phủ định. «hơi …» là chê nhẹ; «không/chưa + chê» là khen.
_NEG = {"long", "mop", "ro", "ri", "gi", "nut", "gay", "vong", "truot", "mui", "kem", "nang", "kho", "cham", "bam", "tron",
        "xu", "sac", "chat", "bung", "phai", "tiec", "lau", "moc", "ket", "rung"}  # fmt: skip
_POS = {"chac", "em", "gon", "nhanh", "dep", "thich", "ung", "sach", "vua", "ben", "nhe", "mem", "de", "tot", "kin"}
_NEGATORS = {"khong", "chua", "chang", "it"}
_MEASURE = re.compile(r"\d+([.,]\d+)?\s*(cm|mm|m|kg|g|gam|ml|l|lit|phut|giay|gio|ngay|lan|cai|do|%)\b", re.I)


def _plain(s: str) -> str:
    return unidecode(s).lower()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…;])\s+|\n+|,\s+(?:nhưng|mà|còn)\s+", text.strip())
    out = []
    for p in parts:
        p = p.strip(" .;,-–")
        if len(p) >= 3:
            out.append(p[0].upper() + p[1:] + ("" if p.endswith((".", "!", "?")) else "."))
    return out


def classify_sentence(s: str) -> str:
    plain = _plain(s)
    if _MEASURE.search(plain):
        return "measure"
    words = re.findall(r"[a-z]+", plain)
    score = 0
    for i, w in enumerate(words):
        negated = any(x in _NEGATORS for x in words[max(0, i - 2) : i])
        if w == "hoi":  # «hơi lâu khô», «hơi sắc»
            score -= 1
        elif w in _NEG:
            score += 1 if negated else -1
        elif w in _POS:
            score += -1 if negated else 1
    return "bad" if score < 0 else "good"


@ai.fake("selection.organize_note")
def _fake_organize(inp: OrganizeNoteIn) -> OrganizeNoteOut:
    points = [OrganizedPoint(kind=classify_sentence(s), text=s) for s in _sentences(inp.text)]  # type: ignore[arg-type]
    kinds = {p.kind for p in points if p.kind != "measure"}
    sentiment = (
        "neutral" if not kinds else "mixed" if len(kinds) == 2 else ("positive" if "good" in kinds else "negative")
    )
    cand, conf = None, 0.0
    if inp.candidates:
        words = set(_plain(inp.text).split())
        best = max(inp.candidates, key=lambda c: len(words & set(_plain(c.title).split())))
        overlap = len(words & set(_plain(best.title).split()))
        if overlap:
            cand, conf = best.id, min(0.95, 0.4 + 0.2 * overlap)
    return OrganizeNoteOut(points=points, sentiment=sentiment, candidate_id=cand, confidence=conf)  # type: ignore[arg-type]


# ---- c3: «Vì sao mình chọn» và «Điều mình chưa ưng» ---------------------------------------------------------------


class DraftNote(BaseModel):
    day: int | None = None
    text: str
    points: list[OrganizedPoint] = Field(default_factory=list)


class DraftReasonsIn(BaseModel):
    candidate_title: str
    trial_days: int | None = None
    notes: list[DraftNote]
    owner_request: str | None = Field(default=None, description="Lời nhắn của chị khi trả lại bản nháp trước")


class DraftReasonsOut(BaseModel):
    reasons_selected: list[str] = Field(max_length=3, description="Đúng 3 ý nếu ghi chú đủ, ít hơn nếu không đủ")
    not_satisfied: list[str] = Field(max_length=3)
    missing_info: str | None = Field(default=None, description="Ghi chú còn thiếu gì để viết cho đủ")


ai.task(
    "selection.draft_reasons",
    tier="smart",
    description="Soạn «Vì sao mình chọn» (3 ý) và «Điều mình chưa ưng» từ ghi chú thử",
    system=(
        "Bạn viết hộ chị hai đoạn ngắn cho trang sản phẩm: «Vì sao mình chọn» (tối đa 3 ý) và «Điều mình chưa ưng».\n"
        "Viết bằng giọng của chị: xưng «mình», câu ngắn, thật thà, kể như đang dùng thật. Mỗi ý một câu.\n"
        "CHỈ dùng điều có trong ghi chú thử hàng được cung cấp. KHÔNG thêm công dụng, số liệu, so sánh hay lời khen "
        "nào không có trong ghi chú. KHÔNG dùng từ «tốt nhất», «số 1», «thần thánh», «cam kết».\n"
        "Ghi chú không đủ 3 ý tốt thì viết ít ý hơn và nói rõ thiếu gì ở `missing_info`. "
        "Không có điều chưa ưng nào trong ghi chú thì để danh sách rỗng, không tự nghĩ ra.\n"
        "Nếu có `owner_request` (chị trả lại bản trước kèm lời nhắn) thì sửa theo lời nhắn, vẫn chỉ dùng ghi chú."
    ),
)


def _as_mine(text: str) -> str:
    """Giữ nguyên lời chị (hàm giả không viết lại để khỏi thêm ý)."""
    t = text.strip().rstrip(".")
    return f"{t[:1].upper()}{t[1:]}." if t else t


@ai.fake("selection.draft_reasons")
def _fake_draft(inp: DraftReasonsIn) -> DraftReasonsOut:
    good: list[str] = []
    bad: list[str] = []
    for n in inp.notes:
        pts = n.points or [OrganizedPoint(kind=classify_sentence(s), text=s) for s in _sentences(n.text)]  # type: ignore[arg-type]
        for p in pts:
            bucket = bad if p.kind == "bad" else good
            if p.text not in bucket:
                bucket.append(p.text)
    reasons = [_as_mine(t) for t in good[:3]]
    missing = None if len(reasons) >= 3 else f"Ghi chú mới có {len(reasons)} ý tốt, chị nói thêm vài câu nữa nhé."
    return DraftReasonsOut(reasons_selected=reasons, not_satisfied=[_as_mine(t) for t in bad[:3]], missing_info=missing)


# ---- c6: gu của chị -----------------------------------------------------------------------------------------------


class TasteDecision(BaseModel):
    decision: Literal["selected", "rejected"]
    title: str
    reasons: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None
    rejection_tags: list[str] = Field(default_factory=list)


class TasteTraitOut(BaseModel):
    trait: str = Field(description="Một đặc điểm ngắn, vd «chịu nhiệt tốt», «có mùi nhựa»")
    weight: float = Field(ge=-1, le=1, description="> 0 chị hay chọn, < 0 chị hay loại")


class TasteIn(BaseModel):
    category_name: str | None = None
    decisions: list[TasteDecision]
    principles: list[str] = Field(default_factory=list)
    previous_summary: str | None = None
    previous_traits: list[TasteTraitOut] = Field(default_factory=list)
    owner_edited: bool = False


class TasteOut(BaseModel):
    summary: str = Field(description="2–4 câu mô tả gu của chị, nói với chị (xưng «em», gọi «chị»)")
    traits: list[TasteTraitOut]


ai.task(
    "selection.taste_profile",
    tier="smart",
    description="Tổng hợp gu chọn hàng của chị từ lịch sử chọn/loại",
    system=(
        "Bạn tổng hợp «gu» chọn hàng của chị từ lịch sử các món chị đã chọn và đã loại (kèm lý do).\n"
        "Trả về đoạn tóm tắt 2–4 câu (xưng «em», gọi «chị») và danh sách đặc điểm có trọng số: dương là điều chị hay chọn, "
        "âm là điều chị hay loại; trị tuyệt đối càng lớn khi càng nhiều lần lặp lại.\n"
        "CHỈ rút từ lý do có trong dữ liệu; không đoán tính cách, không thêm đặc điểm không có căn cứ. Ít dữ liệu thì nói rõ "
        "là còn ít mẫu.\n"
        "Nếu `owner_edited` là true thì chị đã tự sửa bản trước: giữ các đặc điểm chị đã sửa, chỉ bổ sung điều mới."
    ),
)


@ai.fake("selection.taste_profile")
def _fake_taste(inp: TasteIn) -> TasteOut:
    from app.modules.selection.service import REJECT_GROUP_LABELS

    score: dict[str, float] = {t.trait: t.weight for t in inp.previous_traits} if inp.owner_edited else {}
    seen: dict[str, int] = {}
    for d in inp.decisions:
        if d.decision == "rejected":
            for tag in d.rejection_tags or ["khac"]:
                label = REJECT_GROUP_LABELS.get(tag, tag)
                seen[f"-{label}"] = seen.get(f"-{label}", 0) + 1
        else:
            for r in d.reasons[:3]:
                key = re.sub(r"^(mình thấy|mình)\s+", "", r.strip().rstrip("."), flags=re.I)
                key = key[:60]
                seen[f"+{key}"] = seen.get(f"+{key}", 0) + 1
    for key, n in seen.items():
        sign = -1 if key.startswith("-") else 1
        score.setdefault(key[1:], round(sign * min(1.0, 0.3 + 0.2 * n), 2))
    traits = [TasteTraitOut(trait=k, weight=v) for k, v in sorted(score.items(), key=lambda kv: -abs(kv[1]))[:10]]
    n_sel = sum(d.decision == "selected" for d in inp.decisions)
    n_rej = len(inp.decisions) - n_sel
    where = f" ở nhóm {inp.category_name}" if inp.category_name else ""
    likes = [t.trait for t in traits if t.weight > 0][:2]
    dislikes = [t.trait.lower() for t in traits if t.weight < 0][:2]
    parts = [f"Em mới xem {n_sel} món chị chọn và {n_rej} món chị loại{where}."]
    if likes:
        parts.append("Chị hay giữ những món: " + "; ".join(x.lower() for x in likes) + ".")
    if dislikes:
        parts.append("Chị thường loại vì " + " và ".join(dislikes) + ".")
    if len(inp.decisions) < 5:
        parts.append("Còn ít mẫu nên em chưa chắc, chị sửa giúp em nếu thấy chưa đúng.")
    return TasteOut(summary=" ".join(parts), traits=traits)
