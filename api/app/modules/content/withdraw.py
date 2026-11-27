"""Gỡ bài khi chị ngừng bán một món và hiện lại khi mở bán lại.

catalog phát `product.sale_stop_requested` / `product.sale_resume_requested` (payload: `stop_id`, `product_id`, mã các
bài chị đã chọn). Kết quả từng bài ghi vào `scheduled_posts.removal` để catalog đọc lại và báo chị từng bước.
Chạy lặp lại không làm lại: bài đã xử lý trong cùng `stop_id` thì bỏ qua (không gọi kênh lần hai)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.errors import AppError
from app.core.timeutil import now_utc
from app.integrations.social import driver_for
from app.modules.content.channels import channel_label
from app.modules.content.models import PostStatus, ScheduledPost
from app.modules.content.publishing import CANCELLABLE, cancel_scheduled
from app.modules.control.models import User

log = logging.getLogger("app.content.withdraw")

LIVE = (PostStatus.PUBLISHED, PostStatus.DRAFT_PUSHED)


def _uuid(v: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(v))
    except (TypeError, ValueError):
        return None


def _mark(post: ScheduledPost, stop_id: str, outcome: str, prev: str, error: str | None = None) -> None:
    post.removal = {"stop_id": stop_id, "outcome": outcome, "error": error, "prev_status": prev,
                    "at": now_utc().isoformat()}  # fmt: skip


async def _post(db: AsyncSession, post_id: Any, product_id: uuid.UUID | None) -> ScheduledPost | None:
    pid = _uuid(post_id)
    post = await db.get(ScheduledPost, pid) if pid else None
    return post if post is not None and post.product_id == product_id else None


async def on_stop(db: AsyncSession, payload: dict[str, Any]) -> None:
    stop_id = str(payload["stop_id"])
    product_id = _uuid(payload.get("product_id"))
    uid = _uuid(payload.get("user_id"))
    user = await db.get(User, uid) if uid else None

    for raw in payload.get("cancel_post_ids") or []:
        post = await _post(db, raw, product_id)
        if post is None or (post.removal or {}).get("stop_id") == stop_id:
            continue
        prev = post.status.value
        if post.status in CANCELLABLE:
            await cancel_scheduled(db, post, user, summary="Huỷ lịch đăng vì chị ngừng bán món")
            _mark(post, stop_id, "cancelled", prev)
        else:
            _mark(post, stop_id, "failed", prev, "Bài không còn chờ đăng (có thể vừa đăng xong).")

    want = "delete" if payload.get("delete_posts") else "hide"
    for item in payload.get("remove_posts") or []:
        post = await _post(db, item.get("id"), product_id)
        if post is None or (post.removal or {}).get("stop_id") == stop_id:
            continue
        prev = post.status.value
        label = channel_label(post.channel)
        if post.status not in LIVE:
            _mark(post, stop_id, "failed", prev, "Bài không còn ở trạng thái đã đăng.")
            continue
        if item.get("manual_done"):
            post.status = PostStatus.REMOVED
            _mark(post, stop_id, "manual", prev)
            await control.audit(db, "content.post_removed_manually", user=user, entity_type="scheduled_posts",
                                entity_id=post.id, summary=f"Chị báo đã gỡ tay bài {label}")  # fmt: skip
            continue
        if post.status == PostStatus.DRAFT_PUSHED or not post.external_post_id:
            _mark(post, stop_id, "needs_manual", prev)  # nháp TikTok nằm trong app của chị
            continue
        try:
            res = await driver_for(post.channel).remove_post(post.channel, post.external_post_id, mode=want)
        except Exception as e:
            msg = (e.message if isinstance(e, AppError) else str(e))[:500]
            log.warning("Gỡ bài %s (%s) lỗi: %s", post.id, label, msg)
            _mark(post, stop_id, "failed", prev, msg)
            await control.audit(db, "content.post_remove_failed", user=user, entity_type="scheduled_posts",
                                entity_id=post.id, summary=f"Gỡ bài {label} lỗi: {msg[:200]}")  # fmt: skip
            continue
        if res.mode == "unsupported":
            _mark(post, stop_id, "needs_manual", prev)
            continue
        hidden = res.mode == "hidden"
        post.status = PostStatus.HIDDEN if hidden else PostStatus.REMOVED
        _mark(post, stop_id, res.mode, prev)
        await control.audit(
            db, "content.post_hidden" if hidden else "content.post_deleted", user=user, entity_type="scheduled_posts",
            entity_id=post.id, summary=f"{'Ẩn' if hidden else 'Xoá hẳn'} bài {label} vì chị ngừng bán món",
            data={"external_id": post.external_post_id, "stop_id": stop_id},
        )  # fmt: skip
    await db.flush()


async def on_resume(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Hiện lại bài đã ẩn trong lần ngừng bán `stop_id`. Bài đã xoá hẳn / gỡ tay / lịch đã huỷ không tự quay lại."""
    stop_id = str(payload["stop_id"])
    product_id = _uuid(payload.get("product_id"))
    uid = _uuid(payload.get("user_id"))
    user = await db.get(User, uid) if uid else None
    for raw in payload.get("post_ids") or []:
        post = await _post(db, raw, product_id)
        rm = dict(post.removal or {}) if post is not None else {}
        if post is None or post.status != PostStatus.HIDDEN or rm.get("stop_id") != stop_id:
            continue
        label = channel_label(post.channel)
        try:
            await driver_for(post.channel).restore_post(post.channel, post.external_post_id or "")
        except Exception as e:
            msg = (e.message if isinstance(e, AppError) else str(e))[:500]
            post.removal = {**rm, "restore_error": msg}
            await control.audit(db, "content.post_restore_failed", user=user, entity_type="scheduled_posts",
                                entity_id=post.id, summary=f"Hiện lại bài {label} lỗi: {msg[:200]}")  # fmt: skip
            continue
        post.status = PostStatus.PUBLISHED
        post.removal = {**rm, "restored_at": now_utc().isoformat(), "restore_error": None}
        await control.audit(db, "content.post_restored", user=user, entity_type="scheduled_posts", entity_id=post.id,
                            summary=f"Hiện lại bài {label} vì chị mở bán lại")  # fmt: skip
    await db.flush()
