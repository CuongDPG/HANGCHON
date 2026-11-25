"""Chữ tiếng Việt cho tìm kiếm và đường dẫn: bỏ dấu, đ → d, slug duy nhất, băm định danh khách."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

_SPACE = re.compile(r"\s+")
_WORD = re.compile(r"[a-z0-9]+")


def normalize_vi(text: str | None) -> str:
    """«Bình GIỮ  nhiệt Đỏ» → «binh giu nhiet do»."""
    if not text:
        return ""
    s = unicodedata.normalize("NFD", text)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "D").lower()
    return _SPACE.sub(" ", s).strip()


def words(text: str | None) -> list[str]:
    return _WORD.findall(normalize_vi(text))


def matches_vi(haystack: str, query: str) -> bool:
    """Mọi từ của `query` đều có trong `haystack` (không dấu, không cần đúng thứ tự)."""
    terms = words(query)
    if not terms:
        return True
    text = normalize_vi(haystack)
    return all(t in text for t in terms)


def slugify_vi(text: str, *, max_length: int = 120) -> str:
    return slugify(normalize_vi(text), max_length=max_length) or "mon-hang"


async def unique_slug(db: AsyncSession, model: Any, text: str, *, column: str = "slug", exclude_id: Any = None) -> str:
    """Slug chưa dùng trong bảng `model` (thêm -2, -3... khi trùng)."""
    base = slugify_vi(text)
    col = getattr(model, column)
    q = select(col).where(col.like(f"{base}%"))
    if exclude_id is not None:
        q = q.where(model.id != exclude_id)
    taken = set((await db.execute(q)).scalars())
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


# ---- giọng với khách: không gọi người bán là «chị» ---------------------------------------------------------------
# «chị» đứng riêng (không phải một phần của từ khác như «chịu»), kèm «anh chị» / «anh/chị» / «chị em».
_CHI = re.compile(r"(?<!\w)(?:(anh)\s*/?\s*)?(chị)(?:\s+(em))?(?!\w)", re.IGNORECASE)
# lời trích nguyên văn (của khách, của đánh giá) nằm trong ngoặc: không bắt lỗi xưng hô ở trong đó
_QUOTED = re.compile(r"«[^»\n]*»|“[^”\n]*”|\"[^\"\n]*\"")
_SENTENCE_END = re.compile(r"[.!?…\n]")


def _same_case(word: str, like: str) -> str:
    if like.isupper() and len(like) > 1:
        return word.upper()
    return word[:1].upper() + word[1:] if like[:1].isupper() else word


def _fix(m: re.Match[str]) -> str:
    if m.group(1) or m.group(3):  # «anh chị», «chị em» = gọi khách → «bạn»
        return _same_case("bạn", m.group(0))
    return _same_case("mình", m.group(2))  # người bán tự xưng → «mình»


def seller_address_issues(text: str | None) -> list[dict[str, str]]:
    """Các câu gửi khách còn gọi người bán là «chị» (hoặc gọi khách «anh chị», «chị em»), bỏ qua lời trích trong
    ngoặc «…» / “…” / "…". Mỗi mục: `quote` (câu gốc) và `suggestion` (câu đã đổi sang «mình» / «bạn»)."""
    if not text:
        return []
    masked = _QUOTED.sub(lambda m: " " * len(m.group(0)), text)
    out: list[dict[str, str]] = []
    seen: set[int] = set()
    for m in _CHI.finditer(masked):
        start = max((e.end() for e in _SENTENCE_END.finditer(text, 0, m.start())), default=0)
        if start in seen:
            continue
        seen.add(start)
        end_m = _SENTENCE_END.search(text, m.end())
        end = end_m.end() if end_m else len(text)
        raw = text[start:end]
        lead = len(raw) - len(raw.lstrip())
        sentence = raw.strip()
        masked_sentence = masked[start + lead : start + lead + len(sentence)]
        parts, last = [], 0
        for mm in _CHI.finditer(masked_sentence):  # chỉ thay ở chỗ không nằm trong ngoặc trích
            parts += [sentence[last : mm.start()], _fix(mm)]
            last = mm.end()
        parts.append(sentence[last:])
        out.append({"quote": sentence, "suggestion": "".join(parts)})
    return out


def hash_key(*parts: str) -> str:
    """Băm (có muối) cho định danh khách: thiết bị, SĐT, IP — không lưu giá trị thô."""
    raw = "|".join(p.strip().lower() for p in parts)
    return hashlib.sha256(f"{settings.jwt_secret}|{raw}".encode()).hexdigest()


def normalize_contact(contact: str) -> str:
    """Chuẩn hoá SĐT Việt Nam (+84 / 84 → 0); liên hệ khác giữ nguyên chữ thường."""
    c = contact.strip()
    digits = re.sub(r"[\s.\-()]", "", c)
    if re.fullmatch(r"\+?\d{9,12}", digits):
        d = digits.lstrip("+")
        if d.startswith("84"):
            d = "0" + d[2:]
        return d
    return c.lower()


def looks_like_phone(contact: str) -> bool:
    return bool(re.fullmatch(r"0\d{9}", normalize_contact(contact)))
