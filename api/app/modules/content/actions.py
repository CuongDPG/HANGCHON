"""Hành động của xưởng nội dung trong cơ chế giám sát. Mặc định thận trọng: việc nội bộ AI tự làm, thứ khách nhìn
thấy (đăng bài, video, kịch bản lên sóng) chờ chị duyệt."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app import control
from app.core.timeutil import local_day_bounds_utc
from app.modules.content import livestream, planner, publishing, service, video, voice
from app.modules.content.models import LivestreamScript, PostStatus, ScheduledPost, ScriptStatus
from app.modules.control.models import ApprovalItem, ApprovalStatus

G = "Nội dung"

control.register_action(
    service.ACTION_COMPOSE,
    "Soạn bài cho từng kênh",
    G,
    default="auto",
    description="Khi sản phẩm lên web hoặc mở đợt, AI soạn bản Facebook, Instagram, Threads, TikTok, Zalo (chưa đăng).",
)
control.register_action(
    service.ACTION_REWRITE,
    "Viết lại bản nháp theo ý chị",
    G,
    default="auto",
    description="Ngắn hơn, ấm hơn, thêm giá hoặc theo lời chị nói. Bản mới vẫn chờ duyệt trước khi đăng.",
)
control.register_action(
    service.ACTION_CHECK,
    "Soát lời quảng cáo",
    G,
    default="auto",
    description="Kiểm số liệu với hồ sơ, lời nói quá công dụng, nhãn nội dung AI.",
)
control.register_action(
    service.ACTION_PUBLISH,
    "Đăng bài lên mạng xã hội",
    G,
    default="ask",
    customer_facing=True,
    description="Bài đã duyệt được đăng tự động đúng giờ (TikTok: đẩy bản nháp vào app để chị bấm đăng).",
)
control.register_action(
    service.ACTION_RETRY,
    "Đăng lại bài bị lỗi",
    G,
    default="ask",
    customer_facing=True,
    description="Bài đã thử đăng tự động 3 lần vẫn lỗi.",
)
control.register_action(
    service.ACTION_SUGGEST,
    "Gợi ý bài lấp ô trống trên lịch",
    G,
    default="ask",
    description="AI đề xuất ý bài cho ngày còn trống; chị gật thì AI mới soạn.",
)
control.register_action(
    service.ACTION_VOICE,
    "Học giọng viết của chị",
    G,
    default="auto",
    description="Rút cách xưng hô, độ dài câu, từ hay dùng, điều tránh từ bài cũ của chị.",
)
control.register_action(
    service.ACTION_INSIGHT,
    "Rút kinh nghiệm từ số liệu bài",
    G,
    default="auto",
    description="Bài nào ra đơn, kiểu bài/giờ đăng nên làm tiếp.",
)
control.register_action(
    service.ACTION_VIDEO_PLAN,
    "Lập kế hoạch dựng video ngắn",
    G,
    default="auto",
    description="Chọn đoạn từ clip thử hàng, phụ đề từng cảnh, gợi ý nhạc; dựng file nếu máy có ffmpeg.",
)
control.register_action(
    service.ACTION_VIDEO,
    "Duyệt video ngắn AI dựng",
    G,
    default="ask",
    customer_facing=True,
    description="Video dựng từ clip của chị, chờ chị xem trước khi gắn vào bài.",
)
control.register_action(
    service.ACTION_LIVE,
    "Duyệt kịch bản livestream",
    G,
    default="ask",
    customer_facing=True,
    description="Dàn ý, thứ tự món, câu khách hay hỏi cho buổi live chị lên hình.",
)


@control.handler(service.ACTION_COMPOSE)
async def _compose(ctx: control.ActionContext) -> control.HandlerResult:
    rows = await service.apply_compose(ctx.db, ctx.payload)
    return control.HandlerResult(
        result={"draft_ids": [str(r.id) for r in rows]},
        summary=f"{len(rows)} bản nháp, chờ chị duyệt",
        ref_type=ctx.ref_type,
        ref_id=ctx.ref_id,
    )


@control.handler(service.ACTION_REWRITE)
async def _rewrite(ctx: control.ActionContext) -> control.HandlerResult:
    new = await service.apply_rewrite(ctx.db, ctx.payload)
    return control.HandlerResult(
        result={"draft_id": str(new.id)}, summary=f"Bản {new.version}", ref_type="content_drafts", ref_id=new.id
    )


@control.handler(service.ACTION_CHECK)
async def _check(ctx: control.ActionContext) -> control.HandlerResult:
    await service.apply_check(ctx.db, ctx.payload)
    return control.HandlerResult(result={"check_status": ctx.payload["check_status"]})


@control.handler(service.ACTION_PUBLISH)
async def _publish(ctx: control.ActionContext) -> control.HandlerResult:
    return await service.apply_publish_approval(ctx.db, ctx.payload, ctx.item)


@control.undoer(service.ACTION_PUBLISH)
async def _unpublish(ctx: control.UndoContext) -> None:
    await service.undo_publish_approval(ctx.db, ctx.undo)


@control.on_returned(service.ACTION_PUBLISH)
async def _returned(ctx: control.ReturnContext) -> None:
    await service.handle_returned(ctx.db, ctx.item, ctx.note, ctx.user)


@control.handler(service.ACTION_RETRY)
async def _retry(ctx: control.ActionContext) -> control.HandlerResult:
    return await publishing.apply_retry(ctx.db, ctx.payload)


@control.on_returned(service.ACTION_RETRY)
async def _retry_returned(ctx: control.ReturnContext) -> None:
    post = await ctx.db.get(ScheduledPost, uuid.UUID(ctx.item.payload["scheduled_post_id"]))
    if post is not None and post.status == PostStatus.FAILED:
        post.status = PostStatus.CANCELLED  # chị không đăng nữa


@control.handler(service.ACTION_SUGGEST)
async def _suggest(ctx: control.ActionContext) -> control.HandlerResult:
    return await planner.apply_suggestion(ctx.db, ctx.payload)


@control.handler(service.ACTION_VOICE)
async def _voice(ctx: control.ActionContext) -> control.HandlerResult:
    return await voice.apply_learn(ctx.db, ctx.payload)


@control.undoer(service.ACTION_VOICE)
async def _voice_undo(ctx: control.UndoContext) -> None:
    await voice.undo_learn(ctx.db, ctx.undo)


@control.handler(service.ACTION_INSIGHT)
async def _insight(ctx: control.ActionContext) -> control.HandlerResult:
    row = await publishing.apply_insight(ctx.db, ctx.payload)
    return control.HandlerResult(
        result={"insight_id": str(row.id)}, summary=row.summary, ref_type="content_insights", ref_id=row.id
    )


@control.handler(service.ACTION_VIDEO_PLAN)
async def _video_plan(ctx: control.ActionContext) -> control.HandlerResult:
    return await video.apply_plan(ctx.db, ctx.payload)


@control.handler(service.ACTION_VIDEO)
async def _video(ctx: control.ActionContext) -> control.HandlerResult:
    return await video.apply_approve(ctx.db, ctx.payload)


@control.handler(service.ACTION_LIVE)
async def _live(ctx: control.ActionContext) -> control.HandlerResult:
    return await livestream.apply_approve(ctx.db, ctx.payload, ctx.item)


@control.on_returned(service.ACTION_LIVE)
async def _live_returned(ctx: control.ReturnContext) -> None:
    row = await ctx.db.get(LivestreamScript, uuid.UUID(ctx.item.payload["script_id"]))
    if row is not None and row.status == ScriptStatus.PENDING_REVIEW:
        await livestream.regenerate(ctx.db, row, ctx.note)


@control.stat_provider("content.today", order=40)
async def _stats(db) -> list[control.Stat]:
    pending = await db.scalar(
        select(func.count(ApprovalItem.id)).where(
            ApprovalItem.action == service.ACTION_PUBLISH, ApprovalItem.status == ApprovalStatus.PENDING
        )
    )
    start, end = local_day_bounds_utc()
    today = await db.scalar(
        select(func.count(ScheduledPost.id)).where(
            ScheduledPost.scheduled_at >= start,
            ScheduledPost.scheduled_at < end,
            ScheduledPost.status.in_((PostStatus.APPROVED, PostStatus.PUBLISHED, PostStatus.DRAFT_PUSHED)),
        )
    )
    tiktok = await db.scalar(
        select(func.count(ScheduledPost.id)).where(ScheduledPost.status == PostStatus.DRAFT_PUSHED)
    )
    return [
        control.Stat(
            key="content.pending", label="Bài chờ duyệt", value=int(pending or 0), href="/desk/noi-dung", order=40
        ),
        control.Stat(
            key="content.today", label="Bài đăng hôm nay", value=int(today or 0), href="/desk/noi-dung/lich", order=41
        ),
        control.Stat(
            key="content.tiktok",
            label="Nháp TikTok chờ chị bấm đăng",
            value=int(tiktok or 0),
            href="/desk/noi-dung/lich",
            order=42,
        ),
    ]
