"""API bàn làm việc của xưởng nội dung: `/api/desk/content/**`. Duyệt/bỏ qua/huỷ: chỉ chị (owner)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, UploadFile, status
from sqlalchemy import select

from app import control
from app.core.db import DbSession
from app.core.deps import CurrentUser, OwnerUser
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.jobs import enqueue
from app.core.pagination import Page, Paginated
from app.core.storage import get_storage
from app.core.timeutil import now_utc
from app.modules.catalog.models import Drop, DropStatus, Product, ProductStatus
from app.modules.content import board, facts, livestream, planner, publishing, service, video, views, voice
from app.modules.content.models import (
    ContentDraft,
    ContentInsight,
    LivestreamScript,
    MediaAsset,
    MediaPurpose,
    MediaStatus,
    PostStatus,
    ScheduledPost,
    ScriptStatus,
)
from app.modules.content.schemas import (
    ApproveDraftBody,
    CalendarOut,
    ComposeBody,
    ContentBoard,
    ContentInsightOut,
    DraftPatch,
    DraftView,
    LivestreamCreate,
    LivestreamPatch,
    LivestreamView,
    MarkPublishedBody,
    MediaView,
    OverrideBody,
    PerformanceOut,
    PickDrop,
    PickProduct,
    PlanBody,
    PlanResult,
    PostCard,
    PostPatch,
    RewriteBody,
    RewriteResult,
    StudioDetail,
    StudioItem,
    VideoPlanBody,
    VoiceLearnBody,
    VoiceLearnResult,
    VoicePatch,
    VoiceView,
)
from app.modules.control.models import ApprovalItem, ApprovalStatus

router = APIRouter(prefix="/api/desk/content", tags=["content"])


def _list[T](items: list[T]) -> Paginated[T]:
    """Danh sách gọn (một trang) theo khuôn `Paginated[T]` — dữ liệu của một người bán, không cần phân trang."""
    return Paginated[T](items=items, total=len(items), page=1, size=max(1, len(items)), pages=1)


async def _draft(db: DbSession, draft_id: uuid.UUID) -> ContentDraft:
    d = await db.get(ContentDraft, draft_id)
    if d is None:
        raise NotFound("Không tìm thấy bản nháp.")
    return d


async def _post(db: DbSession, post_id: uuid.UUID) -> ScheduledPost:
    p = await db.get(ScheduledPost, post_id)
    if p is None:
        raise NotFound("Không tìm thấy bài trên lịch.")
    return p


async def _approve_pending(db: DbSession, action: str, dedupe_key: str, user, payload: dict | None = None):
    item = await db.scalar(
        select(ApprovalItem).where(
            ApprovalItem.action == action,
            ApprovalItem.dedupe_key == dedupe_key,
            ApprovalItem.status.in_((ApprovalStatus.PENDING, ApprovalStatus.FAILED)),
        )
    )
    if item is None:
        raise Conflict("Việc này không còn chờ duyệt.", code="not_pending")
    done = await control.approve(db, item.id, user, edited_payload=payload)
    if done.status == ApprovalStatus.FAILED:
        raise Conflict(done.error or "Không duyệt được.", code="approve_failed")
    return done


# ---- xưởng (f1, f5) ----------------------------------------------------------------------------------------------


@router.get("/studio", response_model=Paginated[StudioItem])
async def studio(_: CurrentUser, db: DbSession) -> Paginated[StudioItem]:
    items = [StudioItem.model_validate(i) for i in await service.studio_items(db)]
    return _list(items)


@router.get("/board", response_model=ContentBoard)
async def content_board(
    _: CurrentUser,
    db: DbSession,
    page: Page,
    tab: Annotated[Literal["todo", "review", "scheduled", "published", "all"], Query()] = "all",
    q: Annotated[str | None, Query(max_length=100)] = None,
    channel: Annotated[
        str | None, Query(description="website | facebook | instagram | threads | tiktok | zalo_oa")
    ] = None,
) -> ContentBoard:
    """Xưởng: mỗi món một dòng, trạng thái từng kênh + số liệu bài; `counts` là số món mỗi tab (sau tìm/lọc kênh)."""
    out = await board.board(db, tab=tab, q=q, channel=channel, page=page.page, size=page.size)
    return ContentBoard.model_validate(out)


@router.get("/studio/{kind}/{ref_id}", response_model=StudioDetail)
async def studio_detail(kind: str, ref_id: uuid.UUID, _: CurrentUser, db: DbSession) -> StudioDetail:
    if kind not in ("product", "drop"):
        raise NotFound("Không có mục này.")
    return await views.studio_detail(db, kind, ref_id)


@router.post("/studio/{kind}/{ref_id}/compose", response_model=StudioDetail)
async def compose(kind: str, ref_id: uuid.UUID, body: ComposeBody, user: CurrentUser, db: DbSession) -> StudioDetail:
    """Soạn ngay (hoặc soạn lại toàn bộ) cho sản phẩm / đợt."""
    if kind == "drop":
        drop = await db.get(Drop, ref_id)
        if drop is None:
            raise NotFound("Không tìm thấy đợt bán.")
        out = await service.compose(db, drop=drop, channels=body.channels, instruction=body.instruction, user=user)
    elif kind == "product":
        product = await db.get(Product, ref_id)
        if product is None:
            raise NotFound("Không tìm thấy sản phẩm.")
        out = await service.compose(
            db, product=product, channels=body.channels, instruction=body.instruction, user=user
        )
    else:
        raise NotFound("Không có mục này.")
    if out.status == "blocked":
        raise Conflict("Chị đang tắt «Soạn bài cho từng kênh» ở Mức tự chủ.", code="action_off")
    if out.status == "failed":
        raise Conflict(out.error or "Chưa soạn được.", code="compose_failed")
    return await views.studio_detail(db, kind, ref_id)


@router.get("/drafts/{draft_id}", response_model=DraftView)
async def get_draft(draft_id: uuid.UUID, _: CurrentUser, db: DbSession) -> DraftView:
    return await views.draft_view(db, await _draft(db, draft_id))


@router.patch("/drafts/{draft_id}", response_model=DraftView)
async def edit_draft(draft_id: uuid.UUID, body: DraftPatch, user: CurrentUser, db: DbSession) -> DraftView:
    d = await service.edit_draft(db, await _draft(db, draft_id), body.model_dump(exclude_unset=True), user)
    return await views.draft_view(db, d)


@router.post("/drafts/{draft_id}/rewrite", response_model=RewriteResult)
async def rewrite_draft(draft_id: uuid.UUID, body: RewriteBody, user: CurrentUser, db: DbSession) -> RewriteResult:
    d, st = await service.rewrite(
        db, await _draft(db, draft_id), preset=body.preset, instruction=body.instruction, user=user
    )
    return RewriteResult(status=st, draft=await views.draft_view(db, d))


@router.post("/drafts/{draft_id}/recheck", response_model=DraftView)
async def recheck_draft(draft_id: uuid.UUID, _: CurrentUser, db: DbSession) -> DraftView:
    return await views.draft_view(db, await service.recheck(db, await _draft(db, draft_id)))


@router.post("/drafts/{draft_id}/override", response_model=DraftView)
async def override_check(draft_id: uuid.UUID, body: OverrideBody, user: OwnerUser, db: DbSession) -> DraftView:
    d = await service.override_check(db, await _draft(db, draft_id), body.key, body.reason, user)
    return await views.draft_view(db, d)


@router.post("/drafts/{draft_id}/approve", response_model=DraftView)
async def approve_draft(draft_id: uuid.UUID, body: ApproveDraftBody, user: OwnerUser, db: DbSession) -> DraftView:
    d = await _draft(db, draft_id)
    await service.approve_draft(db, d, user, scheduled_at=body.scheduled_at)
    await db.refresh(d)
    return await views.draft_view(db, d)


# ---- lịch (f3) + đăng (f4) ---------------------------------------------------------------------------------------


@router.get("/calendar", response_model=CalendarOut)
async def get_calendar(_: CurrentUser, db: DbSession, week: date | None = None) -> CalendarOut:
    return CalendarOut.model_validate(await planner.calendar(db, week))


@router.post("/calendar/plan", response_model=PlanResult)
async def plan_week(body: PlanBody, _: CurrentUser, db: DbSession) -> PlanResult:
    return PlanResult.model_validate(await planner.plan_week(db, body.week))


@router.post("/calendar/suggestions/{item_id}/accept", response_model=CalendarOut)
async def accept_suggestion(item_id: uuid.UUID, user: OwnerUser, db: DbSession) -> CalendarOut:
    item = await db.get(ApprovalItem, item_id)
    if item is None or item.action != service.ACTION_SUGGEST:
        raise NotFound("Không tìm thấy gợi ý.")
    done = await control.approve(db, item_id, user)
    if done.status == ApprovalStatus.FAILED:
        raise Conflict(done.error or "Chưa soạn được bài cho gợi ý này.", code="suggest_failed")
    return CalendarOut.model_validate(await planner.calendar(db, date.fromisoformat(item.payload["slot_at"][:10])))


@router.post("/calendar/suggestions/{item_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_suggestion(item_id: uuid.UUID, user: OwnerUser, db: DbSession) -> None:
    item = await db.get(ApprovalItem, item_id)
    if item is None or item.action != service.ACTION_SUGGEST:
        raise NotFound("Không tìm thấy gợi ý.")
    await control.return_item(db, item_id, user, "Chị bỏ qua gợi ý này.")


@router.patch("/posts/{post_id}", response_model=PostCard)
async def reschedule(post_id: uuid.UUID, body: PostPatch, user: CurrentUser, db: DbSession) -> PostCard:
    p = await _post(db, post_id)
    if p.status not in (PostStatus.PLANNED, PostStatus.APPROVED, PostStatus.FAILED):
        raise Conflict("Bài đã đăng hoặc đang đăng, không đổi giờ được.", code="post_locked")
    if body.scheduled_at <= now_utc():
        raise BadRequest("Giờ đăng phải sau bây giờ.")
    old = p.scheduled_at
    p.scheduled_at = body.scheduled_at
    if p.status == PostStatus.FAILED:
        p.status = PostStatus.APPROVED
        p.attempts = 0
    await control.audit(
        db,
        "content.rescheduled",
        user=user,
        entity_type="scheduled_posts",
        entity_id=p.id,
        summary="Đổi giờ đăng",
        data={"from": old.isoformat(), "to": body.scheduled_at.isoformat()},
    )
    await db.flush()
    return PostCard.model_validate((await planner.post_cards(db, [p]))[0])


@router.post("/posts/{post_id}/cancel", response_model=PostCard)
async def cancel_post(post_id: uuid.UUID, user: OwnerUser, db: DbSession) -> PostCard:
    p = await _post(db, post_id)
    await publishing.cancel_scheduled(db, p, user)
    return PostCard.model_validate((await planner.post_cards(db, [p]))[0])


@router.post("/posts/{post_id}/mark-published", response_model=PostCard)
async def mark_published(post_id: uuid.UUID, body: MarkPublishedBody, user: OwnerUser, db: DbSession) -> PostCard:
    p = await publishing.mark_published(db, await _post(db, post_id), user, body.url)
    return PostCard.model_validate((await planner.post_cards(db, [p]))[0])


@router.post("/posts/{post_id}/publish-now", response_model=PostCard)
async def publish_now(post_id: uuid.UUID, user: OwnerUser, db: DbSession) -> PostCard:
    """Đăng ngay bài đã duyệt (hoặc đăng lại bài lỗi) thay vì chờ tới giờ."""
    p = await _post(db, post_id)
    if await publishing.is_stopped(db, p.product_id):
        raise Conflict("Món này đang ngừng bán. Chị mở bán lại rồi mới đăng bài.", code="product_stopped")
    if p.status == PostStatus.FAILED:
        item = await db.scalar(
            select(ApprovalItem.id).where(
                ApprovalItem.action == service.ACTION_RETRY,
                ApprovalItem.dedupe_key == f"retry:{p.id}",
                ApprovalItem.status == ApprovalStatus.PENDING,
            )
        )
        if item:
            await _approve_pending(db, service.ACTION_RETRY, f"retry:{p.id}", user)
            await db.refresh(p)
            return PostCard.model_validate((await planner.post_cards(db, [p]))[0])
        p.status = PostStatus.APPROVED
        p.attempts = 0
    if p.status != PostStatus.APPROVED:
        raise Conflict("Chỉ đăng ngay được bài đã duyệt.", code="not_approved")
    p.scheduled_at = min(p.scheduled_at, now_utc())
    await publishing.publish_one(db, p)
    return PostCard.model_validate((await planner.post_cards(db, [p]))[0])


# ---- đo và học (f7) ----------------------------------------------------------------------------------------------


@router.get("/performance", response_model=PerformanceOut)
async def performance(_: CurrentUser, db: DbSession, days: int = 30) -> PerformanceOut:
    return PerformanceOut.model_validate(await publishing.performance(db, days=max(1, min(days, 180))))


@router.post("/performance/refresh", response_model=PerformanceOut)
async def refresh_metrics(_: CurrentUser, db: DbSession) -> PerformanceOut:
    await publishing.pull_metrics(db)
    return PerformanceOut.model_validate(await publishing.performance(db))


@router.post("/insights/run", response_model=ContentInsightOut)
async def run_insights(_: CurrentUser, db: DbSession) -> ContentInsight:
    out = await publishing.learn(db)
    if out.status != "applied" or not out.result:
        raise Conflict("Việc rút kinh nghiệm đang chờ duyệt hoặc đang tắt.", code="not_applied")
    row = await db.get(ContentInsight, uuid.UUID(out.result["insight_id"]))
    assert row is not None
    return row


@router.get("/insights", response_model=Paginated[ContentInsightOut])
async def list_insights(_: CurrentUser, db: DbSession) -> Paginated[ContentInsightOut]:
    rows = list(
        (await db.execute(select(ContentInsight).order_by(ContentInsight.created_at.desc()).limit(10))).scalars()
    )
    return _list([ContentInsightOut.model_validate(r) for r in rows])


# ---- giọng (f2) --------------------------------------------------------------------------------------------------


@router.get("/voice", response_model=VoiceView)
async def get_voice(_: CurrentUser, db: DbSession) -> VoiceView:
    vp = await facts.active_voice(db, create=True)
    return VoiceView.model_validate(voice.voice_view(vp))  # type: ignore[arg-type]


@router.patch("/voice", response_model=VoiceView)
async def edit_voice(body: VoicePatch, user: OwnerUser, db: DbSession) -> VoiceView:
    vp = await voice.edit(db, body.model_dump(exclude_unset=True), user)
    return VoiceView.model_validate(voice.voice_view(vp))


@router.post("/voice/learn", response_model=VoiceLearnResult)
async def learn_voice(body: VoiceLearnBody, user: OwnerUser, db: DbSession) -> VoiceLearnResult:
    out = await voice.learn(db, body.samples, body.notes, user, spoken=body.spoken)
    vp = await facts.active_voice(db)
    await db.refresh(vp)  # type: ignore[arg-type]
    return VoiceLearnResult(status=out.status, voice=VoiceView.model_validate(voice.voice_view(vp)))  # type: ignore[arg-type]


# ---- video (f6) --------------------------------------------------------------------------------------------------


@router.get("/media", response_model=Paginated[MediaView])
async def list_media(
    _: CurrentUser, db: DbSession, purpose: MediaPurpose | None = None, product_id: uuid.UUID | None = None
) -> Paginated[MediaView]:
    q = select(MediaAsset).where(MediaAsset.purpose.in_((MediaPurpose.TRIAL_CLIP, MediaPurpose.EDITED_VIDEO)))
    if purpose:
        q = q.where(MediaAsset.purpose == purpose)
    if product_id:
        q = q.where(MediaAsset.product_id == product_id)
    rows = list((await db.execute(q.order_by(MediaAsset.created_at.desc()).limit(100))).scalars())
    return _list([await views.media_view(db, a) for a in rows])


@router.post("/media", response_model=MediaView, status_code=status.HTTP_201_CREATED)
async def upload_media(
    user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    product_id: Annotated[uuid.UUID | None, Form()] = None,
    note: Annotated[str | None, Form(max_length=1000)] = None,
) -> MediaView:
    data = await file.read()
    asset = await video.upload_clip(
        db,
        data=data,
        content_type=file.content_type or "",
        filename=file.filename,
        product_id=product_id,
        note=note,
        user=user,
    )
    return await views.media_view(db, asset)


@router.delete("/media/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(asset_id: uuid.UUID, user: OwnerUser, db: DbSession) -> None:
    a = await db.get(MediaAsset, asset_id)
    if a is None:
        raise NotFound("Không tìm thấy tệp.")
    if a.status == MediaStatus.APPROVED and a.purpose == MediaPurpose.EDITED_VIDEO:
        raise Conflict("Video đã duyệt đang gắn vào bài, không xoá được.", code="in_use")
    if a.storage_key:
        await get_storage().delete(a.storage_key)
    await control.cancel_pending(db, action=service.ACTION_VIDEO, dedupe_key=f"video:{a.id}")
    await control.audit(
        db,
        "content.media_deleted",
        user=user,
        entity_type="media_assets",
        entity_id=a.id,
        summary=f"Xoá {a.purpose.value}",
    )
    await db.delete(a)


@router.post("/videos", response_model=MediaView, status_code=status.HTTP_201_CREATED)
async def plan_video(body: VideoPlanBody, user: CurrentUser, db: DbSession, tasks: BackgroundTasks) -> MediaView:
    asset = await video.plan_video(
        db,
        product_id=body.product_id,
        clip_ids=body.clip_ids,
        notes=body.notes,
        target_seconds=body.target_seconds,
        user=user,
    )
    if asset.status == MediaStatus.PROCESSING:
        tasks.add_task(enqueue, "content.render_video", asset_id=str(asset.id))  # sau khi commit
    return await views.media_view(db, asset)


@router.get("/videos/{asset_id}", response_model=MediaView)
async def get_video(asset_id: uuid.UUID, _: CurrentUser, db: DbSession) -> MediaView:
    a = await db.get(MediaAsset, asset_id)
    if a is None:
        raise NotFound("Không tìm thấy video.")
    return await views.media_view(db, a)


@router.post("/videos/{asset_id}/approve", response_model=MediaView)
async def approve_video(asset_id: uuid.UUID, user: OwnerUser, db: DbSession) -> MediaView:
    await _approve_pending(db, service.ACTION_VIDEO, f"video:{asset_id}", user)
    a = await db.get(MediaAsset, asset_id)
    assert a is not None
    await db.refresh(a)
    return await views.media_view(db, a)


# ---- livestream (f8) ---------------------------------------------------------------------------------------------


@router.get("/livestreams", response_model=Paginated[LivestreamView])
async def list_livestreams(_: CurrentUser, db: DbSession) -> Paginated[LivestreamView]:
    rows = list(
        (await db.execute(select(LivestreamScript).order_by(LivestreamScript.created_at.desc()).limit(50))).scalars()
    )
    return _list([await views.livestream_view(db, s) for s in rows])


@router.post("/livestreams", response_model=LivestreamView, status_code=status.HTTP_201_CREATED)
async def create_livestream(body: LivestreamCreate, user: CurrentUser, db: DbSession) -> LivestreamView:
    s = await livestream.create(
        db,
        title=body.title,
        drop_id=body.drop_id,
        product_ids=body.product_ids,
        minutes=body.minutes,
        scheduled_for=body.scheduled_for,
        instruction=body.instruction,
        user=user,
    )
    return await views.livestream_view(db, s)


@router.get("/livestreams/{script_id}", response_model=LivestreamView)
async def get_livestream(script_id: uuid.UUID, _: CurrentUser, db: DbSession) -> LivestreamView:
    s = await db.get(LivestreamScript, script_id)
    if s is None:
        raise NotFound("Không tìm thấy kịch bản.")
    return await views.livestream_view(db, s)


@router.patch("/livestreams/{script_id}", response_model=LivestreamView)
async def edit_livestream(
    script_id: uuid.UUID, body: LivestreamPatch, user: CurrentUser, db: DbSession
) -> LivestreamView:
    s = await db.get(LivestreamScript, script_id)
    if s is None:
        raise NotFound("Không tìm thấy kịch bản.")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await control.audit(
        db,
        "content.livestream_edited",
        user=user,
        entity_type="livestream_scripts",
        entity_id=s.id,
        summary="Sửa kịch bản livestream",
    )
    await db.flush()
    return await views.livestream_view(db, s)


@router.post("/livestreams/{script_id}/approve", response_model=LivestreamView)
async def approve_livestream(script_id: uuid.UUID, user: OwnerUser, db: DbSession) -> LivestreamView:
    await _approve_pending(db, service.ACTION_LIVE, f"live:{script_id}", user)
    s = await db.get(LivestreamScript, script_id)
    assert s is not None
    await db.refresh(s)
    return await views.livestream_view(db, s)


@router.post("/livestreams/{script_id}/used", response_model=LivestreamView)
async def mark_livestream_used(script_id: uuid.UUID, _: OwnerUser, db: DbSession) -> LivestreamView:
    s = await db.get(LivestreamScript, script_id)
    if s is None:
        raise NotFound("Không tìm thấy kịch bản.")
    if s.status != ScriptStatus.APPROVED:
        raise Conflict("Kịch bản cần được duyệt trước.", code="not_approved")
    s.status = ScriptStatus.USED
    await db.flush()
    return await views.livestream_view(db, s)


# ---- chọn món / đợt (cho video, livestream) ----------------------------------------------------------------------


@router.get("/pick/products", response_model=Paginated[PickProduct])
async def pick_products(_: CurrentUser, db: DbSession) -> Paginated[PickProduct]:
    rows = list(
        (
            await db.execute(select(Product).where(Product.status == ProductStatus.PUBLISHED).order_by(Product.name))
        ).scalars()
    )
    items = []
    for p in rows:
        keys = facts.image_keys(p)
        items.append(
            PickProduct(
                id=p.id, name=p.name, price_vnd=p.price_vnd, image_url=facts.file_url(keys[0]) if keys else None
            )
        )
    return _list(items)


@router.get("/pick/drops", response_model=Paginated[PickDrop])
async def pick_drops(_: CurrentUser, db: DbSession) -> Paginated[PickDrop]:
    rows = list(
        (
            await db.execute(
                select(Drop)
                .where(Drop.status.in_((DropStatus.OPEN, DropStatus.SCHEDULED, DropStatus.CLOSED)))
                .order_by(Drop.opens_at.desc().nulls_last())
            )
        ).scalars()
    )
    items = [PickDrop(id=d.id, code=d.code, title=d.title, status=d.status.value) for d in rows]
    return _list(items)
