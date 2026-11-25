"""Khuôn vào/ra của các tác vụ AI trong module content."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ChannelKey = Literal["facebook", "instagram", "threads", "tiktok", "zalo_oa"]


class ProductFacts(BaseModel):
    """Hồ sơ sản phẩm — nguồn sự thật duy nhất cho số liệu trong bài. Không kèm quá trình chọn (số món đã xem, mẫu bị loại)."""

    id: str
    name: str
    subtitle: str | None = None
    short_description: str | None = None
    price_vnd: int = 0
    compare_at_price_vnd: int | None = None
    specs: list[dict] = Field(default_factory=list)
    trial_days: int | None = None
    reason_selected: str | None = None
    not_satisfied: str | None = None
    image_count: int = 0
    image_alts: list[str] = Field(default_factory=list)
    url: str | None = None


class DropItemFacts(BaseModel):
    product_id: str
    name: str
    price_vnd: int
    slots_total: int | None = None
    slots_left: int | None = None


class DropFacts(BaseModel):
    id: str
    code: str
    title: str
    description: str | None = None
    closes_at_text: str | None = None
    expected_arrival_text: str | None = None
    deposit_pct: int | None = None
    items: list[DropItemFacts] = Field(default_factory=list)
    url: str | None = None


class VoiceCard(BaseModel):
    style_summary: str | None = None
    pronouns: str | None = None
    sentence_style: str | None = None
    rules: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    vocabulary: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class ComposeIn(BaseModel):
    kind: Literal["product", "drop"]
    product: ProductFacts | None = None
    drop: DropFacts | None = None
    trial_notes: list[str] = Field(default_factory=list)
    voice: VoiceCard = Field(default_factory=VoiceCard)
    channels: list[ChannelKey]
    channel_guides: dict[str, str] = Field(default_factory=dict)
    insights: list[str] = Field(default_factory=list)
    instruction: str | None = None


class Scene(BaseModel):
    scene: int
    seconds: int
    visual: str
    voiceover: str
    on_screen_text: str


class Slide(BaseModel):
    image_index: int
    caption: str


class ChannelDraftOut(BaseModel):
    channel: ChannelKey
    title: str = Field(description="Tên ngắn nội bộ cho bài, vd «3 tuần thử bình»")
    body: str
    hashtags: list[str] = Field(default_factory=list)
    slides: list[Slide] = Field(default_factory=list, description="Instagram: thứ tự ảnh + chú thích từng ảnh")
    scenes: list[Scene] = Field(default_factory=list, description="TikTok: kịch bản theo cảnh")


class ComposeOut(BaseModel):
    drafts: list[ChannelDraftOut]


class RewriteIn(BaseModel):
    channel: ChannelKey
    current: ChannelDraftOut
    instruction: str
    product: ProductFacts | None = None
    drop: DropFacts | None = None
    voice: VoiceCard = Field(default_factory=VoiceCard)
    channel_guide: str = ""


class CheckIn(BaseModel):
    channel: ChannelKey
    text: str
    product: ProductFacts | None = None
    drop: DropFacts | None = None


class CheckIssue(BaseModel):
    quote: str = Field(description="Đoạn chữ có vấn đề, trích nguyên văn")
    detail: str
    suggestion: str | None = None


class CheckOut(BaseModel):
    number_issues: list[CheckIssue] = Field(default_factory=list)
    claim_issues: list[CheckIssue] = Field(default_factory=list)
    note: str | None = None


class VoiceLearnIn(BaseModel):
    samples: list[str]
    notes: str | None = None
    spoken: list[str] = Field(
        default_factory=list, description="Lời chị nói, chép từ giọng nói (không có dấu câu chuẩn)"
    )
    current: VoiceCard = Field(default_factory=VoiceCard)


class VoiceLearnOut(BaseModel):
    style_summary: str
    pronouns: str
    sentence_style: str
    vocabulary: list[str]
    rules: list[str]
    avoid: list[str]
    examples: list[str]


class EmptySlot(BaseModel):
    index: int
    day_label: str
    time: str
    channel: ChannelKey


class PlanProduct(BaseModel):
    id: str
    name: str
    days_since_last_post: int | None = None
    orders_from_posts: int = 0
    reason_selected: str | None = None


class PlanWeekIn(BaseModel):
    week_label: str
    empty_slots: list[EmptySlot]
    products: list[PlanProduct]
    open_drops: list[str] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)


class SlotIdea(BaseModel):
    slot_index: int
    product_id: str | None = None
    idea: str
    reason: str


class PlanWeekOut(BaseModel):
    suggestions: list[SlotIdea]


class ClipFacts(BaseModel):
    index: int
    duration_seconds: float
    note: str | None = None


class VideoPlanIn(BaseModel):
    product: ProductFacts | None = None
    clips: list[ClipFacts]
    target_seconds: int = 24
    notes: str | None = None


class VideoSegment(BaseModel):
    clip_index: int
    start: float
    end: float
    caption: str


class MusicHint(BaseModel):
    mood: str
    suggestion: str
    bpm: int | None = None


class VideoPlanOut(BaseModel):
    summary: str
    segments: list[VideoSegment]
    music: MusicHint
    cover_text: str


class PostStat(BaseModel):
    post_id: str
    title: str
    channel: str
    format: str
    weekday: str
    hour: int
    length: int
    has_price: bool
    reach: int
    likes: int
    comments: int
    shares: int
    clicks: int
    orders: int
    revenue_vnd: int


class InsightIn(BaseModel):
    period_label: str
    posts: list[PostStat]


class InsightFinding(BaseModel):
    pattern: str
    evidence: str
    recommendation: str


class InsightOut(BaseModel):
    summary: str
    findings: list[InsightFinding] = Field(description="2–3 nhận xét")
    top_post_ids: list[str] = Field(default_factory=list)


class LiveQuestion(BaseModel):
    question: str
    product_id: str | None = None


class LiveIn(BaseModel):
    title: str
    minutes: int = 30
    products: list[ProductFacts]
    drop: DropFacts | None = None
    questions: list[LiveQuestion] = Field(default_factory=list)
    voice: VoiceCard = Field(default_factory=VoiceCard)


class LiveSegment(BaseModel):
    segment: str
    minutes: int
    notes: str


class LiveItem(BaseModel):
    product_id: str
    order: int
    name: str
    talking_points: list[str]
    demo: str
    price_note: str


class LiveFaq(BaseModel):
    q: str
    a: str
    product_id: str | None = None
    source: Literal["khach_hoi", "du_doan"] = "du_doan"


class LiveOut(BaseModel):
    outline: list[LiveSegment]
    items: list[LiveItem]
    faq: list[LiveFaq]
