"""c5 + c6 tác dụng ngược lại săn hàng: nguyên tắc của chị và gu đã học chỉnh thứ hạng ứng viên.

Luật tính trong code, không gọi AI, để giải thích được từng điểm cộng/trừ:
- Nguyên tắc dạng loại trừ (`must_not`, `avoid`) khớp chữ trong tên/lý do của tin rao → giữ ứng viên nhưng hạ hạng
  và ghi «Trái nguyên tắc: …» (không xoá âm thầm). `must_not` còn gắn cờ để xếp xuống cuối.
- Gu (`taste_profiles.weights`: đặc điểm → trọng số −1..1) khớp chữ → cộng/trừ điểm, tổng giới hạn ±15.

Chỉ đọc bảng của selection (`selection_principles`, `taste_profiles`)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from unidecode import unidecode

from app.modules.selection.models import PrincipleKind, SelectionPrinciple, TasteProfile  # chỉ đọc

MUST_NOT_PENALTY = 30
AVOID_PENALTY = 10
TASTE_SCALE = 10  # trọng số 1.0 → 10 điểm
TASTE_CAP = 15
TASTE_MIN_WEIGHT = 0.2  # đặc điểm yếu quá thì bỏ qua

# Chữ không mang nghĩa khi so khớp (không dấu): phủ định, động từ chọn/nhập, từ chung chỉ món hàng.
_STOP = {
    "khong", "chua", "chang", "dung", "tranh", "han", "che", "bot", "it", "nen", "phai", "can", "co", "duoc", "bi",
    "nhap", "ban", "chon", "lay", "mua", "giu", "loai", "bo", "hang", "mon", "do", "san", "pham", "mau", "cai", "chiec",
    "cac", "nhung", "mot", "la", "va", "cua", "cho", "voi", "nao", "gi", "khi", "thi", "ma", "rat", "qua", "hon",
    "nhieu", "the", "nay", "kia", "minh", "chi", "em", "hay", "hoac", "neu", "vi", "de", "o", "tu", "ve", "len", "ra",
}  # fmt: skip
_ALT = re.compile(r",|;|/|\bhoac\b|\bhay\b")


def plain(text: str | None) -> str:
    return " " + " ".join(re.findall(r"[a-z0-9]+", unidecode(text or "").lower())) + " "


def content_words(text: str) -> list[str]:
    return [w for w in plain(text).split() if w not in _STOP and len(w) >= 2]


_NEGATORS = {"khong", "chua", "chang", "it"}


def trait_tokens(text: str) -> list[str]:
    """Chữ để so một đặc điểm gu. Phủ định dính với chữ sau nó: «Không bền» → ["khong ben"] (khớp «không bền», không
    khớp «bền»), «Không pin, cắm USB» → ["khong pin", "cam", "usb"]."""
    words = plain(text).split()
    out: list[str] = []
    i = 0
    while i < len(words):
        w = words[i]
        if w in _NEGATORS and i + 1 < len(words):
            out.append(f"{w} {words[i + 1]}")
            i += 2
            continue
        if w not in _STOP and len(w) >= 2:
            out.append(w)
        i += 1
    return out


def alternatives(text: str) -> list[list[str]]:
    """«Không nhập đồ có pin hoặc sạc điện» → [["pin"], ["sac", "dien"]]."""
    out = [content_words(part) for part in _ALT.split(plain(text))]
    return [ws for ws in out if ws]


@dataclass
class Rule:
    kind: PrincipleKind
    text: str
    alts: list[list[str]]


@dataclass
class Trait:
    trait: str
    weight: float
    words: list[str]


@dataclass
class Guidance:
    rules: list[Rule] = field(default_factory=list)
    traits: list[Trait] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.rules or self.traits)


async def load(db: AsyncSession, category_id: uuid.UUID | None) -> Guidance:
    cond = SelectionPrinciple.category_id.is_(None)
    if category_id:
        cond = or_(cond, SelectionPrinciple.category_id == category_id)
    rows = (
        await db.execute(
            select(SelectionPrinciple)
            .where(
                SelectionPrinciple.is_active.is_(True),
                SelectionPrinciple.kind.in_([PrincipleKind.MUST_NOT, PrincipleKind.AVOID]),
                cond,
            )
            .order_by(SelectionPrinciple.priority)
        )
    ).scalars()
    rules = []
    for p in rows:
        kw = (p.structured or {}).get("keywords")
        alts = [content_words(str(k)) for k in kw] if isinstance(kw, list) and kw else alternatives(p.text)
        alts = [a for a in alts if a]
        if alts:
            rules.append(Rule(kind=p.kind, text=p.text.strip().rstrip("."), alts=alts))
    # gu chung trước, gu của nhóm hàng ghi đè cùng đặc điểm
    profiles = (
        await db.execute(
            select(TasteProfile).where(
                or_(TasteProfile.category_id.is_(None), TasteProfile.category_id == category_id)
                if category_id
                else TasteProfile.category_id.is_(None)
            )
        )
    ).scalars()
    weights: dict[str, float] = {}
    for prof in sorted(profiles, key=lambda x: x.category_id is not None):
        for k, v in (prof.weights or {}).items():
            if isinstance(v, int | float) and abs(v) >= TASTE_MIN_WEIGHT:
                weights[str(k)] = float(v)
    traits = [Trait(trait=k, weight=v, words=ws) for k, v in weights.items() if (ws := trait_tokens(k))]
    return Guidance(rules=rules, traits=traits)


def _has(text: str, words: list[str]) -> bool:
    return all(f" {w} " in text for w in words)


def _trait_hits(text: str, words: list[str]) -> bool:
    hit = sum(f" {w} " in text for w in words)
    return hit >= max(1, -(-len(words) * 2 // 3))  # ít nhất 2/3 số chữ của đặc điểm


def assess(g: Guidance, text: str) -> tuple[int, bool, list[dict[str, Any]]]:
    """→ (điểm cộng/trừ, có trái nguyên tắc «không chấp nhận», ghi chú giải thích)."""
    t = plain(text)
    delta, violates, notes = 0, False, []
    for r in g.rules:
        if any(_has(t, a) for a in r.alts):
            pen = MUST_NOT_PENALTY if r.kind == PrincipleKind.MUST_NOT else AVOID_PENALTY
            delta -= pen
            violates = violates or r.kind == PrincipleKind.MUST_NOT
            notes.append({"kind": "principle", "delta": -pen, "text": f"Trái nguyên tắc: {r.text}"})
    taste = 0
    taste_notes = []
    for tr in g.traits:
        if _trait_hits(t, tr.words):
            d = round(tr.weight * TASTE_SCALE)
            if d == 0:
                continue
            taste += d
            label = "Hợp gu chị" if d > 0 else "Chị hay loại"
            taste_notes.append({"kind": "taste", "delta": d, "text": f"{label}: {tr.trait.strip().rstrip('.')}"})
    capped = max(-TASTE_CAP, min(TASTE_CAP, taste))
    if taste_notes and capped != taste:
        taste_notes.append({"kind": "taste", "delta": 0, "text": f"Gu chỉnh tối đa ±{TASTE_CAP} điểm."})
    return delta + capped, violates, notes + taste_notes


def apply(g: Guidance, fields: dict[str, Any], *texts: str | None) -> dict[str, Any]:
    """Chỉnh `ai_score` của một ứng viên (dict trước khi lưu), lưu giải thích vào `raw.guidance`."""
    if not g:
        return fields
    text = " ".join(x for x in (fields.get("title_vi"), fields.get("title_original"), fields.get("rank_reason"),
                                *texts) if x)  # fmt: skip
    delta, violates, notes = assess(g, text)
    if not notes:
        return fields
    base = fields.get("ai_score")
    fields["ai_score"] = max(0, min(100, (base or 0) + delta)) if base is not None else None
    raw = dict(fields.get("raw") or {})
    raw["guidance"] = {"base_score": base, "delta": delta, "violates": violates, "notes": notes}
    fields["raw"] = raw
    return fields


def view(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Phần giải thích cho giao diện (None nếu nguyên tắc/gu không đụng tới món này)."""
    gd = (raw or {}).get("guidance")
    return gd if isinstance(gd, dict) and gd.get("notes") else None
