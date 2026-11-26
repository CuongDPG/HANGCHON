"""Khuôn vào/ra của tác vụ AI trong module assessment (b1–b7)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Level = Literal["info", "warning", "danger"]


# ---- b2: đọc hộ đánh giá -----------------------------------------------------------------------------------------


class ReviewIn(BaseModel):
    id: str
    rating: int
    text: str
    language: str


class DigestIn(BaseModel):
    product_title: str
    reviews: list[ReviewIn]


class DigestPoint(BaseModel):
    point: str = Field(description="Ý khen/chê lặp lại, tiếng Việt, ngắn")
    count: int = Field(ge=1, description="Số đánh giá nhắc tới ý này (trong số đã đọc)")
    review_ids: list[str] = Field(default_factory=list, description="Tối đa 3 id đánh giá để trích dẫn")


class Translation(BaseModel):
    id: str
    vi: str


class DigestOut(BaseModel):
    praise: list[DigestPoint] = Field(default_factory=list)
    complaints: list[DigestPoint] = Field(default_factory=list)
    low_star_summary: str | None = Field(default=None, description="Tóm tắt riêng đánh giá 1–2 sao")
    translations: list[Translation] = Field(
        default_factory=list, description="Bản dịch tiếng Việt của mọi đánh giá được trích và mọi đánh giá 1–2 sao"
    )
    suspicious_ratio: float = Field(ge=0, le=1, description="Tỉ lệ đánh giá có dấu hiệu ảo (0–1)")
    suspicious_notes: str | None = None


# ---- b5: giá bán ở Việt Nam --------------------------------------------------------------------------------------


class ListingIn(BaseModel):
    ref: str
    title: str
    shop: str | None = None
    price_vnd: int


class MatchIn(BaseModel):
    product_title: str
    specs: dict[str, str] = Field(default_factory=dict)
    listings: list[ListingIn]


class MatchItem(BaseModel):
    ref: str
    confidence: float = Field(ge=0, le=1, description="Có đúng cùng món (cùng kiểu, cùng cỡ) không")
    note: str | None = None


class MatchOut(BaseModel):
    matches: list[MatchItem]


# ---- b6: an toàn và giấy tờ --------------------------------------------------------------------------------------


class SafetyIn(BaseModel):
    title: str
    description: str | None = None
    specs: dict[str, str] = Field(default_factory=dict)
    category: str | None = None
    platform: str


class Finding(BaseModel):
    level: Level
    text: str


class SafetyOut(BaseModel):
    status: Literal["ok", "warning", "blocked"]
    has_battery: bool = False
    has_liquid: bool = False
    food_contact: bool = False
    is_cosmetic: bool = False
    is_food: bool = False
    is_electrical: bool = False
    materials: list[str] = Field(default_factory=list)
    requires_declaration: bool = Field(default=False, description="Thuộc nhóm phải công bố (mỹ phẩm, thực phẩm...)")
    declaration: str | None = Field(default=None, description="Loại công bố / giấy phép cần có")
    docs_needed: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    customer_warnings: list[str] = Field(
        default_factory=list, description="0–3 câu cảnh báo khách cần biết khi dùng; không ghi chuyện giấy tờ"
    )


# ---- b1 + b4: hồ sơ và chấm điểm ---------------------------------------------------------------------------------


class CriterionIn(BaseModel):
    key: str
    label: str
    weight: float
    description: str | None = None


class EvaluateIn(BaseModel):
    product: dict[str, object]
    brief: dict[str, object] = Field(default_factory=dict)
    criteria: list[CriterionIn]
    reviews: dict[str, object] = Field(default_factory=dict)
    market: dict[str, object] = Field(default_factory=dict)
    cost: dict[str, object] = Field(default_factory=dict)
    safety: dict[str, object] = Field(default_factory=dict)
    risks: list[dict[str, object]] = Field(default_factory=list)


class ScoreItem(BaseModel):
    key: str
    score: float = Field(ge=0, le=10, description="Điểm 0–10 cho tiêu chí")
    reason: str = Field(description="Căn cứ cụ thể từ dữ liệu đã cho")


class EvaluateOut(BaseModel):
    summary: str = Field(description="3–5 câu, đọc trong hai phút, nói cả điều chưa ưng")
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list, description="Chỗ AI chưa chắc, để chị kiểm khi thử")
    scores: list[ScoreItem]


# ---- b3: so sánh -------------------------------------------------------------------------------------------------


class CompareCandidate(BaseModel):
    id: str
    name: str = Field(description="Tên gọi món này trong kết luận (khách quan, đã phân biệt các món trùng tên)")
    title: str
    values: dict[str, str]


class CompareIn(BaseModel):
    criteria: list[dict[str, str]]
    candidates: list[CompareCandidate]


class CompareNote(BaseModel):
    candidate_id: str
    key: str
    note: str


class CompareOut(BaseModel):
    conclusion: str = Field(description="2–3 câu: món nào hợp nhất với đề và vì sao, món nào nên loại")
    recommended_id: str | None = None
    notes: list[CompareNote] = Field(default_factory=list)
