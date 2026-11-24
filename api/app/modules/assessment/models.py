"""assessment — thẩm định và so sánh (b1–b7): hồ sơ thẩm định, chấm điểm theo khung, đọc hộ đánh giá,
giá bán ở VN, bảng so sánh, kiểm an toàn, cảnh báo hàng nhái / đánh giá ảo."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamps, UUIDPk, count, enum_col, fk, flag, json_list, json_obj, money_opt
from app.core.enums import Language, SourcePlatform, StrEnum


class AssessmentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    STALE = "stale"  # nguồn đổi (giá, đánh giá), cần chạy lại


class ScoreStatus(StrEnum):
    NONE = "none"
    AI_DRAFT = "ai_draft"  # AI chấm nháp, chờ chị (b4)
    CONFIRMED = "confirmed"  # chị đã duyệt/sửa điểm


class SafetyStatus(StrEnum):
    UNCHECKED = "unchecked"
    OK = "ok"
    WARNING = "warning"  # cần lưu ý (pin, chất lỏng, tiếp xúc thực phẩm...)
    BLOCKED = "blocked"  # không nên bán / phải công bố mà chưa có giấy tờ


class RiskLevel(StrEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ScoringProfile(UUIDPk, Timestamps, Base):
    """Khung chấm điểm của chị (b4): bảy tiêu chí, trọng số chị đặt; có thể riêng theo nhóm hàng."""

    __tablename__ = "scoring_profiles"

    name: Mapped[str] = mapped_column(String(120))
    category_id: Mapped[uuid.UUID | None] = fk("categories")
    is_default: Mapped[bool] = flag()
    criteria: Mapped[list[Any]] = json_list(comment='[{"key","label","weight","description"}] — tổng trọng số 100')
    pass_score: Mapped[int | None] = mapped_column(Integer, comment="Ngưỡng điểm để vào bảng chọn")


class Assessment(UUIDPk, Timestamps, Base):
    """Hồ sơ thẩm định (b1): một trang cho mỗi ứng viên. Mỗi ứng viên có một hồ sơ hiện hành (`version` tăng khi chạy lại)."""

    __tablename__ = "assessments"

    candidate_id: Mapped[uuid.UUID] = fk("candidates", ondelete="CASCADE", nullable=False, unique=True)
    status: Mapped[AssessmentStatus] = mapped_column(enum_col(AssessmentStatus), default=AssessmentStatus.PENDING)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    summary: Mapped[str | None] = mapped_column(Text, comment="Đọc trong hai phút")
    strengths: Mapped[list[Any]] = json_list()
    weaknesses: Mapped[list[Any]] = json_list()
    specs: Mapped[dict[str, Any]] = json_obj(comment="Thông số chuẩn hoá")
    buyer_photos: Mapped[list[Any]] = json_list(comment="Ảnh thật từ người mua (URL + nguồn)")
    price_overview: Mapped[dict[str, Any]] = json_obj(comment="Giá ở các nơi (nguồn + VN) tóm tắt")
    # b4 chấm điểm
    scoring_profile_id: Mapped[uuid.UUID | None] = fk("scoring_profiles")
    score_status: Mapped[ScoreStatus] = mapped_column(enum_col(ScoreStatus), default=ScoreStatus.NONE)
    score_total: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), comment="0–100 theo trọng số")
    score_confirmed_at: Mapped[datetime | None]
    score_confirmed_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)
    # b6 an toàn và giấy tờ
    safety_status: Mapped[SafetyStatus] = mapped_column(enum_col(SafetyStatus), default=SafetyStatus.UNCHECKED)
    safety: Mapped[dict[str, Any]] = json_obj(
        comment="has_battery, has_liquid, food_contact, materials, ingredients, requires_declaration, docs_needed, notes"
    )
    safety_confirmed_at: Mapped[datetime | None]
    safety_confirmed_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)
    # b7 hàng nhái / đánh giá ảo
    counterfeit_risk: Mapped[RiskLevel] = mapped_column(enum_col(RiskLevel), default=RiskLevel.UNKNOWN)
    fake_review_risk: Mapped[RiskLevel] = mapped_column(enum_col(RiskLevel), default=RiskLevel.UNKNOWN)
    risk_notes: Mapped[list[Any]] = json_list(comment="Căn cứ: ảnh trùng, giá thấp bất thường, đánh giá dồn ngày...")
    # dẫn nguồn (dùng lại cho trợ lý web e7)
    sources: Mapped[list[Any]] = json_list(comment='[{"url","title","kind"}]')
    ai_generated: Mapped[bool] = flag(True)
    generated_at: Mapped[datetime | None]
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)
    error: Mapped[str | None] = mapped_column(Text)

    scores: Mapped[list[AssessmentScore]] = relationship(
        back_populates="assessment", lazy="selectin", cascade="all, delete-orphan", order_by="AssessmentScore.position"
    )


class AssessmentScore(UUIDPk, Timestamps, Base):
    """Điểm từng tiêu chí (b4): AI chấm nháp + căn cứ, chị sửa điểm."""

    __tablename__ = "assessment_scores"
    __table_args__ = (UniqueConstraint("assessment_id", "criterion_key", name="uq_assessment_scores_criterion"),)

    assessment_id: Mapped[uuid.UUID] = fk("assessments", ondelete="CASCADE", nullable=False)
    criterion_key: Mapped[str] = mapped_column(String(60))
    criterion_label: Mapped[str] = mapped_column(String(120))
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    position: Mapped[int] = count()
    ai_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), comment="0–10")
    ai_reason: Mapped[str | None] = mapped_column(Text)
    owner_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    owner_note: Mapped[str | None] = mapped_column(Text)

    assessment: Mapped[Assessment] = relationship(back_populates="scores", lazy="raise")


class ReviewDigest(UUIDPk, Timestamps, Base):
    """Đọc hộ đánh giá (b2): tóm tắt khen/chê lặp lại, tách riêng 1–2 sao; tỉ lệ đánh giá đáng ngờ (b7)."""

    __tablename__ = "review_digests"
    __table_args__ = (Index("ix_review_digests_candidate", "candidate_id", "created_at"),)

    candidate_id: Mapped[uuid.UUID] = fk("candidates", ondelete="CASCADE", nullable=False, index=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[SourcePlatform | None] = mapped_column(enum_col(SourcePlatform))
    language: Mapped[Language | None] = mapped_column(enum_col(Language))
    reviews_read: Mapped[int] = count()
    rating_avg: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    rating_histogram: Mapped[dict[str, Any]] = json_obj(comment='{"5": 120, "4": 30, ...}')
    praise: Mapped[list[Any]] = json_list(comment='[{"point","count","quotes":[{"original","vi"}]}]')
    complaints: Mapped[list[Any]] = json_list()
    low_star_summary: Mapped[str | None] = mapped_column(Text)
    low_star_reviews: Mapped[list[Any]] = json_list(comment="Đánh giá 1–2 sao đã dịch")
    suspicious_ratio: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    suspicious_notes: Mapped[str | None] = mapped_column(Text)
    sample_photos: Mapped[list[Any]] = json_list()
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)


class MarketPrice(UUIDPk, Timestamps, Base):
    """Giá cùng món ở Việt Nam (b5) — để biết còn chỗ cho mình không."""

    __tablename__ = "market_prices"
    __table_args__ = (
        Index("ix_market_prices_candidate", "candidate_id", "captured_at"),
        Index("ix_market_prices_product", "product_id", "captured_at"),
    )

    candidate_id: Mapped[uuid.UUID | None] = fk("candidates", ondelete="CASCADE", index=False)
    product_id: Mapped[uuid.UUID | None] = fk("products", ondelete="CASCADE", index=False)
    platform: Mapped[SourcePlatform] = mapped_column(enum_col(SourcePlatform))
    shop_name: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    price_vnd: Mapped[int] = mapped_column(BigInteger)
    original_price_vnd: Mapped[int | None] = money_opt()
    sold_count: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), comment="0–1: có đúng cùng món không")
    captured_at: Mapped[datetime]
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)


class Comparison(UUIDPk, Timestamps, Base):
    """Bảng so sánh cạnh nhau (b3): 3–5 ứng viên cùng loại theo tiêu chí chị quan tâm."""

    __tablename__ = "comparisons"

    title: Mapped[str] = mapped_column(String(200))
    brief_id: Mapped[uuid.UUID | None] = fk("sourcing_briefs")
    criteria: Mapped[list[Any]] = json_list(comment='[{"key","label"}]')
    conclusion: Mapped[str | None] = mapped_column(Text)
    recommended_candidate_id: Mapped[uuid.UUID | None] = fk("candidates", index=False)
    ai_run_id: Mapped[uuid.UUID | None] = fk("ai_runs", index=False)

    items: Mapped[list[ComparisonItem]] = relationship(
        back_populates="comparison", lazy="selectin", cascade="all, delete-orphan", order_by="ComparisonItem.position"
    )


class ComparisonItem(UUIDPk, Base):
    __tablename__ = "comparison_items"
    __table_args__ = (UniqueConstraint("comparison_id", "candidate_id", name="uq_comparison_items_candidate"),)

    comparison_id: Mapped[uuid.UUID] = fk("comparisons", ondelete="CASCADE", nullable=False)
    candidate_id: Mapped[uuid.UUID] = fk("candidates", ondelete="CASCADE", nullable=False)
    position: Mapped[int] = count()
    values: Mapped[dict[str, Any]] = json_obj(comment="criterion_key → {value, note, best: bool}")
    landed_cost_vnd: Mapped[int | None] = money_opt()

    comparison: Mapped[Comparison] = relationship(back_populates="items", lazy="raise")
