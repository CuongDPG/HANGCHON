"""Schema đọc cơ bản của sourcing (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.core.enums import Channel, Language, SourcePlatform
from app.modules.sourcing.models import (
    BriefInputMode,
    BriefStatus,
    CandidateOrigin,
    CandidateStage,
    DemandSource,
    DemandStatus,
    RunKind,
    RunStatus,
    TrendStatus,
)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SourcingBriefOut(ORM):
    """Đề tìm hàng (a1): lời chị dặn → bộ lọc AI hiểu. Đề đã lưu có thể chạy theo lịch (a7)."""

    id: uuid.UUID
    title: str
    raw_text: str
    input_mode: BriefInputMode
    voice_storage_key: str | None
    status: BriefStatus
    interpretation: str | None
    filters: dict[str, Any]
    keywords_vi: list[Any]
    keywords_translated: dict[str, Any]
    platforms: list[Any]
    category_id: uuid.UUID | None
    price_min_vnd: int | None
    price_max_vnd: int | None
    target_landed_cost_max_vnd: int | None
    confirmed_at: datetime | None
    is_scheduled: bool
    schedule_interval_days: int | None
    next_run_at: datetime | None
    last_run_at: datetime | None
    alert_min_score: int | None
    demand_signal_id: uuid.UUID | None
    find_request_id: uuid.UUID | None
    created_by_id: uuid.UUID | None
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class SourcingRunOut(ORM):
    """Một lượt AI đi tìm (quét đề, lấy link, tìm ảnh, radar, gom nhu cầu)."""

    id: uuid.UUID
    brief_id: uuid.UUID | None
    kind: RunKind
    status: RunStatus
    input: dict[str, Any]
    platforms: list[Any]
    started_at: datetime | None
    finished_at: datetime | None
    found_count: int
    new_count: int
    above_threshold_count: int
    error: str | None
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class CandidateOut(ORM):
    """Ứng viên: một sản phẩm cụ thể ở một nguồn. Đi qua bảng chọn (`stage`), `selected` thì thành product."""

    id: uuid.UUID
    brief_id: uuid.UUID | None
    run_id: uuid.UUID | None
    origin: CandidateOrigin
    stage: CandidateStage
    stage_changed_at: datetime | None
    board_position: int
    category_id: uuid.UUID | None
    source_platform: SourcePlatform
    source_url: str | None
    source_external_id: str | None
    supplier_id: uuid.UUID | None
    seller_name: str | None
    seller_url: str | None
    original_language: Language
    title_original: str | None
    title_vi: str
    description_original: str | None
    description_vi: str | None
    specs: dict[str, Any]
    variants: list[Any]
    images: list[Any]
    main_image_url: str | None
    price_amount: Decimal | None
    price_currency: str | None
    price_vnd_estimate: int | None
    moq: int | None
    weight_grams: int | None
    rating: Decimal | None
    review_count: int | None
    sales_count: int | None
    ai_score: int | None
    rank_reason: str | None
    image_hash: str | None
    same_model_group: str | None
    trend_signal_id: uuid.UUID | None
    demand_signal_id: uuid.UUID | None
    is_archived: bool
    notes: str | None
    raw: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TrendSignalOut(ORM):
    """Radar xu hướng (a5): món đang lên ở Tiểu Hồng Thư, @cosme, TikTok Shop VN..."""

    id: uuid.UUID
    platform: SourcePlatform
    title: str
    title_vi: str
    url: str
    image_url: str | None
    reason: str | None
    metrics: dict[str, Any]
    score: int | None
    detected_on: date
    status: TrendStatus
    category_id: uuid.UUID | None
    candidate_id: uuid.UUID | None
    run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DemandSignalOut(ORM):
    """Nhu cầu khách (a6): gom câu hỏi / lời nhờ tìm thành một nhu cầu, xếp theo số người hỏi."""

    id: uuid.UUID
    title: str
    description: str | None
    normalized_key: str
    category_id: uuid.UUID | None
    status: DemandStatus
    ask_count: int
    mention_count: int
    first_asked_at: datetime | None
    last_asked_at: datetime | None
    find_request_id: uuid.UUID | None
    product_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DemandMentionOut(ORM):
    """Một lần khách nhắc tới nhu cầu (từ bình luận, tin nhắn, trợ lý web, trang Nhờ chị tìm)."""

    id: uuid.UUID
    signal_id: uuid.UUID
    source: DemandSource
    channel: Channel | None
    customer_id: uuid.UUID | None
    source_type: str | None
    source_id: uuid.UUID | None
    text: str
    created_at: datetime


# ---- schema tạo/sửa và schema hiển thị (viết thêm khi làm router) ------------------------------------------------


class BriefIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000, description="Lời chị gõ hoặc nói")
    input_mode: BriefInputMode = BriefInputMode.TEXT


class ReinterpretIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class BriefFilters(BaseModel):
    """Tiêu chí có cấu trúc (hiện thành chip «AI hiểu là» sửa được)."""

    product_type: str | None = None
    category: str | None = None
    materials: list[str] = Field(default_factory=list)
    must: list[str] = Field(default_factory=list)
    must_not: list[str] = Field(default_factory=list)
    prefer: list[str] = Field(default_factory=list)
    origins: list[str] = Field(default_factory=list)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    min_reviews: int | None = Field(default=None, ge=0)
    unclear: list[str] = Field(default_factory=list)
    trend_signal_id: str | None = None


class BriefPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    filters: BriefFilters | None = None
    keywords_vi: list[str] | None = None
    keywords_translated: dict[str, list[str]] | None = None
    platforms: list[SourcePlatform] | None = None
    target_landed_cost_max_vnd: int | None = Field(default=None, ge=0)
    price_max_vnd: int | None = Field(default=None, ge=0)
    clear_landed_cost: bool = False
    is_scheduled: bool | None = None
    schedule_interval_days: int | None = Field(default=None, ge=1, le=60)
    alert_min_score: int | None = Field(default=None, ge=0, le=100)
    status: BriefStatus | None = None

    @field_validator("keywords_translated")
    @classmethod
    def _langs(cls, v: dict[str, list[str]] | None) -> dict[str, list[str]] | None:
        if v is not None and set(v) - {"zh", "ja", "en", "ko"}:
            raise ValueError("Chỉ nhận từ khoá zh, ja, en, ko")
        return v


class RunView(SourcingRunOut):
    progress: dict[str, Any] = Field(default_factory=dict)


class BriefCard(SourcingBriefOut):
    candidate_count: int = 0
    selected_count: int = 0
    last_run: RunView | None = None


class ImportLinkIn(BaseModel):
    url: HttpUrl
    brief_id: uuid.UUID | None = None


class Offer(BaseModel):
    platform: SourcePlatform
    url: str | None = None
    seller_name: str | None = None
    price_amount: Decimal | None = None
    currency: str | None = None
    price_vnd_estimate: int | None = None
    rating: float | None = None
    review_count: int | None = None


class GuidanceNote(BaseModel):
    kind: Literal["principle", "taste"]
    delta: int
    text: str


class RankGuidance(BaseModel):
    """c5 + c6: nguyên tắc và gu đã chỉnh điểm AI thế nào (để chị thấy vì sao món lên/xuống)."""

    base_score: int | None = None
    delta: int = 0
    violates: bool = False
    notes: list[GuidanceNote] = Field(default_factory=list)


class CandidateCard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brief_id: uuid.UUID | None
    origin: CandidateOrigin
    stage: CandidateStage
    source_platform: SourcePlatform
    source_url: str | None
    seller_name: str | None
    title_vi: str
    title_original: str | None
    main_image_url: str | None
    price_amount: Decimal | None
    price_currency: str | None
    price_vnd_estimate: int | None
    landed_estimate_vnd: int | None = None
    rating: Decimal | None
    review_count: int | None
    sales_count: int | None
    ai_score: int | None
    rank_reason: str | None
    offers_count: int = 0
    guidance: RankGuidance | None = None
    assessment_status: str | None = None
    score_total: Decimal | None = None
    created_at: datetime


class CandidateDetail(CandidateOut):
    landed_estimate_vnd: int | None = None
    guidance: RankGuidance | None = None
    offers: list[Offer] = Field(default_factory=list)


class TrendCard(TrendSignalOut):
    brief_id: uuid.UUID | None = None


class DemandView(DemandSignalOut):
    mentions: list[DemandMentionOut] = Field(default_factory=list)
    brief_id: uuid.UUID | None = None
