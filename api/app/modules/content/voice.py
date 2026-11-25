"""Giọng của chị (f2): chị dán bài cũ / ghi chú → AI rút hồ sơ giọng → mọi lần soạn đều dùng; chị xem và sửa."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core.errors import BadRequest
from app.core.timeutil import now_utc
from app.modules.content import facts
from app.modules.content.ai_io import VoiceLearnIn, VoiceLearnOut
from app.modules.content.models import VoiceProfile
from app.modules.content.service import ACTION_VOICE
from app.modules.control.models import User

MAX_SAMPLES = 20
MAX_SAMPLE_CHARS = 4000


def voice_view(vp: VoiceProfile) -> dict[str, Any]:
    r = facts.split_rules(vp.rules)
    return {
        "id": vp.id,
        "name": vp.name,
        "style_summary": vp.style_summary,
        "pronouns": r["pronouns"],
        "sentence_style": r["sentence"],
        "rules": r["do"],
        "avoid": r["avoid"],
        "vocabulary": [str(v) for v in vp.vocabulary],
        "examples": [str(e) for e in vp.examples],
        "samples_count": len(vp.sample_sources),
        "samples": [s.get("text", "")[:200] for s in vp.sample_sources if isinstance(s, dict)][-5:],
        "version": vp.version,
        "trained_at": vp.trained_at,
        "updated_at": vp.updated_at,
    }


def snapshot(vp: VoiceProfile) -> dict[str, Any]:
    return {
        "style_summary": vp.style_summary,
        "rules": list(vp.rules),
        "vocabulary": list(vp.vocabulary),
        "examples": list(vp.examples),
        "sample_sources": list(vp.sample_sources),
        "version": vp.version,
        "trained_at": vp.trained_at.isoformat() if vp.trained_at else None,
    }


async def learn(
    db: AsyncSession, samples: list[str], notes: str | None, user: User | None, spoken: list[str] | None = None
) -> control.ProposeOutcome:
    """Học từ bài cũ, ghi chú và lời chị nói (chép từ giọng nói ở trình duyệt, f2 «ghi âm của chị»)."""
    clean = [s.strip()[:MAX_SAMPLE_CHARS] for s in samples if s and s.strip()][:MAX_SAMPLES]
    said = [s.strip()[:MAX_SAMPLE_CHARS] for s in spoken or [] if s and s.strip()][:10]
    if not clean and not said and not (notes or "").strip():
        raise BadRequest("Chị dán ít nhất một bài cũ, nói vài câu hoặc ghi chú để AI học giọng.")
    vp = await facts.active_voice(db, create=True)
    assert vp is not None
    res = await ai.run(
        "content.learn_voice",
        VoiceLearnIn(samples=clean, notes=(notes or "").strip() or None, spoken=said, current=facts.voice_card(vp)),
        VoiceLearnOut,
    )
    out = res.output
    return await control.propose(
        ACTION_VOICE,
        "Cập nhật hồ sơ giọng viết của chị",
        {
            "voice_profile_id": str(vp.id),
            "profile": out.model_dump(),
            "samples": clean,
            "spoken": said,
            "notes": notes,
            "ai_run_id": str(res.run_id),
        },
        preview={"style_summary": out.style_summary, "pronouns": out.pronouns},
        db=db,
        summary=out.style_summary,
        rationale=f"Học từ {len(clean)} bài mẫu"
        + (f", {len(said)} đoạn chị nói" if said else "")
        + (" và ghi chú của chị" if notes else ""),
        ref_type="voice_profiles",
        ref_id=vp.id,
        ai_run_id=res.run_id,
    )


async def apply_learn(db: AsyncSession, payload: dict[str, Any]) -> control.HandlerResult:
    vp = await db.get(VoiceProfile, uuid.UUID(payload["voice_profile_id"]))
    if vp is None:
        raise BadRequest("Không tìm thấy hồ sơ giọng.")
    before = snapshot(vp)
    p = payload["profile"]
    vp.style_summary = p["style_summary"]
    vp.rules = facts.join_rules(do=p["rules"], avoid=p["avoid"], pronouns=p["pronouns"], sentence=p["sentence_style"])
    vp.vocabulary = list(p["vocabulary"])
    vp.examples = list(p["examples"])
    vp.sample_sources = [
        *vp.sample_sources,
        *[{"kind": "post", "text": s, "added_at": now_utc().isoformat()} for s in payload.get("samples") or []],
        *[{"kind": "voice", "text": s, "added_at": now_utc().isoformat()} for s in payload.get("spoken") or []],
    ][-50:]
    if payload.get("notes"):
        vp.sample_sources = [*vp.sample_sources, {"kind": "note", "text": payload["notes"]}][-50:]
    vp.version += 1
    vp.trained_at = now_utc()
    vp.ai_run_id = uuid.UUID(payload["ai_run_id"]) if payload.get("ai_run_id") else None
    await db.flush()
    return control.HandlerResult(
        result={"version": vp.version},
        undo={"voice_profile_id": str(vp.id), "before": before},
        summary=f"Hồ sơ giọng bản {vp.version}",
        ref_type="voice_profiles",
        ref_id=vp.id,
    )


async def undo_learn(db: AsyncSession, undo: dict[str, Any]) -> None:
    from datetime import datetime

    vp = await db.get(VoiceProfile, uuid.UUID(undo["voice_profile_id"]))
    if vp is None:
        return
    b = undo["before"]
    vp.style_summary = b["style_summary"]
    vp.rules, vp.vocabulary, vp.examples, vp.sample_sources = (
        b["rules"],
        b["vocabulary"],
        b["examples"],
        b["sample_sources"],
    )
    vp.version = b["version"]
    vp.trained_at = datetime.fromisoformat(b["trained_at"]) if b.get("trained_at") else None
    await db.flush()


async def edit(db: AsyncSession, data: dict[str, Any], user: User) -> VoiceProfile:
    """Chị sửa trực tiếp hồ sơ giọng (ghi lưu vết)."""
    vp = await facts.active_voice(db, create=True)
    assert vp is not None
    cur = facts.split_rules(vp.rules)
    if "style_summary" in data:
        vp.style_summary = (data["style_summary"] or "").strip() or None
    vp.rules = facts.join_rules(
        do=data.get("rules", cur["do"]),
        avoid=data.get("avoid", cur["avoid"]),
        pronouns=data.get("pronouns", cur["pronouns"]),
        sentence=data.get("sentence_style", cur["sentence"]),
    )
    if "vocabulary" in data:
        vp.vocabulary = [v.strip() for v in data["vocabulary"] if v.strip()]
    if "examples" in data:
        vp.examples = [v.strip() for v in data["examples"] if v.strip()]
    vp.version += 1
    await control.audit(
        db,
        "content.voice_edited",
        user=user,
        entity_type="voice_profiles",
        entity_id=vp.id,
        summary="Chị sửa hồ sơ giọng viết",
        data={"fields": sorted(data)},
    )
    await db.flush()
    return vp
