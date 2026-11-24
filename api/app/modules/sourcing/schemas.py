"""Schema đọc cơ bản của sourcing (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

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
