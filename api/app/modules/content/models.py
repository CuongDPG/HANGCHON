"""content — xưởng nội dung và đăng bài (f1–f8): giọng của chị, bản nháp theo kênh, lịch đăng, tư liệu (ảnh/clip),
số liệu bài, rút kinh nghiệm, kịch bản livestream."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, Timestamps, UUIDPk, count, enum_col, fk, flag, json_list, json_obj, money
from app.core.enums import Channel, StrEnum


class DraftFormat(StrEnum):
    POST = "post"  # bài Facebook / Threads
    CAROUSEL = "carousel"  # bộ ảnh Instagram
    REEL = "reel"
    VIDEO_SCRIPT = "video_script"  # kịch bản TikTok
    ZALO_MESSAGE = "zalo_message"  # tin Zalo / nhóm khách quen
    STORY = "story"


class DraftStatus(StrEnum):
    DRAFTING = "drafting"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    RETURNED = "returned"  # chị trả lại kèm lời nhắn
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class CheckStatus(StrEnum):
    """Soát lời quảng cáo (f5)."""

    UNCHECKED = "unchecked"
    PASSED = "passed"
    WARNINGS = "warnings"
    FAILED = "failed"


class PostStatus(StrEnum):
    PLANNED = "planned"  # AI xếp vào lịch tuần (f3), chờ chị
    APPROVED = "approved"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    DRAFT_PUSHED = "draft_pushed"  # TikTok: đã đẩy bản nháp vào app
    FAILED = "failed"
    CANCELLED = "cancelled"


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class MediaPurpose(StrEnum):
    TRIAL_CLIP = "trial_clip"  # clip chị quay khi thử hàng
    PRODUCT_PHOTO = "product_photo"
    POST_MEDIA = "post_media"
    EDITED_VIDEO = "edited_video"  # video AI dựng (f6)
    VOICE_SAMPLE = "voice_sample"  # ghi âm để học giọng (f2)
    OTHER = "other"


class MediaStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    FAILED = "failed"


class ScriptStatus(StrEnum):
    DRAFTING = "drafting"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    USED = "used"


class VoiceProfile(UUIDPk, Timestamps, Base):
    """Giọng của chị (f2): AI học từ bài cũ và ghi âm để bài mới nghe giống chị."""

    __tablename__ = "voice_profiles"

    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = flag(True)
    style_summary: Mapped[str | None] = mapped_column(Text)
    rules: Mapped[list[Any]] = json_list(comment="Nên / không nên khi viết")
    vocabulary: Mapped[list[Any]] = json_list(comment="Từ, cách xưng hô hay dùng")
    examples: Mapped[list[Any]] = json_list(comment="Đoạn mẫu tiêu biểu")
    sample_sources: Mapped[list[Any]] = json_list(comment='[{"kind":"post|audio","ref"}] đã học')
    channel_overrides: Mapped[dict[str, Any]] = json_obj(comment="Khác biệt theo kênh")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    trained_at: Mapped[datetime | None]
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)


class MediaAsset(UUIDPk, Timestamps, Base):
    """Tư liệu ảnh/clip/ghi âm dùng cho nội dung; video dựng (f6) là asset con của clip gốc."""

    __tablename__ = "media_assets"

    kind: Mapped[MediaKind] = mapped_column(enum_col(MediaKind))
    purpose: Mapped[MediaPurpose] = mapped_column(enum_col(MediaPurpose), default=MediaPurpose.OTHER)
    status: Mapped[MediaStatus] = mapped_column(enum_col(MediaStatus), default=MediaStatus.UPLOADED)
    storage_key: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    thumbnail_key: Mapped[str | None] = mapped_column(String(300))
    product_id: Mapped[uuid.UUID | None] = fk("products")
    candidate_id: Mapped[uuid.UUID | None] = fk("candidates")
    parent_asset_id: Mapped[uuid.UUID | None] = fk("media_assets", comment="Bản dựng từ clip gốc")
    edit_spec: Mapped[dict[str, Any]] = json_obj(comment="Cắt đoạn, phụ đề, gợi ý nhạc (f6)")
    transcript: Mapped[str | None] = mapped_column(Text)
    ai_generated: Mapped[bool] = flag(comment="Có phần do AI tạo/dựng (k3)")
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    uploaded_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)


class ContentDraft(UUIDPk, Timestamps, Base):
    """Bản nháp theo kênh (f1): một sản phẩm → nhiều bản, mỗi kênh một cách viết. Đã soát lời (f5)."""

    __tablename__ = "content_drafts"
    __table_args__ = (Index("ix_content_drafts_product_channel", "product_id", "channel"),)

    product_id: Mapped[uuid.UUID | None] = fk("products", index=False)
    drop_id: Mapped[uuid.UUID | None] = fk("drops")
    channel: Mapped[Channel] = mapped_column(enum_col(Channel))
    format: Mapped[DraftFormat] = mapped_column(enum_col(DraftFormat))
    status: Mapped[DraftStatus] = mapped_column(enum_col(DraftStatus), default=DraftStatus.DRAFTING, index=True)
    title: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    hashtags: Mapped[list[Any]] = json_list()
    media_asset_ids: Mapped[list[Any]] = json_list()
    script: Mapped[list[Any]] = json_list(comment='Kịch bản video: [{"scene","visual","voiceover","seconds"}]')
    link_url: Mapped[str | None] = mapped_column(Text)
    voice_profile_id: Mapped[uuid.UUID | None] = fk("voice_profiles")
    parent_draft_id: Mapped[uuid.UUID | None] = fk("content_drafts", comment="Bản gốc khi soạn lại")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # f5 soát lời + k3 nhãn AI
    check_status: Mapped[CheckStatus] = mapped_column(enum_col(CheckStatus), default=CheckStatus.UNCHECKED)
    check_findings: Mapped[list[Any]] = json_list(
        comment='[{"kind":"claim|number|overstatement|label","text","suggestion"}]'
    )
    ai_generated: Mapped[bool] = flag(True)
    ai_label_required: Mapped[bool] = flag(comment="Phải gắn nhãn «có nội dung do AI tạo» khi đăng")
    feedback_note: Mapped[str | None] = mapped_column(Text, comment="Lời nhắn chị khi trả lại")
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)
    created_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)


class ScheduledPost(UUIDPk, Timestamps, Base):
    """Lịch đăng (f3) và đăng tự động (f4). TikTok chỉ đẩy bản nháp."""

    __tablename__ = "scheduled_posts"
    __table_args__ = (
        Index("ix_scheduled_posts_status_time", "status", "scheduled_at"),
        UniqueConstraint("channel", "external_post_id", name="uq_scheduled_posts_external"),
    )

    draft_id: Mapped[uuid.UUID] = fk("content_drafts", ondelete="CASCADE", nullable=False)
    channel: Mapped[Channel] = mapped_column(enum_col(Channel))
    channel_account_id: Mapped[uuid.UUID | None] = fk("channel_accounts")
    product_id: Mapped[uuid.UUID | None] = fk("products")
    scheduled_at: Mapped[datetime]
    status: Mapped[PostStatus] = mapped_column(enum_col(PostStatus), default=PostStatus.PLANNED)
    published_at: Mapped[datetime | None]
    external_post_id: Mapped[str | None] = mapped_column(String(120))
    external_url: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = count()
    error: Mapped[str | None] = mapped_column(Text)
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    ai_label_applied: Mapped[bool] = flag()


class PostMetric(UUIDPk, CreatedAt, Base):
    """Số liệu bài theo thời điểm (f7): bài nào ra đơn."""

    __tablename__ = "post_metrics"
    __table_args__ = (Index("ix_post_metrics_post_captured", "scheduled_post_id", "captured_at"),)

    scheduled_post_id: Mapped[uuid.UUID] = fk("scheduled_posts", ondelete="CASCADE", nullable=False, index=False)
    captured_at: Mapped[datetime]
    impressions: Mapped[int] = count()
    reach: Mapped[int] = count()
    likes: Mapped[int] = count()
    comments: Mapped[int] = count()
    shares: Mapped[int] = count()
    saves: Mapped[int] = count()
    clicks: Mapped[int] = count()
    video_views: Mapped[int] = count()
    messages_started: Mapped[int] = count()
    orders_attributed: Mapped[int] = count()
    revenue_attributed_vnd: Mapped[int] = money()


class ContentInsight(UUIDPk, CreatedAt, Base):
    """Rút kinh nghiệm (f7): AI đọc số liệu kỳ qua, đề xuất kiểu bài nên làm tiếp."""

    __tablename__ = "content_insights"

    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    summary: Mapped[str] = mapped_column(Text)
    findings: Mapped[list[Any]] = json_list(comment='[{"pattern","evidence","recommendation"}]')
    top_post_ids: Mapped[list[Any]] = json_list()
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)


class LivestreamScript(UUIDPk, Timestamps, Base):
    """Kịch bản livestream (f8): dàn ý, thứ tự món, câu khách hay hỏi. Chị là người lên hình."""

    __tablename__ = "livestream_scripts"

    title: Mapped[str] = mapped_column(String(200))
    scheduled_for: Mapped[datetime | None]
    channel: Mapped[Channel | None] = mapped_column(enum_col(Channel))
    drop_id: Mapped[uuid.UUID | None] = fk("drops")
    status: Mapped[ScriptStatus] = mapped_column(enum_col(ScriptStatus), default=ScriptStatus.DRAFTING)
    outline: Mapped[list[Any]] = json_list(comment='[{"segment","minutes","notes"}]')
    items: Mapped[list[Any]] = json_list(comment='[{"product_id","order","talking_points":[],"demo"}]')
    faq: Mapped[list[Any]] = json_list(comment='[{"q","a","product_id"}]')
    notes: Mapped[str | None] = mapped_column(Text)
    ai_generated: Mapped[bool] = flag(True)
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)
