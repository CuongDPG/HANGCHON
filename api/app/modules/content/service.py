"""Nghiệp vụ xưởng nội dung: soạn bản theo kênh (f1), soát lời (f5), chờ duyệt → xếp lịch (f3/f4), viết lại, sửa tay.

Vòng đời một bản: placeholder `drafting` (khi sản phẩm lên web) → AI soạn + soát → `pending_review` (+ một bài
`planned` trên lịch + việc chờ duyệt `content.publish_post` nếu soát đạt) → chị duyệt → `scheduled` (bài `approved`)
→ job đăng tới giờ → `published`. Viết lại = bản mới (`parent_draft_id`, `version+1`), bản cũ `archived`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core.enums import Channel
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.timeutil import now_utc, to_local
from app.modules.catalog.models import Drop, DropItem, DropStatus, Product, ProductStatus
from app.modules.content import facts
from app.modules.content.ai_io import (
    ChannelDraftOut,
    CheckIn,
    CheckOut,
    ComposeIn,
    ComposeOut,
    DropFacts,
    ProductFacts,
    RewriteIn,
)
from app.modules.content.channels import (
    CHANNEL_GUIDE,
    DROP_CHANNELS,
    FORMAT_BY_CHANNEL,
    PRODUCT_CHANNELS,
    channel_label,
)
from app.modules.content.checks import build_findings, can_approve, status_of
from app.modules.content.models import CheckStatus, ContentDraft, DraftFormat, DraftStatus, PostStatus, ScheduledPost
from app.modules.content.schedule import next_slot, src_code
from app.modules.control.models import ApprovalItem, ApprovalStatus, User

log = logging.getLogger("app.content")

ACTION_COMPOSE = "content.compose_drafts"
ACTION_REWRITE = "content.rewrite_draft"
ACTION_CHECK = "content.check_copy"
ACTION_PUBLISH = "content.publish_post"
ACTION_RETRY = "content.retry_publish"
ACTION_SUGGEST = "content.suggest_post"
ACTION_VOICE = "content.learn_voice"
ACTION_INSIGHT = "content.save_insight"
ACTION_VIDEO_PLAN = "content.plan_video"
ACTION_VIDEO = "content.approve_video"
ACTION_LIVE = "content.approve_livestream"

PRESETS = {
    "shorter": ("Ngắn hơn", "Ngắn hơn: rút còn khoảng 60% độ dài, giữ lý do chọn và điều chưa ưng."),
    "warmer": ("Ấm hơn", "Ấm hơn: thân mật như nói với người quen, thêm một câu hỏi han, không sến."),
    "price": ("Thêm giá", "Thêm giá: ghi rõ giá bán đúng hồ sơ (và giá thường nếu có), đặt gần cuối bài."),
}

OPEN_POST = (PostStatus.PLANNED, PostStatus.APPROVED, PostStatus.FAILED)


STOPPED_MSG = "Món này đang ngừng bán. Chị mở bán lại rồi mới duyệt đăng bài."


async def product_stopped(db: AsyncSession, product_id: uuid.UUID | None) -> bool:
    """Món đã ngừng bán: bài của món không được duyệt / xếp lịch."""
    return bool(product_id) and await db.scalar(select(Product.status).where(Product.id == product_id)) == (
        ProductStatus.STOPPED
    )


def publish_key(draft_id: uuid.UUID) -> str:
    return f"publish:{draft_id}"


def compose_key(kind: str, ref: uuid.UUID) -> str:
    return f"compose:{kind}:{ref}"


def _uuid(v: Any) -> uuid.UUID:
    try:
        return uuid.UUID(str(v))
    except ValueError as e:
        raise NotFound("Không tìm thấy dữ liệu.") from e


# ---- ngữ cảnh ----------------------------------------------------------------------------------------------------


async def draft_context(
    db: AsyncSession, draft: ContentDraft
) -> tuple[Product | None, Drop | None, ProductFacts | None, DropFacts | None]:
    product = await db.get(Product, draft.product_id) if draft.product_id else None
    drop = await db.get(Drop, draft.drop_id) if draft.drop_id else None
    return (
        product,
        drop,
        await facts.product_facts_full(db, product) if product else None,
        await facts.drop_facts(db, drop) if drop else None,
    )


def ref_name(product: Product | None, drop: Drop | None) -> str:
    if drop is not None:
        return drop.title
    return product.name if product else "bài chung"


def draft_to_out(d: ContentDraft) -> ChannelDraftOut:
    scenes = [s for s in d.script if isinstance(s, dict) and "voiceover" in s]
    slides = [s for s in d.script if isinstance(s, dict) and "caption" in s and "voiceover" not in s]
    return ChannelDraftOut.model_validate(
        {
            "channel": d.channel.value,
            "title": d.title or "",
            "body": d.body,
            "hashtags": [str(h) for h in d.hashtags],
            "slides": [{"image_index": int(s.get("image_index", 0)), "caption": str(s["caption"])} for s in slides],
            "scenes": [
                {
                    "scene": int(s.get("scene", i + 1)),
                    "seconds": int(s.get("seconds", 5)),
                    "visual": str(s.get("visual", "")),
                    "voiceover": str(s["voiceover"]),
                    "on_screen_text": str(s.get("on_screen_text", "")),
                }
                for i, s in enumerate(scenes)
            ],
        }
    )


def script_of(out: ChannelDraftOut) -> list[dict[str, Any]]:
    if out.scenes:
        return [
            {**s.model_dump(), "seconds": max(1, min(15, s.seconds)), "scene": i + 1} for i, s in enumerate(out.scenes)
        ]
    return [s.model_dump() for s in out.slides]


def _hashtags(tags: list[str]) -> list[str]:
    out = []
    for t in tags:
        t = t.strip().replace(" ", "")
        if t:
            out.append(t if t.startswith("#") else f"#{t}")
    return list(dict.fromkeys(out))


# ---- soát lời (f5) -----------------------------------------------------------------------------------------------


async def run_check(
    *,
    channel: Channel,
    title: str | None,
    body: str,
    hashtags: list[str],
    script: list[dict[str, Any]],
    pf: ProductFacts | None,
    df: DropFacts | None,
    ai_generated: bool,
    previous: list[dict[str, Any]] | None = None,
    use_ai: bool = True,
) -> tuple[list[dict[str, Any]], CheckStatus]:
    from app.modules.content.checks import full_text

    ai_out: CheckOut | None = None
    if use_ai:
        scenes = [s for s in script if "voiceover" in s]
        slides = [s for s in script if "caption" in s and "voiceover" not in s]
        try:
            res = await ai.run(
                "content.check",
                CheckIn(channel=channel.value, text=full_text(body, title, scenes, slides), product=pf, drop=df),
                CheckOut,
            )
            ai_out = res.output
        except ai.AIError as e:  # luật vẫn chạy; AI soát lỗi không chặn chị
            log.warning("AI soát lời lỗi: %s", e)
    findings = build_findings(
        channel=channel,
        title=title,
        body=body,
        hashtags=hashtags,
        script=script,
        product=pf,
        drop=df,
        ai_generated=ai_generated,
        ai=ai_out,
        previous=previous,
    )
    return findings, status_of(findings)


# ---- soạn (f1) ---------------------------------------------------------------------------------------------------


def channels_for(kind: str) -> list[tuple[Channel, DraftFormat]]:
    return DROP_CHANNELS if kind == "drop" else PRODUCT_CHANNELS


async def ensure_placeholders(db: AsyncSession, *, product: Product | None = None, drop: Drop | None = None) -> int:
    """Tạo bản `drafting` cho từng kênh (idempotent): đã có bản nào (chưa archived) thì không làm gì."""
    if drop is not None:
        cond = ContentDraft.drop_id == drop.id
        kind, ref_product, ref_drop = "drop", None, drop.id
    elif product is not None:
        cond = (ContentDraft.product_id == product.id) & ContentDraft.drop_id.is_(None)
        kind, ref_product, ref_drop = "product", product.id, None
    else:
        return 0
    exists = await db.scalar(select(ContentDraft.id).where(cond, ContentDraft.status != DraftStatus.ARCHIVED).limit(1))
    if exists:
        return 0
    for ch, fmt in channels_for(kind):
        db.add(
            ContentDraft(product_id=ref_product, drop_id=ref_drop, channel=ch, format=fmt, status=DraftStatus.DRAFTING)
        )
    await db.flush()
    return len(channels_for(kind))


async def compose(
    db: AsyncSession,
    *,
    product: Product | None = None,
    drop: Drop | None = None,
    channels: list[Channel] | None = None,
    instruction: str | None = None,
    slot_at: datetime | None = None,
    user: User | None = None,
) -> control.ProposeOutcome:
    """AI soạn bản cho các kênh, soát từng bản, rồi đề xuất `content.compose_drafts` (mặc định AI tự làm)."""
    if product is None and drop is None:
        raise BadRequest("Cần chọn một sản phẩm hoặc một đợt mở bán.")
    kind = "drop" if drop is not None else "product"
    allowed = [c for c, _ in channels_for(kind)]
    chans = [c for c in (channels or allowed) if c in allowed] or allowed
    pf = await facts.product_facts_full(db, product) if product is not None else None  # kèm ghi chú thử, cảnh báo
    df = await facts.drop_facts(db, drop) if drop is not None else None
    vp = await facts.active_voice(db)
    res = await ai.run(
        "content.compose",
        ComposeIn(
            kind=kind,
            product=pf,
            drop=df,
            voice=facts.voice_card(vp),
            channels=[c.value for c in chans],
            channel_guides={c.value: CHANNEL_GUIDE[c.value] for c in chans},
            insights=await facts.insight_lines(db),
            instruction=instruction,
        ),
        ComposeOut,
    )
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d in res.output.drafts:
        if d.channel in seen or Channel(d.channel) not in chans:
            continue
        seen.add(d.channel)
        d.hashtags = _hashtags(d.hashtags)
        script = script_of(d)
        findings, status = await run_check(
            channel=Channel(d.channel),
            title=d.title,
            body=d.body,
            hashtags=d.hashtags,
            script=script,
            pf=pf,
            df=df,
            ai_generated=True,
        )
        items.append(
            {
                "channel": d.channel,
                "title": d.title,
                "body": d.body,
                "hashtags": d.hashtags,
                "script": script,
                "check_findings": findings,
                "check_status": status.value,
            }
        )
    if not items:
        raise ai.AIOutputInvalid("AI không trả bản nào cho các kênh đã chọn.")
    name = ref_name(product, drop)
    ref = drop.id if drop is not None else product.id  # type: ignore[union-attr]
    payload = {
        "kind": kind,
        "product_id": str(product.id) if product is not None and drop is None else None,
        "drop_id": str(drop.id) if drop is not None else None,
        "voice_profile_id": str(vp.id) if vp else None,
        "ai_run_id": str(res.run_id),
        "slot_at": slot_at.isoformat() if slot_at else None,
        "user_id": str(user.id) if user else None,
        "drafts": items,
    }
    return await control.propose(
        ACTION_COMPOSE,
        f"Soạn {len(items)} bản cho {name}",
        payload,
        preview={"name": name, "channels": [channel_label(i["channel"]) for i in items]},
        db=db,
        summary=", ".join(channel_label(i["channel"]) for i in items),
        rationale="Soạn từ hồ sơ chọn (lý do chọn, điều chưa ưng, ghi chú thử hàng) theo giọng của chị.",
        ref_type="drops" if drop is not None else "products",
        ref_id=ref,
        ai_run_id=res.run_id,
        dedupe_key=None if slot_at else compose_key(kind, ref),
    )


async def apply_compose(db: AsyncSession, payload: dict[str, Any]) -> list[ContentDraft]:
    """Hàm thực thi `content.compose_drafts`: điền bản `drafting` (hoặc tạo mới), xếp lịch, đưa vào hàng chờ duyệt."""
    product_id = _uuid(payload["product_id"]) if payload.get("product_id") else None
    drop_id = _uuid(payload["drop_id"]) if payload.get("drop_id") else None
    slot_at = datetime.fromisoformat(payload["slot_at"]) if payload.get("slot_at") else None
    out: list[ContentDraft] = []
    for item in payload["drafts"]:
        ch = Channel(item["channel"])
        row = None
        if slot_at is None:
            q = select(ContentDraft).where(ContentDraft.channel == ch, ContentDraft.status == DraftStatus.DRAFTING)
            q = (
                q.where(ContentDraft.drop_id == drop_id)
                if drop_id
                else q.where(ContentDraft.product_id == product_id, ContentDraft.drop_id.is_(None))
            )
            row = await db.scalar(q.order_by(ContentDraft.created_at).limit(1))
        if row is None:
            row = ContentDraft(product_id=product_id, drop_id=drop_id, channel=ch)
            db.add(row)
        fmt = dict(DROP_CHANNELS).get(ch) if drop_id else FORMAT_BY_CHANNEL.get(ch)
        row.format = fmt or DraftFormat.POST
        row.title = item.get("title")
        row.body = item.get("body") or ""
        row.hashtags = list(item.get("hashtags") or [])
        row.script = list(item.get("script") or [])
        row.check_findings = list(item.get("check_findings") or [])
        row.check_status = CheckStatus(item.get("check_status") or status_of(row.check_findings))
        row.ai_generated = True
        row.ai_label_required = True
        row.status = DraftStatus.PENDING_REVIEW
        row.voice_profile_id = _uuid(payload["voice_profile_id"]) if payload.get("voice_profile_id") else None
        row.ai_run_id = _uuid(payload["ai_run_id"]) if payload.get("ai_run_id") else None
        row.created_by_id = _uuid(payload["user_id"]) if payload.get("user_id") else None
        await db.flush()
        await submit(db, row, slot_at=slot_at)
        out.append(row)
    return out


async def compose_pending(db: AsyncSession, *, limit: int = 10) -> int:
    """Quét bản `drafting` chưa soạn (do sự kiện tạo) và soạn. Bỏ qua khi việc soạn đang tắt hoặc đang chờ chị duyệt."""
    if await control.get_level(db, ACTION_COMPOSE) == control.AutonomyLevel.OFF:
        return 0
    rows = (
        await db.execute(
            select(ContentDraft.product_id, ContentDraft.drop_id, func.array_agg(ContentDraft.channel))
            .where(ContentDraft.status == DraftStatus.DRAFTING)
            .group_by(ContentDraft.product_id, ContentDraft.drop_id)
            .limit(limit)
        )
    ).all()
    done = 0
    for product_id, drop_id, chans in rows:
        kind, ref = ("drop", drop_id) if drop_id else ("product", product_id)
        if ref is None:
            continue
        waiting = await db.scalar(
            select(ApprovalItem.id).where(
                ApprovalItem.action == ACTION_COMPOSE,
                ApprovalItem.dedupe_key == compose_key(kind, ref),
                ApprovalItem.status == ApprovalStatus.PENDING,
            )
        )
        if waiting:
            continue
        product = await db.get(Product, product_id) if product_id else None
        drop = await db.get(Drop, drop_id) if drop_id else None
        if product is None and drop is None:
            continue
        if drop is not None and drop.status not in (DropStatus.SCHEDULED, DropStatus.OPEN):
            # đợt đã đóng / huỷ trước khi kịp soạn: bài báo mở đợt không còn ý nghĩa → cất đi, không xếp lịch
            await db.execute(
                update(ContentDraft)
                .where(ContentDraft.drop_id == drop.id, ContentDraft.status == DraftStatus.DRAFTING)
                .values(status=DraftStatus.ARCHIVED)
            )
            continue
        try:
            async with db.begin_nested():
                await compose(db, product=product, drop=drop, channels=[Channel(c) for c in chans])
            done += 1
        except ai.AIError as e:
            log.warning("Soạn bài cho %s %s lỗi: %s", kind, ref, e)
    return done


# ---- lịch + hàng chờ duyệt ---------------------------------------------------------------------------------------


async def open_post(db: AsyncSession, draft_id: uuid.UUID) -> ScheduledPost | None:
    return await db.scalar(
        select(ScheduledPost)
        .where(ScheduledPost.draft_id == draft_id, ScheduledPost.status.in_(OPEN_POST))
        .order_by(ScheduledPost.created_at.desc())
        .limit(1)
    )


async def latest_post(db: AsyncSession, draft_id: uuid.UUID) -> ScheduledPost | None:
    return await db.scalar(
        select(ScheduledPost)
        .where(ScheduledPost.draft_id == draft_id, ScheduledPost.status != PostStatus.CANCELLED)
        .order_by(ScheduledPost.created_at.desc())
        .limit(1)
    )


async def ensure_post(db: AsyncSession, draft: ContentDraft, *, slot_at: datetime | None = None) -> ScheduledPost:
    post = await open_post(db, draft.id)
    if post is None:
        at = slot_at or await next_slot(db, draft.channel)
        post = ScheduledPost(
            id=uuid.uuid4(),
            draft_id=draft.id,
            channel=draft.channel,
            product_id=draft.product_id,
            scheduled_at=at,
            status=PostStatus.PLANNED,
        )
        db.add(post)
        await db.flush()
    product = await db.get(Product, draft.product_id) if draft.product_id else None
    drop = await db.get(Drop, draft.drop_id) if draft.drop_id else None
    path = facts.drop_path(drop) if drop else (facts.product_path(product) if product else "/")
    draft.link_url = facts.store_url(path, src_code(post))
    return post


def draft_preview(draft: ContentDraft, post: ScheduledPost, name: str) -> dict[str, Any]:
    return {
        "kind": "content_draft",
        "name": name,
        "channel": draft.channel.value,
        "channel_label": channel_label(draft.channel),
        "title": draft.title,
        "body": draft.body,
        "hashtags": draft.hashtags,
        "script": draft.script,
        "link_url": draft.link_url,
        "scheduled_at": post.scheduled_at.isoformat(),
        "checks": [
            {"label": f["label"], "ok": f.get("ok"), "overridden": f.get("overridden", False)}
            for f in draft.check_findings
        ],
        "ai_generated": draft.ai_generated,
        "tiktok_draft": draft.channel == Channel.TIKTOK,
    }


async def submit(
    db: AsyncSession, draft: ContentDraft, *, slot_at: datetime | None = None
) -> control.ProposeOutcome | None:
    """Xếp bản vào lịch (bài `planned`) và — nếu soát đạt — đưa vào hàng chờ duyệt đăng. Soát chưa đạt thì rút khỏi hàng chờ.
    Món đã ngừng bán: bản nháp giữ nguyên, không lên lịch, không vào hàng chờ."""
    if await product_stopped(db, draft.product_id):
        await control.cancel_pending(db, action=ACTION_PUBLISH, dedupe_key=publish_key(draft.id))
        return None
    post = await ensure_post(db, draft, slot_at=slot_at)
    if not can_approve(draft.check_status):
        await control.cancel_pending(db, action=ACTION_PUBLISH, dedupe_key=publish_key(draft.id))
        return None
    product = await db.get(Product, draft.product_id) if draft.product_id else None
    drop = await db.get(Drop, draft.drop_id) if draft.drop_id else None
    name = ref_name(product, drop)
    label = channel_label(draft.channel)
    when = to_local(post.scheduled_at).strftime("%H:%M %d/%m")
    verb = "Đẩy bản nháp TikTok" if draft.channel == Channel.TIKTOK else f"Đăng {label}"
    return await control.propose(
        ACTION_PUBLISH,
        f"{verb}: {name}",
        {"draft_id": str(draft.id), "scheduled_post_id": str(post.id)},
        preview=draft_preview(draft, post, name),
        db=db,
        summary=f"Dự kiến {when}",
        rationale="Đã soát số liệu, lời quảng cáo và nhãn AI trước khi tới tay chị.",
        ref_type="content_drafts",
        ref_id=draft.id,
        ai_run_id=draft.ai_run_id,
        dedupe_key=publish_key(draft.id),
        ai_generated=draft.ai_generated,
    )


async def apply_publish_approval(
    db: AsyncSession, payload: dict[str, Any], item: ApprovalItem | None
) -> control.HandlerResult:
    """Hàm thực thi `content.publish_post`: bài được phép đăng → `approved`, job đăng khi tới giờ."""
    draft = await db.get(ContentDraft, _uuid(payload["draft_id"]))
    post = await db.get(ScheduledPost, _uuid(payload["scheduled_post_id"]))
    if draft is None or post is None or draft.status == DraftStatus.ARCHIVED or post.status == PostStatus.CANCELLED:
        raise Conflict("Bản này đã được thay bằng bản mới hoặc lịch đã huỷ.", code="draft_stale")
    if await product_stopped(db, post.product_id or draft.product_id):
        raise Conflict(STOPPED_MSG, code="product_stopped")
    edited = {k: payload[k] for k in ("title", "body", "hashtags") if k in payload}
    if edited:  # chị «sửa rồi duyệt» ngay trong hàng chờ: soát lại bằng luật
        for k, v in edited.items():
            setattr(draft, k, _hashtags(v) if k == "hashtags" else v)
        _, _, pf, df = await draft_context(db, draft)
        draft.check_findings, draft.check_status = await run_check(
            channel=draft.channel,
            title=draft.title,
            body=draft.body,
            hashtags=draft.hashtags,
            script=draft.script,
            pf=pf,
            df=df,
            ai_generated=draft.ai_generated,
            previous=draft.check_findings,
            use_ai=False,
        )
    if not can_approve(draft.check_status):
        raise Conflict(
            "Còn mục soát lời chưa đạt — chị sửa hoặc xác nhận bỏ qua có lý do trước khi duyệt.", code="check_failed"
        )
    if payload.get("scheduled_at"):
        post.scheduled_at = datetime.fromisoformat(str(payload["scheduled_at"]))
    if post.status in (PostStatus.PLANNED, PostStatus.FAILED):
        post.status = PostStatus.APPROVED
        post.attempts = 0
        post.error = None
    post.approval_item_id = item.id if item else None
    draft.status = DraftStatus.SCHEDULED
    draft.approval_item_id = item.id if item else None
    await db.flush()
    when = to_local(post.scheduled_at).strftime("%H:%M %d/%m")
    return control.HandlerResult(
        result={"scheduled_post_id": str(post.id), "scheduled_at": post.scheduled_at.isoformat()},
        undo={"post_id": str(post.id), "draft_id": str(draft.id)},
        summary=f"Xếp lịch {channel_label(draft.channel)} lúc {when}",
        ref_type="scheduled_posts",
        ref_id=post.id,
    )


async def undo_publish_approval(db: AsyncSession, undo: dict[str, Any]) -> None:
    post = await db.get(ScheduledPost, _uuid(undo["post_id"]))
    draft = await db.get(ContentDraft, _uuid(undo["draft_id"]))
    if post is None or draft is None:
        return
    if post.status != PostStatus.APPROVED:
        raise Conflict("Bài đã đăng hoặc đang đăng, không hoàn tác được.", code="already_published")
    post.status = PostStatus.PLANNED
    draft.status = DraftStatus.PENDING_REVIEW
    await db.flush()
    await submit(db, draft)


async def pending_item(db: AsyncSession, draft_id: uuid.UUID) -> ApprovalItem | None:
    return await db.scalar(
        select(ApprovalItem).where(
            ApprovalItem.action == ACTION_PUBLISH,
            ApprovalItem.dedupe_key == publish_key(draft_id),
            ApprovalItem.status.in_((ApprovalStatus.PENDING, ApprovalStatus.FAILED)),
        )
    )


async def approve_draft(
    db: AsyncSession, draft: ContentDraft, user: User, *, scheduled_at: datetime | None = None
) -> ScheduledPost:
    """Nút «Duyệt, xếp lịch» ở xưởng: duyệt qua hàng chờ chung (ghi nhật ký + lưu vết như duyệt ở /desk/duyet)."""
    if draft.status in (DraftStatus.ARCHIVED, DraftStatus.PUBLISHED):
        raise Conflict("Bản này đã đăng hoặc đã được thay.", code="draft_stale")
    if draft.status == DraftStatus.DRAFTING:
        raise Conflict("AI đang soạn bản này, chị đợi chút nhé.", code="drafting")
    if await product_stopped(db, draft.product_id):
        raise Conflict(STOPPED_MSG, code="product_stopped")
    if not can_approve(draft.check_status):
        raise Conflict(
            "Còn mục soát lời chưa đạt — chị sửa hoặc xác nhận bỏ qua có lý do trước khi duyệt.", code="check_failed"
        )
    post = await ensure_post(db, draft)
    if scheduled_at is not None:
        if scheduled_at < now_utc():
            raise BadRequest("Giờ đăng phải sau bây giờ.")
        post.scheduled_at = scheduled_at
    if draft.status == DraftStatus.SCHEDULED and post.status == PostStatus.APPROVED:
        return post
    item = await pending_item(db, draft.id)
    if item is None:
        out = await submit(db, draft)
        if out is None:
            raise Conflict("Bản này chưa vào được hàng chờ duyệt.", code="not_submitted")
        if out.status == "applied":
            return post
        if out.status == "blocked":
            raise Conflict("Chị đang tắt «Đăng bài lên mạng xã hội» ở Mức tự chủ.", code="action_off")
        if out.status == "failed":
            raise Conflict(out.error or "Không duyệt được.", code="approve_failed")
        item_id = out.item_id
    else:
        item_id = item.id
    assert item_id is not None
    done = await control.approve(db, item_id, user)
    if done.status == ApprovalStatus.FAILED:
        raise Conflict(done.error or "Không duyệt được.", code="approve_failed")
    await db.refresh(post)
    return post


# ---- viết lại, sửa tay, bỏ qua mục soát ---------------------------------------------------------------------------


async def rewrite(
    db: AsyncSession,
    draft: ContentDraft,
    *,
    preset: str | None = None,
    instruction: str | None = None,
    user: User | None = None,
) -> tuple[ContentDraft, str]:
    """Viết lại nhanh (Ngắn hơn / Ấm hơn / Thêm giá / ý của chị). Trả (bản hiện hành, trạng thái đề xuất)."""
    if draft.status in (DraftStatus.ARCHIVED, DraftStatus.PUBLISHED, DraftStatus.DRAFTING):
        raise Conflict("Bản này không viết lại được (đã đăng, đã thay hoặc AI đang soạn).", code="draft_locked")
    if preset:
        if preset not in PRESETS:
            raise BadRequest("Kiểu viết lại không hợp lệ.")
        label, instr = PRESETS[preset]
    else:
        instr = (instruction or "").strip()
        if not instr:
            raise BadRequest("Chị nói hoặc gõ ý muốn sửa nhé.")
        label = "theo ý chị"
    product, drop, pf, df = await draft_context(db, draft)
    vp = await facts.active_voice(db)
    res = await ai.run(
        "content.rewrite",
        RewriteIn(
            channel=draft.channel.value,
            current=draft_to_out(draft),
            instruction=instr,
            product=pf,
            drop=df,
            voice=facts.voice_card(vp),
            channel_guide=CHANNEL_GUIDE.get(draft.channel.value, ""),
        ),
        ChannelDraftOut,
    )
    out = res.output
    out.hashtags = _hashtags(out.hashtags)
    script = script_of(out) or list(draft.script)
    findings, status = await run_check(
        channel=draft.channel,
        title=out.title,
        body=out.body,
        hashtags=out.hashtags,
        script=script,
        pf=pf,
        df=df,
        ai_generated=True,
    )
    o = await control.propose(
        ACTION_REWRITE,
        f"Viết lại bản {channel_label(draft.channel)} ({label}): {ref_name(product, drop)}",
        {
            "draft_id": str(draft.id),
            "instruction": instr,
            "ai_run_id": str(res.run_id),
            "user_id": str(user.id) if user else None,
            "draft": {
                "title": out.title,
                "body": out.body,
                "hashtags": out.hashtags,
                "script": script,
                "check_findings": findings,
                "check_status": status.value,
            },
        },
        preview={"before": draft.body, "after": out.body, "channel_label": channel_label(draft.channel)},
        db=db,
        rationale=f"Chị yêu cầu: {instr}",
        ref_type="content_drafts",
        ref_id=draft.id,
        ai_run_id=res.run_id,
        dedupe_key=f"rewrite:{draft.id}",
    )
    if o.status == "applied" and o.result:
        new = await db.get(ContentDraft, _uuid(o.result["draft_id"]))
        if new is not None:
            return new, o.status
    return draft, o.status


async def apply_rewrite(db: AsyncSession, payload: dict[str, Any]) -> ContentDraft:
    old = await db.get(ContentDraft, _uuid(payload["draft_id"]))
    if old is None or old.status in (DraftStatus.ARCHIVED, DraftStatus.PUBLISHED):
        raise Conflict("Bản gốc đã đăng hoặc đã được thay.", code="draft_stale")
    d = payload["draft"]
    new = ContentDraft(
        product_id=old.product_id,
        drop_id=old.drop_id,
        channel=old.channel,
        format=old.format,
        status=DraftStatus.PENDING_REVIEW,
        title=d.get("title"),
        body=d.get("body") or "",
        hashtags=list(d.get("hashtags") or []),
        script=list(d.get("script") or []),
        media_asset_ids=list(old.media_asset_ids),
        link_url=old.link_url,
        voice_profile_id=old.voice_profile_id,
        parent_draft_id=old.id,
        version=old.version + 1,
        check_findings=list(d.get("check_findings") or []),
        check_status=CheckStatus(d.get("check_status") or "unchecked"),
        ai_generated=True,
        ai_label_required=True,
        feedback_note=old.feedback_note,
        ai_run_id=_uuid(payload["ai_run_id"]) if payload.get("ai_run_id") else None,
        created_by_id=_uuid(payload["user_id"]) if payload.get("user_id") else None,
    )
    db.add(new)
    old.status = DraftStatus.ARCHIVED
    await db.flush()
    post = await open_post(db, old.id)
    if post is not None:  # giữ chỗ trên lịch, nhưng bản mới cần chị duyệt lại
        post.draft_id = new.id
        if post.status == PostStatus.APPROVED:
            post.status = PostStatus.PLANNED
    await control.cancel_pending(db, action=ACTION_PUBLISH, dedupe_key=publish_key(old.id))
    await db.flush()
    await submit(db, new)
    return new


async def edit_draft(db: AsyncSession, draft: ContentDraft, data: dict[str, Any], user: User) -> ContentDraft:
    """Sửa tay. Soát lại; bản đã duyệt mà sửa thì quay về chờ duyệt."""
    if draft.status in (DraftStatus.ARCHIVED, DraftStatus.PUBLISHED, DraftStatus.DRAFTING):
        raise Conflict("Bản này không sửa được (đã đăng, đã thay hoặc AI đang soạn).", code="draft_locked")
    changed = {}
    for k in ("title", "body", "hashtags", "script"):
        if k in data and data[k] is not None:
            v = _hashtags(data[k]) if k == "hashtags" else data[k]
            if v != getattr(draft, k):
                changed[k] = v
                setattr(draft, k, v)
    if not changed:
        return draft
    _, _, pf, df = await draft_context(db, draft)
    findings, status = await run_check(
        channel=draft.channel,
        title=draft.title,
        body=draft.body,
        hashtags=draft.hashtags,
        script=draft.script,
        pf=pf,
        df=df,
        ai_generated=draft.ai_generated,
        previous=draft.check_findings,
    )
    await control.propose(
        ACTION_CHECK,
        f"Soát lại bản {channel_label(draft.channel)} sau khi chị sửa",
        {"draft_id": str(draft.id), "check_findings": findings, "check_status": status.value},
        preview={"checks": [{"label": f["label"], "ok": f["ok"]} for f in findings]},
        db=db,
        ref_type="content_drafts",
        ref_id=draft.id,
    )
    post = await open_post(db, draft.id)
    if draft.status in (DraftStatus.APPROVED, DraftStatus.SCHEDULED, DraftStatus.RETURNED):
        draft.status = DraftStatus.PENDING_REVIEW
        if post is not None and post.status == PostStatus.APPROVED:
            post.status = PostStatus.PLANNED
    await control.audit(
        db,
        "content.draft_edited",
        user=user,
        entity_type="content_drafts",
        entity_id=draft.id,
        summary=f"Sửa tay bản {channel_label(draft.channel)}",
        data={"fields": sorted(changed)},
    )
    await db.flush()
    await submit(db, draft)
    return draft


async def apply_check(db: AsyncSession, payload: dict[str, Any]) -> None:
    draft = await db.get(ContentDraft, _uuid(payload["draft_id"]))
    if draft is None:
        return
    draft.check_findings = list(payload["check_findings"])
    draft.check_status = CheckStatus(payload["check_status"])
    await db.flush()


async def recheck(db: AsyncSession, draft: ContentDraft) -> ContentDraft:
    _, _, pf, df = await draft_context(db, draft)
    draft.check_findings, draft.check_status = await run_check(
        channel=draft.channel,
        title=draft.title,
        body=draft.body,
        hashtags=draft.hashtags,
        script=draft.script,
        pf=pf,
        df=df,
        ai_generated=draft.ai_generated,
        previous=draft.check_findings,
    )
    await db.flush()
    if draft.status == DraftStatus.PENDING_REVIEW:
        await submit(db, draft)
    return draft


async def override_check(db: AsyncSession, draft: ContentDraft, key: str, reason: str, user: User) -> ContentDraft:
    """Chị xác nhận bỏ qua một mục soát chưa đạt, bắt buộc có lý do (ghi lưu vết)."""
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise BadRequest("Chị ghi lý do bỏ qua (ít nhất vài chữ) để lưu vết.")
    findings = [dict(f) for f in draft.check_findings]
    target = next((f for f in findings if f.get("key") == key), None)
    if target is None or target.get("ok"):
        raise BadRequest("Mục này không cần bỏ qua.")
    target.update(overridden=True, override_reason=reason, overridden_by=user.name, overridden_at=now_utc().isoformat())
    draft.check_findings = findings
    draft.check_status = status_of(findings)
    await control.audit(
        db,
        "content.check_override",
        user=user,
        entity_type="content_drafts",
        entity_id=draft.id,
        summary=f"Bỏ qua mục soát «{target.get('label')}»: {reason}",
        data={"key": key, "detail": target.get("detail"), "reason": reason},
    )
    await db.flush()
    await submit(db, draft)
    return draft


async def handle_returned(db: AsyncSession, item: ApprovalItem, note: str, user: User | None) -> None:
    """Chị trả lại bài trong hàng chờ kèm lời nhắn → AI viết lại theo lời nhắn và đưa vào hàng chờ lần nữa."""
    draft = await db.get(ContentDraft, _uuid(item.payload.get("draft_id")))
    if draft is None or draft.status in (DraftStatus.ARCHIVED, DraftStatus.PUBLISHED):
        return
    draft.feedback_note = note
    draft.status = DraftStatus.RETURNED
    await db.flush()
    await rewrite(db, draft, instruction=f"Chị trả lại với lời nhắn: {note}", user=user)


# ---- đọc cho giao diện -------------------------------------------------------------------------------------------


async def current_drafts(db: AsyncSession, *, product_id: uuid.UUID | None = None, drop_id: uuid.UUID | None = None):
    q = select(ContentDraft).where(ContentDraft.status != DraftStatus.ARCHIVED)
    q = (
        q.where(ContentDraft.drop_id == drop_id)
        if drop_id
        else q.where(ContentDraft.product_id == product_id, ContentDraft.drop_id.is_(None))
    )
    return list((await db.execute(q.order_by(ContentDraft.created_at))).scalars())


def draft_counts(drafts: list[ContentDraft]) -> dict[str, int]:
    ok = (DraftStatus.APPROVED, DraftStatus.SCHEDULED, DraftStatus.PUBLISHED)
    return {
        "total": len(drafts),
        "approved": sum(d.status in ok for d in drafts),
        "drafting": sum(d.status == DraftStatus.DRAFTING for d in drafts),
        "needs_fix": sum(d.status == DraftStatus.PENDING_REVIEW and not can_approve(d.check_status) for d in drafts),
        "pending": sum(d.status in (DraftStatus.PENDING_REVIEW, DraftStatus.RETURNED) for d in drafts),
    }


async def studio_items(db: AsyncSession) -> list[dict[str, Any]]:
    """Danh sách cho màn hình xưởng: mọi sản phẩm chưa lưu trữ (kể cả món vừa chọn, trang website còn chờ đăng —
    Website là kênh đầu tiên) hoặc có bản nháp, đợt đang mở / có bản nháp."""
    has_draft = select(ContentDraft.product_id).where(
        ContentDraft.drop_id.is_(None), ContentDraft.product_id.is_not(None)
    )
    products = list(
        (
            await db.execute(
                select(Product)
                .where(or_(Product.status != ProductStatus.ARCHIVED, Product.id.in_(has_draft)))
                .order_by(Product.published_at.desc().nulls_last(), Product.created_at.desc())
                .limit(100)
            )
        ).scalars()
    )
    drop_has = select(ContentDraft.drop_id).where(ContentDraft.drop_id.is_not(None))
    drops = list(
        (
            await db.execute(
                select(Drop)
                .where(or_(Drop.status.in_((DropStatus.OPEN, DropStatus.SCHEDULED)), Drop.id.in_(drop_has)))
                .order_by(Drop.opens_at.desc().nulls_last())
                .limit(20)
            )
        ).scalars()
    )
    items: list[dict[str, Any]] = []
    for d in drops:
        ds = await current_drafts(db, drop_id=d.id)
        items.append(
            {
                "kind": "drop",
                "id": d.id,
                "name": d.title,
                "subtitle": f"Đợt {d.code}",
                "image_url": None,
                "status": d.status.value,
                **draft_counts(ds),
                "updated_at": max([x.updated_at for x in ds], default=d.updated_at),
            }
        )
    for p in products:
        ds = await current_drafts(db, product_id=p.id)
        keys = facts.image_keys(p)
        items.append(
            {
                "kind": "product",
                "id": p.id,
                "name": p.name,
                "subtitle": p.subtitle,
                "image_url": facts.file_url(keys[0]) if keys else None,
                "status": p.status.value,
                **draft_counts(ds),
                "updated_at": max([x.updated_at for x in ds], default=p.updated_at),
            }
        )
    return items


async def open_drop_for(db: AsyncSession, product_id: uuid.UUID) -> Drop | None:
    return await db.scalar(
        select(Drop)
        .join(DropItem, DropItem.drop_id == Drop.id)
        .where(DropItem.product_id == product_id, Drop.status == DropStatus.OPEN)
        .order_by(Drop.closes_at)
        .limit(1)
    )
