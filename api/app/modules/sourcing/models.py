"""sourcing — săn hàng (a1–a7): đề tìm, lượt quét, ứng viên, tín hiệu xu hướng, tín hiệu nhu cầu khách."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, CreatedAt, Timestamps, UUIDPk, count, enum_col, fk, flag, json_list, json_obj, money_opt
from app.core.enums import Channel, Language, SourcePlatform, StrEnum


class BriefInputMode(StrEnum):
    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"  # đề sinh từ ảnh (a3)
    TREND = "trend"  # đề mở từ tín hiệu xu hướng (a5)
    DEMAND = "demand"  # đề mở từ nhu cầu khách (a6)


class BriefStatus(StrEnum):
    DRAFT = "draft"  # AI vừa hiểu xong, chờ chị xác nhận cách hiểu (a1)
    ACTIVE = "active"  # đã xác nhận, đang/sẽ quét
    PAUSED = "paused"
    DONE = "done"  # đã chọn được món, đóng đề
    ARCHIVED = "archived"


class RunKind(StrEnum):
    BRIEF_SCAN = "brief_scan"  # a4 quét nhiều nguồn theo đề
    LINK_IMPORT = "link_import"  # a2 dán link
    IMAGE_SEARCH = "image_search"  # a3 tìm bằng ảnh
    SCHEDULED_SCAN = "scheduled_scan"  # a7 săn theo lịch
    TREND_RADAR = "trend_radar"  # a5 radar xu hướng
    DEMAND_DIGEST = "demand_digest"  # a6 gom nhu cầu khách


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CandidateStage(StrEnum):
    """Giai đoạn trên bảng chọn (c1). Chỉ `selected` mới thành product."""

    CANDIDATE = "candidate"
    SAMPLE = "sample"  # mua mẫu
    TRIAL = "trial"  # đang thử
    SELECTED = "selected"
    REJECTED = "rejected"


class CandidateOrigin(StrEnum):
    BRIEF_SCAN = "brief_scan"
    LINK = "link"
    IMAGE = "image"
    TREND = "trend"
    DEMAND = "demand"
    MANUAL = "manual"


class TrendStatus(StrEnum):
    NEW = "new"
    WATCHING = "watching"
    CONVERTED = "converted"  # đã thành ứng viên
    DISMISSED = "dismissed"


class DemandSource(StrEnum):
    COMMENT = "comment"
    MESSAGE = "message"
    FIND_REQUEST = "find_request"  # trang Nhờ tìm (e9)
    ASSISTANT = "assistant"  # trợ lý web (e7)
    MANUAL = "manual"


class DemandStatus(StrEnum):
    OPEN = "open"
    SEARCHING = "searching"  # đã mở đề tìm
    FOUND = "found"
    DISMISSED = "dismissed"


class SourcingBrief(UUIDPk, Timestamps, Base):
    """Đề tìm hàng (a1): lời chị dặn → bộ lọc AI hiểu. Đề đã lưu có thể chạy theo lịch (a7)."""

    __tablename__ = "sourcing_briefs"

    title: Mapped[str] = mapped_column(String(200))
    raw_text: Mapped[str] = mapped_column(Text, comment="Nguyên văn chị nói/gõ")
    input_mode: Mapped[BriefInputMode] = mapped_column(enum_col(BriefInputMode), default=BriefInputMode.TEXT)
    voice_storage_key: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[BriefStatus] = mapped_column(enum_col(BriefStatus), default=BriefStatus.DRAFT, index=True)
    interpretation: Mapped[str | None] = mapped_column(Text, comment="AI diễn giải lại để chị xem nó hiểu thế nào")
    filters: Mapped[dict[str, Any]] = json_obj(
        comment="Bộ lọc có cấu trúc: must/must_not/prefer, chất liệu, kích thước..."
    )
    keywords_vi: Mapped[list[Any]] = json_list()
    keywords_translated: Mapped[dict[str, Any]] = json_obj(comment='{"zh": [...], "ja": [...], "en": [...]}')
    platforms: Mapped[list[Any]] = json_list(comment="Danh sách SourcePlatform cần quét")
    category_id: Mapped[uuid.UUID | None] = fk("categories")
    price_min_vnd: Mapped[int | None] = money_opt()
    price_max_vnd: Mapped[int | None] = money_opt(comment="Giá bán dự kiến tối đa ở VN")
    target_landed_cost_max_vnd: Mapped[int | None] = money_opt()
    confirmed_at: Mapped[datetime | None]
    # săn theo lịch (a7)
    is_scheduled: Mapped[bool] = flag()
    schedule_interval_days: Mapped[int | None] = mapped_column(Integer)
    next_run_at: Mapped[datetime | None] = mapped_column(index=True)
    last_run_at: Mapped[datetime | None]
    alert_min_score: Mapped[int | None] = mapped_column(Integer, comment="Chỉ báo khi ứng viên mới đạt ngưỡng điểm này")
    demand_signal_id: Mapped[uuid.UUID | None] = fk("demand_signals", use_alter=True)
    find_request_id: Mapped[uuid.UUID | None] = fk("find_requests", use_alter=True)
    created_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)

    runs: Mapped[list[SourcingRun]] = relationship(back_populates="brief", lazy="raise", passive_deletes=True)
    candidates: Mapped[list[Candidate]] = relationship(back_populates="brief", lazy="raise", passive_deletes=True)


class SourcingRun(UUIDPk, Timestamps, Base):
    """Một lượt AI đi tìm (quét đề, lấy link, tìm ảnh, radar, gom nhu cầu)."""

    __tablename__ = "sourcing_runs"

    brief_id: Mapped[uuid.UUID | None] = fk("sourcing_briefs", ondelete="CASCADE")
    kind: Mapped[RunKind] = mapped_column(enum_col(RunKind), index=True)
    status: Mapped[RunStatus] = mapped_column(enum_col(RunStatus), default=RunStatus.QUEUED, index=True)
    input: Mapped[dict[str, Any]] = json_obj(comment="url / storage_key ảnh / từ khoá đã dùng")
    platforms: Mapped[list[Any]] = json_list()
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    found_count: Mapped[int] = count()
    new_count: Mapped[int] = count()
    above_threshold_count: Mapped[int] = count()
    error: Mapped[str | None] = mapped_column(Text)
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)

    brief: Mapped[SourcingBrief | None] = relationship(back_populates="runs", lazy="raise")


class Candidate(UUIDPk, Timestamps, Base):
    """Ứng viên: một sản phẩm cụ thể ở một nguồn. Đi qua bảng chọn (`stage`), `selected` thì thành product."""

    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint("source_platform", "source_external_id", name="uq_candidates_source"),
        Index("ix_candidates_brief_stage", "brief_id", "stage"),
        Index("ix_candidates_stage_position", "stage", "board_position"),
    )

    brief_id: Mapped[uuid.UUID | None] = fk("sourcing_briefs")
    run_id: Mapped[uuid.UUID | None] = fk("sourcing_runs")
    origin: Mapped[CandidateOrigin] = mapped_column(enum_col(CandidateOrigin), default=CandidateOrigin.BRIEF_SCAN)
    stage: Mapped[CandidateStage] = mapped_column(enum_col(CandidateStage), default=CandidateStage.CANDIDATE)
    stage_changed_at: Mapped[datetime | None]
    board_position: Mapped[int] = count(comment="Thứ tự trong cột của bảng chọn")
    category_id: Mapped[uuid.UUID | None] = fk("categories")
    # nguồn
    source_platform: Mapped[SourcePlatform] = mapped_column(enum_col(SourcePlatform), index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_external_id: Mapped[str | None] = mapped_column(String(120))
    supplier_id: Mapped[uuid.UUID | None] = fk("suppliers")
    seller_name: Mapped[str | None] = mapped_column(String(200))
    seller_url: Mapped[str | None] = mapped_column(Text)
    # nội dung (bản gốc + bản dịch)
    original_language: Mapped[Language] = mapped_column(enum_col(Language), default=Language.ZH)
    title_original: Mapped[str | None] = mapped_column(Text)
    title_vi: Mapped[str] = mapped_column(String(300))
    description_original: Mapped[str | None] = mapped_column(Text)
    description_vi: Mapped[str | None] = mapped_column(Text)
    specs: Mapped[dict[str, Any]] = json_obj(comment="Thông số đã dịch, khoá tiếng Việt")
    variants: Mapped[list[Any]] = json_list()
    images: Mapped[list[Any]] = json_list(comment="URL ảnh từ nguồn")
    main_image_url: Mapped[str | None] = mapped_column(Text)
    # giá ở nguồn
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price_currency: Mapped[str | None] = mapped_column(String(3))
    price_vnd_estimate: Mapped[int | None] = money_opt(comment="Quy đổi nhanh, chưa gồm phí")
    moq: Mapped[int | None] = mapped_column(Integer)
    weight_grams: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    review_count: Mapped[int | None] = mapped_column(Integer)
    sales_count: Mapped[int | None] = mapped_column(Integer)
    # xếp hạng
    ai_score: Mapped[int | None] = mapped_column(Integer, comment="0–100: điểm khớp đề + gu chị (c6)")
    rank_reason: Mapped[str | None] = mapped_column(Text)
    image_hash: Mapped[str | None] = mapped_column(String(64), index=True, comment="Băm ảnh để gom cùng mẫu (a3, b7)")
    same_model_group: Mapped[str | None] = mapped_column(String(64), index=True, comment="Cùng mẫu ở nhiều shop")
    trend_signal_id: Mapped[uuid.UUID | None] = fk("trend_signals")
    demand_signal_id: Mapped[uuid.UUID | None] = fk("demand_signals")
    is_archived: Mapped[bool] = flag()
    notes: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict[str, Any]] = json_obj(comment="Dữ liệu gốc từ nguồn (để tra lại)")

    brief: Mapped[SourcingBrief | None] = relationship(back_populates="candidates", lazy="raise")


class TrendSignal(UUIDPk, Timestamps, Base):
    """Radar xu hướng (a5): món đang lên ở Tiểu Hồng Thư, @cosme, TikTok Shop VN..."""

    __tablename__ = "trend_signals"
    __table_args__ = (UniqueConstraint("platform", "url", "detected_on", name="uq_trend_signals_platform_url_day"),)

    platform: Mapped[SourcePlatform] = mapped_column(enum_col(SourcePlatform))
    title: Mapped[str] = mapped_column(Text)
    title_vi: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text, comment="Vì sao đáng xem")
    metrics: Mapped[dict[str, Any]] = json_obj()
    score: Mapped[int | None] = mapped_column(Integer)
    detected_on: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[TrendStatus] = mapped_column(enum_col(TrendStatus), default=TrendStatus.NEW, index=True)
    category_id: Mapped[uuid.UUID | None] = fk("categories")
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL", use_alter=True)
    )
    run_id: Mapped[uuid.UUID | None] = fk("sourcing_runs")


class DemandSignal(UUIDPk, Timestamps, Base):
    """Nhu cầu khách (a6): gom câu hỏi / lời nhờ tìm thành một nhu cầu, xếp theo số người hỏi."""

    __tablename__ = "demand_signals"

    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    normalized_key: Mapped[str] = mapped_column(String(200), unique=True, comment="Khoá gộp (không dấu, rút gọn)")
    category_id: Mapped[uuid.UUID | None] = fk("categories")
    status: Mapped[DemandStatus] = mapped_column(enum_col(DemandStatus), default=DemandStatus.OPEN, index=True)
    ask_count: Mapped[int] = count(comment="Số người khác nhau đã hỏi")
    mention_count: Mapped[int] = count()
    first_asked_at: Mapped[datetime | None]
    last_asked_at: Mapped[datetime | None] = mapped_column(index=True)
    find_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("find_requests.id", ondelete="SET NULL", use_alter=True)
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL", use_alter=True), comment="Món đã tìm được"
    )

    mentions: Mapped[list[DemandMention]] = relationship(back_populates="signal", lazy="raise", passive_deletes=True)


class DemandMention(UUIDPk, CreatedAt, Base):
    """Một lần khách nhắc tới nhu cầu (từ bình luận, tin nhắn, trợ lý web, trang Nhờ tìm)."""

    __tablename__ = "demand_mentions"

    signal_id: Mapped[uuid.UUID] = fk("demand_signals", ondelete="CASCADE", nullable=False)
    source: Mapped[DemandSource] = mapped_column(enum_col(DemandSource))
    channel: Mapped[Channel | None] = mapped_column(enum_col(Channel))
    customer_id: Mapped[uuid.UUID | None] = fk("customers")
    source_type: Mapped[str | None] = mapped_column(String(60), comment="messages / find_requests / assistant_messages")
    source_id: Mapped[uuid.UUID | None]
    text: Mapped[str] = mapped_column(Text)

    signal: Mapped[DemandSignal] = relationship(back_populates="mentions", lazy="raise")
