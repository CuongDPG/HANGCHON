"""Dựng dữ liệu cho màn hình (gộp bản nháp + lịch + hàng chờ + ảnh)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.modules.catalog.models import Drop, Product
from app.modules.content import board, facts, service
from app.modules.content.channels import channel_label
from app.modules.content.checks import can_approve
from app.modules.content.models import ContentDraft, DraftStatus, LivestreamScript, MediaAsset, ScriptStatus
from app.modules.content.schedule import src_code
from app.modules.content.schemas import (
    ContentDraftOut,
    DraftView,
    LivestreamScriptOut,
    LivestreamView,
    MediaAssetOut,
    MediaView,
    ScheduledPostOut,
    SlideView,
    StudioDetail,
    StudioDropInfo,
)
from app.modules.control.models import ApprovalItem, ApprovalStatus


async def draft_view(db: AsyncSession, d: ContentDraft, image_keys: list[str] | None = None) -> DraftView:
    post = await service.latest_post(db, d.id)
    item = await db.scalar(
        select(ApprovalItem.id).where(
            ApprovalItem.action == service.ACTION_PUBLISH,
            ApprovalItem.dedupe_key == service.publish_key(d.id),
            ApprovalItem.status == ApprovalStatus.PENDING,
        )
    )
    if image_keys is None:
        product = await db.get(Product, d.product_id) if d.product_id else None
        image_keys = facts.image_keys(product) if product else []
    slides = [
        SlideView(
            image_index=int(s.get("image_index", 0)),
            caption=str(s.get("caption", "")),
            image_url=facts.file_url(image_keys[int(s.get("image_index", 0))])
            if 0 <= int(s.get("image_index", 0)) < len(image_keys)
            else None,
        )
        for s in d.script
        if isinstance(s, dict) and "caption" in s and "voiceover" not in s
    ]
    vid = None
    for mid in d.media_asset_ids:
        try:
            vid = await db.get(MediaAsset, uuid.UUID(str(mid)))
        except ValueError:
            vid = None
        if vid:
            break
    return DraftView(
        **ContentDraftOut.model_validate(d).model_dump(),
        channel_label=channel_label(d.channel),
        can_approve=can_approve(d.check_status) and d.status not in (DraftStatus.DRAFTING, DraftStatus.ARCHIVED),
        post=ScheduledPostOut.model_validate(post) if post else None,
        src_code=src_code(post) if post else None,
        approval_item_id_pending=item,
        slides=slides,
        video=MediaAssetOut.model_validate(vid) if vid else None,
        video_url=facts.file_url(vid.storage_key) if vid and vid.storage_key else None,
    )


async def studio_detail(db: AsyncSession, kind: str, ref_id: uuid.UUID) -> StudioDetail:
    if kind == "drop":
        drop = await db.get(Drop, ref_id)
        if drop is None:
            raise NotFound("Không tìm thấy đợt bán.")
        drafts = await service.current_drafts(db, drop_id=drop.id)
        pids = [it.product_id for it in drop.items]
        first = await db.get(Product, pids[0]) if pids else None
        keys = facts.image_keys(first) if first else []
        return StudioDetail(
            kind="drop",
            id=drop.id,
            name=drop.title,
            subtitle=f"Đợt {drop.code}",
            image_url=facts.file_url(keys[0]) if keys else None,
            image_urls=[facts.file_url(k) for k in keys],
            url=facts.store_url(facts.drop_path(drop)),
            drop=StudioDropInfo(id=drop.id, code=drop.code, title=drop.title, closes_at=drop.closes_at),
            drafts=[await draft_view(db, d, keys) for d in drafts],
            compose_pending=any(d.status == DraftStatus.DRAFTING for d in drafts),
            tracking=await board.one(db, "drop", drop.id),
        )
    product = await db.get(Product, ref_id)
    if product is None:
        raise NotFound("Không tìm thấy sản phẩm.")
    drafts = await service.current_drafts(db, product_id=product.id)
    keys = facts.image_keys(product)
    drop = await service.open_drop_for(db, product.id)
    return StudioDetail(
        kind="product",
        id=product.id,
        name=product.name,
        subtitle=product.subtitle,
        price_vnd=product.price_vnd,
        image_url=facts.file_url(keys[0]) if keys else None,
        image_urls=[facts.file_url(k) for k in keys],
        url=facts.store_url(facts.product_path(product)),
        reason_selected=product.reason_selected,
        not_satisfied=product.not_satisfied,
        trial_days=product.trial_days,
        considered_count=product.considered_count,
        page_status=product.status.value,
        candidate_id=product.candidate_id,
        drop=StudioDropInfo(id=drop.id, code=drop.code, title=drop.title, closes_at=drop.closes_at) if drop else None,
        drafts=[await draft_view(db, d, keys) for d in drafts],
        compose_pending=any(d.status == DraftStatus.DRAFTING for d in drafts),
        tracking=await board.one(db, "product", product.id),
    )


async def media_view(db: AsyncSession, a: MediaAsset) -> MediaView:
    name = await db.scalar(select(Product.name).where(Product.id == a.product_id)) if a.product_id else None
    return MediaView(
        **MediaAssetOut.model_validate(a).model_dump(),
        url=facts.file_url(a.storage_key) if a.storage_key else None,
        product_name=name,
    )


async def livestream_view(db: AsyncSession, s: LivestreamScript) -> LivestreamView:
    title = await db.scalar(select(Drop.title).where(Drop.id == s.drop_id)) if s.drop_id else None
    return LivestreamView(
        **LivestreamScriptOut.model_validate(s).model_dump(),
        drop_title=title,
        approval_pending=s.status == ScriptStatus.PENDING_REVIEW,
    )
