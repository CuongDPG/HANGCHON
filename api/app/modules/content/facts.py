"""Đọc dữ liệu nguồn cho AI (chỉ đọc bảng của module khác): hồ sơ sản phẩm, đợt mở bán, ghi chú thử hàng, giọng của chị,
nhận xét gần nhất; tiện ích dựng link và đường dẫn ảnh."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import get_storage
from app.core.timeutil import to_local
from app.modules.catalog.models import Drop, Product
from app.modules.content.ai_io import DropFacts, DropItemFacts, ProductFacts, VoiceCard
from app.modules.content.models import ContentInsight, VoiceProfile
from app.modules.selection.models import TrialNote


def store_url(path: str, src: str | None = None) -> str:
    base = settings.web_base_url.rstrip("/")
    return f"{base}{path}" + (f"?src={src}" if src else "")


def product_path(p: Product) -> str:
    return f"/san-pham/{p.slug}"


def drop_path(d: Drop) -> str:
    return f"/dot/{d.slug}"


def image_keys(p: Product) -> list[str]:
    imgs = sorted(p.images, key=lambda i: (not i.is_primary, i.position))
    return [i.processed_key or i.original_key for i in imgs]


def file_url(key: str) -> str:
    return get_storage().url(key)


def product_facts(p: Product) -> ProductFacts:
    imgs = sorted(p.images, key=lambda i: (not i.is_primary, i.position))
    return ProductFacts(
        id=str(p.id),
        name=p.name,
        subtitle=p.subtitle,
        short_description=p.short_description,
        price_vnd=p.price_vnd,
        compare_at_price_vnd=p.compare_at_price_vnd,
        specs=[s for s in p.specs if isinstance(s, dict)],
        trial_days=p.trial_days,
        selected_count=p.selected_count,
        considered_count=p.considered_count,
        reason_selected=p.reason_selected,
        not_satisfied=p.not_satisfied,
        rejected_alternatives=[
            f"{a.get('title')}: {a.get('reason')}" for a in p.rejected_alternatives if isinstance(a, dict)
        ][:5],
        image_count=len(imgs),
        image_alts=[i.alt or "" for i in imgs],
        url=store_url(product_path(p)),
    )


async def drop_facts(db: AsyncSession, d: Drop) -> DropFacts:
    pids = [it.product_id for it in d.items]
    names = {}
    if pids:
        names = dict((await db.execute(select(Product.id, Product.name).where(Product.id.in_(pids)))).all())
    return DropFacts(
        id=str(d.id),
        code=d.code,
        title=d.title,
        description=d.description,
        closes_at_text=to_local(d.closes_at).strftime("%H:%M %d/%m") if d.closes_at else None,
        expected_arrival_text=d.expected_arrival_date.strftime("%d/%m") if d.expected_arrival_date else None,
        deposit_pct=d.deposit_pct,
        items=[
            DropItemFacts(
                product_id=str(it.product_id),
                name=names.get(it.product_id, "Món trong đợt"),
                price_vnd=it.price_vnd,
                slots_total=it.slots_total,
                slots_left=(it.slots_total - it.slots_reserved) if it.slots_total is not None else None,
            )
            for it in d.items
        ],
        url=store_url(drop_path(d)),
    )


async def trial_notes(db: AsyncSession, p: Product, limit: int = 5) -> list[str]:
    if not p.candidate_id:
        return []
    rows = await db.execute(
        select(TrialNote.text)
        .where(TrialNote.candidate_id == p.candidate_id, TrialNote.text.is_not(None))
        .order_by(TrialNote.recorded_at.desc())
        .limit(limit)
    )
    return [t for t in rows.scalars() if t and t.strip()]


# ---- giọng của chị (f2) ------------------------------------------------------------------------------------------
# Không thêm cột: `rules` lưu [{kind, text}] với kind ∈ do | avoid | pronouns | sentence. Chuỗi trần (seed cũ) = "do".


def split_rules(rules: list[Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"do": [], "avoid": [], "pronouns": None, "sentence": None}
    for r in rules or []:
        if isinstance(r, str):
            out["do"].append(r)
        elif isinstance(r, dict) and r.get("text"):
            kind = r.get("kind", "do")
            if kind in ("pronouns", "sentence"):
                out[kind] = r["text"]
            elif kind in ("do", "avoid"):
                out[kind].append(r["text"])
    return out


def join_rules(*, do: list[str], avoid: list[str], pronouns: str | None, sentence: str | None) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    if pronouns:
        rules.append({"kind": "pronouns", "text": pronouns})
    if sentence:
        rules.append({"kind": "sentence", "text": sentence})
    rules += [{"kind": "do", "text": t} for t in do if t.strip()]
    rules += [{"kind": "avoid", "text": t} for t in avoid if t.strip()]
    return rules


async def active_voice(db: AsyncSession, *, create: bool = False) -> VoiceProfile | None:
    vp = await db.scalar(
        select(VoiceProfile).where(VoiceProfile.is_active.is_(True)).order_by(VoiceProfile.created_at).limit(1)
    )
    if vp is None and create:
        vp = VoiceProfile(name="Giọng của chị", style_summary=None, rules=[])
        db.add(vp)
        await db.flush()
    return vp


def voice_card(vp: VoiceProfile | None) -> VoiceCard:
    if vp is None:
        return VoiceCard()
    r = split_rules(vp.rules)
    return VoiceCard(
        style_summary=vp.style_summary,
        pronouns=r["pronouns"],
        sentence_style=r["sentence"],
        rules=r["do"],
        avoid=r["avoid"],
        vocabulary=[str(v) for v in vp.vocabulary],
        examples=[str(e) for e in vp.examples][:3],
    )


async def insight_lines(db: AsyncSession) -> list[str]:
    ins = await db.scalar(select(ContentInsight).order_by(ContentInsight.created_at.desc()).limit(1))
    if ins is None:
        return []
    return [f"{f.get('pattern')}: {f.get('recommendation')}" for f in ins.findings if isinstance(f, dict)][:3]


async def get_product(db: AsyncSession, product_id: uuid.UUID | str) -> Product | None:
    try:
        return await db.get(Product, uuid.UUID(str(product_id)))
    except ValueError:
        return None


async def get_drop(db: AsyncSession, drop_id: uuid.UUID | str) -> Drop | None:
    try:
        return await db.get(Drop, uuid.UUID(str(drop_id)))
    except ValueError:
        return None
