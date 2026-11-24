"""Schema đọc cơ bản của assessment (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.enums import Language, SourcePlatform
from app.modules.assessment.models import AssessmentStatus, RiskLevel, SafetyStatus, ScoreStatus


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ScoringProfileOut(ORM):
    """Khung chấm điểm của chị (b4): bảy tiêu chí, trọng số chị đặt; có thể riêng theo nhóm hàng."""

    id: uuid.UUID
    name: str
    category_id: uuid.UUID | None
    is_default: bool
    criteria: list[Any]
    pass_score: int | None
    created_at: datetime
    updated_at: datetime


class AssessmentOut(ORM):
    """Hồ sơ thẩm định (b1): một trang cho mỗi ứng viên. Mỗi ứng viên có một hồ sơ hiện hành (`version` tăng khi chạy lại)."""

    id: uuid.UUID
    candidate_id: uuid.UUID
    status: AssessmentStatus
    version: int
    summary: str | None
    strengths: list[Any]
    weaknesses: list[Any]
    specs: dict[str, Any]
    buyer_photos: list[Any]
    price_overview: dict[str, Any]
    scoring_profile_id: uuid.UUID | None
    score_status: ScoreStatus
    score_total: Decimal | None
    score_confirmed_at: datetime | None
    score_confirmed_by_id: uuid.UUID | None
    safety_status: SafetyStatus
    safety: dict[str, Any]
    safety_confirmed_at: datetime | None
    safety_confirmed_by_id: uuid.UUID | None
    counterfeit_risk: RiskLevel
    fake_review_risk: RiskLevel
    risk_notes: list[Any]
    sources: list[Any]
    ai_generated: bool
    generated_at: datetime | None
    ai_run_id: uuid.UUID | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class AssessmentScoreOut(ORM):
    """Điểm từng tiêu chí (b4): AI chấm nháp + căn cứ, chị sửa điểm."""

    id: uuid.UUID
    assessment_id: uuid.UUID
    criterion_key: str
    criterion_label: str
    weight: Decimal
    position: int
    ai_score: Decimal | None
    ai_reason: str | None
    owner_score: Decimal | None
    owner_note: str | None
    created_at: datetime
    updated_at: datetime


class ReviewDigestOut(ORM):
    """Đọc hộ đánh giá (b2): tóm tắt khen/chê lặp lại, tách riêng 1–2 sao; tỉ lệ đánh giá đáng ngờ (b7)."""

    id: uuid.UUID
    candidate_id: uuid.UUID
    source_url: str | None
    platform: SourcePlatform | None
    language: Language | None
    reviews_read: int
    rating_avg: Decimal | None
    rating_histogram: dict[str, Any]
    praise: list[Any]
    complaints: list[Any]
    low_star_summary: str | None
    low_star_reviews: list[Any]
    suspicious_ratio: Decimal | None
    suspicious_notes: str | None
    sample_photos: list[Any]
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class MarketPriceOut(ORM):
    """Giá cùng món ở Việt Nam (b5) — để biết còn chỗ cho mình không."""

    id: uuid.UUID
    candidate_id: uuid.UUID | None
    product_id: uuid.UUID | None
    platform: SourcePlatform
    shop_name: str | None
    title: str
    url: str
    price_vnd: int
    original_price_vnd: int | None
    sold_count: int | None
    rating: Decimal | None
    match_confidence: Decimal | None
    captured_at: datetime
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ComparisonOut(ORM):
    """Bảng so sánh cạnh nhau (b3): 3–5 ứng viên cùng loại theo tiêu chí chị quan tâm."""

    id: uuid.UUID
    title: str
    brief_id: uuid.UUID | None
    criteria: list[Any]
    conclusion: str | None
    recommended_candidate_id: uuid.UUID | None
    ai_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ComparisonItemOut(ORM):
    id: uuid.UUID
    comparison_id: uuid.UUID
    candidate_id: uuid.UUID
    position: int
    values: dict[str, Any]
    landed_cost_vnd: int | None
