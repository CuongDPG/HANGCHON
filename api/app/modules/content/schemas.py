"""Schema đọc cơ bản của content (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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


# ---- schema tạo/sửa và màn hình (router) ------------------------------------------------------------------------


class SlideView(BaseModel):
    image_index: int
    caption: str
    image_url: str | None = None


class DraftView(ContentDraftOut):
    channel_label: str
    can_approve: bool
    post: ScheduledPostOut | None = None
    src_code: str | None = None
    approval_item_id_pending: uuid.UUID | None = None
    slides: list[SlideView] = Field(default_factory=list)
    video: MediaAssetOut | None = None
    video_url: str | None = None


class StudioItem(BaseModel):
    kind: Literal["product", "drop"]
    id: uuid.UUID
    name: str
    subtitle: str | None
    image_url: str | None
    status: str
    total: int
    approved: int
    drafting: int
    needs_fix: int
    pending: int
    updated_at: datetime


class StudioDropInfo(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    closes_at: datetime | None


class StudioDetail(BaseModel):
    kind: Literal["product", "drop"]
    id: uuid.UUID
    name: str
    subtitle: str | None = None
    price_vnd: int | None = None
    image_url: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    url: str
    reason_selected: str | None = None
    not_satisfied: str | None = None
    trial_days: int | None = None
    considered_count: int | None = None
    drop: StudioDropInfo | None = None
    drafts: list[DraftView]
    compose_pending: bool = False
    # trang sản phẩm trên website (kênh chính thức): trạng thái của sản phẩm (draft/pending_review/published/…)
    page_status: str | None = None
    # ứng viên ở Bàn chọn (link «Hồ sơ chọn»)
    candidate_id: uuid.UUID | None = None


class ComposeBody(BaseModel):
    channels: list[Channel] | None = None
    instruction: str | None = Field(default=None, max_length=1000)


class DraftPatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=5000)
    hashtags: list[str] | None = None
    script: list[dict[str, Any]] | None = None


class RewriteBody(BaseModel):
    preset: Literal["shorter", "warmer", "price"] | None = None
    instruction: str | None = Field(default=None, max_length=1000)


class RewriteResult(BaseModel):
    status: str
    draft: DraftView


class OverrideBody(BaseModel):
    key: Literal["numbers", "claims", "length"]
    reason: str = Field(max_length=500)


class ApproveDraftBody(BaseModel):
    scheduled_at: datetime | None = None


class PostPatch(BaseModel):
    scheduled_at: datetime


class MarkPublishedBody(BaseModel):
    url: str | None = Field(default=None, max_length=500)


class PostCard(BaseModel):
    id: uuid.UUID
    draft_id: uuid.UUID
    channel: str
    channel_label: str
    scheduled_at: datetime
    published_at: datetime | None
    status: PostStatus
    display_status: str
    title: str
    product_id: uuid.UUID | None
    drop_id: uuid.UUID | None
    name: str | None
    external_url: str | None
    error: str | None
    attempts: int
    approval_item_id: uuid.UUID | None
    src_code: str
    orders: int


class SlotSuggestionView(BaseModel):
    id: uuid.UUID
    slot_at: datetime
    channel: str | None
    channel_label: str
    product_id: str | None
    name: str | None
    idea: str | None
    reason: str | None


class CalendarDay(BaseModel):
    day: date
    label: str
    name: str
    rest: bool
    posts: list[PostCard]
    suggestions: list[SlotSuggestionView]


class BestTime(BaseModel):
    channel: str
    channel_label: str
    time: str
    source: Literal["default", "metrics"]


class CalendarOut(BaseModel):
    week_start: date
    label: str
    days: list[CalendarDay]
    counts: dict[str, int]
    best_times: list[BestTime]


class PlanBody(BaseModel):
    week: date | None = None


class PlanResult(BaseModel):
    moved: int
    suggested: int
    week_start: date


class PerformanceRow(BaseModel):
    scheduled_post_id: uuid.UUID
    channel: str
    channel_label: str
    status: str
    title: str
    name: str | None
    product_id: uuid.UUID | None
    published_at: datetime
    external_url: str | None
    src_code: str
    reach: int
    likes: int
    comments: int
    shares: int
    clicks: int
    video_views: int
    orders: int
    revenue_vnd: int
    measured_at: datetime | None


class PerformanceTotals(BaseModel):
    posts: int
    orders: int
    revenue_vnd: int
    reach: int


class PerformanceOut(BaseModel):
    days: int
    posts: list[PerformanceRow]
    totals: PerformanceTotals
    insight: ContentInsightOut | None


class VoiceView(BaseModel):
    id: uuid.UUID
    name: str
    style_summary: str | None
    pronouns: str | None
    sentence_style: str | None
    rules: list[str]
    avoid: list[str]
    vocabulary: list[str]
    examples: list[str]
    samples_count: int
    samples: list[str]
    version: int
    trained_at: datetime | None
    updated_at: datetime


class VoicePatch(BaseModel):
    style_summary: str | None = Field(default=None, max_length=2000)
    pronouns: str | None = Field(default=None, max_length=300)
    sentence_style: str | None = Field(default=None, max_length=1000)
    rules: list[str] | None = None
    avoid: list[str] | None = None
    vocabulary: list[str] | None = None
    examples: list[str] | None = None


class VoiceLearnBody(BaseModel):
    samples: list[str] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=4000)
    spoken: list[str] = Field(default_factory=list, max_length=10, description="Lời chị nói, chép từ giọng nói")


class VoiceLearnResult(BaseModel):
    status: str
    voice: VoiceView


class MediaView(MediaAssetOut):
    url: str | None = None
    product_name: str | None = None


class VideoPlanBody(BaseModel):
    product_id: uuid.UUID | None = None
    clip_ids: list[uuid.UUID] = Field(min_length=1, max_length=12)
    notes: str | None = Field(default=None, max_length=1000)
    target_seconds: int = Field(default=24, ge=20, le=30)


class LivestreamCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    drop_id: uuid.UUID | None = None
    product_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    minutes: int = Field(default=30, ge=10, le=120)
    scheduled_for: datetime | None = None
    instruction: str | None = Field(default=None, max_length=1000)


class LivestreamPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    scheduled_for: datetime | None = None
    outline: list[dict[str, Any]] | None = None
    items: list[dict[str, Any]] | None = None
    faq: list[dict[str, Any]] | None = None
    notes: str | None = None


class LivestreamView(LivestreamScriptOut):
    drop_title: str | None = None
    approval_pending: bool = False


class PickProduct(BaseModel):
    id: uuid.UUID
    name: str
    price_vnd: int
    image_url: str | None


class PickDrop(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    status: str
