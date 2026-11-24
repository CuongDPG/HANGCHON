"""Schema đọc cơ bản của content (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.enums import Channel
from app.modules.content.models import (
    CheckStatus,
    DraftFormat,
    DraftStatus,
    MediaKind,
    MediaPurpose,
    MediaStatus,
    PostStatus,
    ScriptStatus,
)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class VoiceProfileOut(ORM):
    """Giọng của chị (f2): AI học từ bài cũ và ghi âm để bài mới nghe giống chị."""

    id: uuid.UUID
    name: str
    is_active: bool
    style_summary: str | None
    rules: list[Any]
    vocabulary: list[Any]
    examples: list[Any]
    sample_sources: list[Any]
    channel_overrides: dict[str, Any]
    version: int
    trained_at: datetime | None
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class MediaAssetOut(ORM):
    """Tư liệu ảnh/clip/ghi âm dùng cho nội dung; video dựng (f6) là asset con của clip gốc."""

    id: uuid.UUID
    kind: MediaKind
    purpose: MediaPurpose
    status: MediaStatus
    storage_key: str
    content_type: str
    size_bytes: int
    width: int | None
    height: int | None
    duration_seconds: int | None
    thumbnail_key: str | None
    product_id: uuid.UUID | None
    candidate_id: uuid.UUID | None
    parent_asset_id: uuid.UUID | None
    edit_spec: dict[str, Any]
    transcript: str | None
    ai_generated: bool
    approval_item_id: uuid.UUID | None
    uploaded_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ContentDraftOut(ORM):
    """Bản nháp theo kênh (f1): một sản phẩm → nhiều bản, mỗi kênh một cách viết. Đã soát lời (f5)."""

    id: uuid.UUID
    product_id: uuid.UUID | None
    drop_id: uuid.UUID | None
    channel: Channel
    format: DraftFormat
    status: DraftStatus
    title: str | None
    body: str
    hashtags: list[Any]
    media_asset_ids: list[Any]
    script: list[Any]
    link_url: str | None
    voice_profile_id: uuid.UUID | None
    parent_draft_id: uuid.UUID | None
    version: int
    check_status: CheckStatus
    check_findings: list[Any]
    ai_generated: bool
    ai_label_required: bool
    feedback_note: str | None
    approval_item_id: uuid.UUID | None
    ai_run_id: uuid.UUID | None
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ScheduledPostOut(ORM):
    """Lịch đăng (f3) và đăng tự động (f4). TikTok chỉ đẩy bản nháp."""

    id: uuid.UUID
    draft_id: uuid.UUID
    channel: Channel
    channel_account_id: uuid.UUID | None
    product_id: uuid.UUID | None
    scheduled_at: datetime
    status: PostStatus
    published_at: datetime | None
    external_post_id: str | None
    external_url: str | None
    attempts: int
    error: str | None
    approval_item_id: uuid.UUID | None
    ai_label_applied: bool
    created_at: datetime
    updated_at: datetime


class PostMetricOut(ORM):
    """Số liệu bài theo thời điểm (f7): bài nào ra đơn."""

    id: uuid.UUID
    scheduled_post_id: uuid.UUID
    captured_at: datetime
    impressions: int
    reach: int
    likes: int
    comments: int
    shares: int
    saves: int
    clicks: int
    video_views: int
    messages_started: int
    orders_attributed: int
    revenue_attributed_vnd: int
    created_at: datetime


class ContentInsightOut(ORM):
    """Rút kinh nghiệm (f7): AI đọc số liệu kỳ qua, đề xuất kiểu bài nên làm tiếp."""

    id: uuid.UUID
    period_start: date
    period_end: date
    summary: str
    findings: list[Any]
    top_post_ids: list[Any]
    ai_run_id: uuid.UUID | None
    created_at: datetime


class LivestreamScriptOut(ORM):
    """Kịch bản livestream (f8): dàn ý, thứ tự món, câu khách hay hỏi. Chị là người lên hình."""

    id: uuid.UUID
    title: str
    scheduled_for: datetime | None
    channel: Channel | None
    drop_id: uuid.UUID | None
    status: ScriptStatus
    outline: list[Any]
    items: list[Any]
    faq: list[Any]
    notes: str | None
    ai_generated: bool
    approval_item_id: uuid.UUID | None
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
