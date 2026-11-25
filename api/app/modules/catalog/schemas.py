"""Schema đọc cơ bản của catalog (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.catalog.models import (
    DropStatus,
    FindRequestStatus,
    ImageKind,
    ImageStatus,
    MovementReason,
    ProductStatus,
    ReviewStatus,
    SaleMode,
)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CategoryOut(ORM):
    id: uuid.UUID
    name: str
    slug: str
    parent_id: uuid.UUID | None
    description: str | None
    position: int
    is_active: bool
    is_consumable: bool
    default_reorder_days: int | None
    default_target_margin_pct: int | None
    created_at: datetime
    updated_at: datetime


class ProductOut(ORM):
    """Sản phẩm trên website — chỉ sinh ra từ ứng viên `selected`. Mang «hồ sơ chọn» (e2): tỉ lệ chọn, thời gian thử,"""

    id: uuid.UUID
    candidate_id: uuid.UUID | None
    category_id: uuid.UUID | None
    slug: str
    sku: str | None
    name: str
    subtitle: str | None
    short_description: str | None
    description: str | None
    specs: list[Any]
    faq: list[Any]
    status: ProductStatus
    published_at: datetime | None
    sale_mode: SaleMode
    price_vnd: int
    compare_at_price_vnd: int | None
    landed_cost_vnd: int | None
    selected_count: int
    considered_count: int | None
    trial_days: int | None
    reason_selected: str | None
    not_satisfied: str | None
    rejected_alternatives: list[Any]
    dossier: dict[str, Any]
    weight_grams: int | None
    dimensions_cm: dict[str, Any]
    origin_country: str | None
    brand: str | None
    gtin: str | None
    shipping_notes: list[Any]
    is_consumable: bool
    reorder_days: int | None
    seo_title: str | None
    seo_description: str | None
    feed_enabled: bool
    ai_generated: bool
    content_approved_at: datetime | None
    approval_item_id: uuid.UUID | None
    rating_avg: float | None
    review_count: int
    created_at: datetime
    updated_at: datetime


class ProductVariantOut(ORM):
    """Phân loại (màu, cỡ). Sản phẩm một loại vẫn có thể không có dòng nào ở đây."""

    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    sku: str | None
    options: dict[str, Any]
    price_vnd: int | None
    position: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductImageOut(ORM):
    """Ảnh sản phẩm (e6): ảnh gốc chị chụp + bản đã xử lý (cắt, cân sáng, làm sạch nền)."""

    id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    kind: ImageKind
    status: ImageStatus
    original_key: str
    processed_key: str | None
    processing_ops: list[Any]
    width: int | None
    height: int | None
    alt: str | None
    position: int
    is_primary: bool
    ai_processed: bool
    created_at: datetime
    updated_at: datetime


class DropOut(ORM):
    """Đợt mở bán (e3): gom đơn có hạn chót, số suất, ngày hàng về dự kiến."""

    id: uuid.UUID
    code: str
    slug: str
    title: str
    description: str | None
    status: DropStatus
    opens_at: datetime | None
    closes_at: datetime | None
    expected_arrival_date: date | None
    actual_arrival_date: date | None
    deposit_pct: int | None
    approval_item_id: uuid.UUID | None
    announced_at: datetime | None
    summary: dict[str, Any]
    ai_generated: bool
    created_at: datetime
    updated_at: datetime


class DropItemOut(ORM):
    id: uuid.UUID
    drop_id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    price_vnd: int
    slots_total: int | None
    slots_reserved: int
    min_total_to_order: int | None
    max_per_order: int | None
    position: int
    created_at: datetime
    updated_at: datetime


class InventoryItemOut(ORM):
    """Tồn kho nhỏ (g8): số lượng các món giữ sẵn, báo khi sắp hết."""

    id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    on_hand: int
    reserved: int
    low_stock_threshold: int | None
    location: str | None
    unit_cost_vnd: int | None
    last_counted_at: datetime | None
    low_stock_alerted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InventoryMovementOut(ORM):
    id: uuid.UUID
    inventory_item_id: uuid.UUID
    delta_on_hand: int
    delta_reserved: int
    reason: MovementReason
    ref_type: str | None
    ref_id: uuid.UUID | None
    note: str | None
    created_by_id: uuid.UUID | None
    created_at: datetime


class ReviewOut(ORM):
    """Đánh giá có ảnh của khách (e8): tự xin sau khi nhận hàng, AI lọc, chị duyệt hiển thị."""

    id: uuid.UUID
    product_id: uuid.UUID
    order_id: uuid.UUID | None
    order_item_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    token: str
    status: ReviewStatus
    display_name: str | None
    rating: int | None
    body: str | None
    photos: list[Any]
    requested_at: datetime | None
    submitted_at: datetime | None
    published_at: datetime | None
    ai_flags: dict[str, Any]
    ai_summary: str | None
    owner_reply: str | None
    approval_item_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class FindRequestOut(ORM):
    """Trang Nhờ tìm (e9): khách gửi nhu cầu, người khác bấm «cùng cần»; đủ người thì mở tìm."""

    id: uuid.UUID
    public_slug: str
    title: str
    description: str | None
    images: list[Any]
    budget_vnd: int | None
    status: FindRequestStatus
    customer_id: uuid.UUID | None
    contact_name: str | None
    contact: str | None
    vote_count: int
    vote_threshold: int
    threshold_reached_at: datetime | None
    brief_id: uuid.UUID | None
    product_id: uuid.UUID | None
    moderation_note: str | None
    created_at: datetime
    updated_at: datetime


class FindRequestVoteOut(ORM):
    id: uuid.UUID
    find_request_id: uuid.UUID
    voter_key: str
    customer_id: uuid.UUID | None
    contact: str | None
    notify: bool
    created_at: datetime


class DropReminderOut(ORM):
    id: uuid.UUID
    drop_id: uuid.UUID
    contact: str
    channel: str
    notified_at: datetime | None
    created_at: datetime


# ---- đầu vào desk ------------------------------------------------------------------------------------------------


class SpecIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=200)
    source: str | None = None


class FaqIn(BaseModel):
    q: str = Field(min_length=1, max_length=200)
    a: str = Field(min_length=1, max_length=1000)
    source: str | None = None


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=160)
    subtitle: str | None = Field(default=None, max_length=300)
    short_description: str | None = None
    description: str | None = None
    specs: list[SpecIn] | None = None
    faq: list[FaqIn] | None = None
    price_vnd: int | None = Field(default=None, ge=0)
    compare_at_price_vnd: int | None = Field(default=None, ge=0)
    category_id: uuid.UUID | None = None
    sale_mode: SaleMode | None = None
    reason_selected: str | None = None
    not_satisfied: str | None = None
    trial_days: int | None = Field(default=None, ge=0, le=3650)
    weight_grams: int | None = Field(default=None, ge=0)
    origin_country: str | None = Field(default=None, max_length=2)
    brand: str | None = Field(default=None, max_length=120)
    gtin: str | None = Field(default=None, max_length=20)
    seo_title: str | None = Field(default=None, max_length=200)
    seo_description: str | None = Field(default=None, max_length=400)
    feed_enabled: bool | None = None
    is_consumable: bool | None = None
    reorder_days: int | None = Field(default=None, ge=1)


class FromCandidateIn(BaseModel):
    candidate_id: uuid.UUID


class RewriteIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class ImageOrderIn(BaseModel):
    ids: list[uuid.UUID]


class DropItemIn(BaseModel):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    price_vnd: int | None = Field(default=None, ge=0)
    slots_total: int | None = Field(default=None, ge=1)
    max_per_order: int | None = Field(default=None, ge=1)
    min_total_to_order: int | None = Field(default=None, ge=1)


class DropIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    expected_arrival_date: date | None = None
    deposit_pct: int | None = Field(default=None, ge=0, le=100)
    items: list[DropItemIn] = Field(default_factory=list)


class DropPatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    expected_arrival_date: date | None = None
    deposit_pct: int | None = Field(default=None, ge=0, le=100)
    items: list[DropItemIn] | None = None


class ArrivedIn(BaseModel):
    arrived_on: date


class ReviewReplyIn(BaseModel):
    owner_reply: str | None = Field(default=None, max_length=1000)


class FindStatusIn(BaseModel):
    status: FindRequestStatus
    product_id: uuid.UUID | None = None
    brief_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=1000)


# ---- đầu vào của khách -------------------------------------------------------------------------------------------


class FindRequestIn(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    description: str | None = Field(default=None, max_length=2000)
    budget_vnd: int | None = Field(default=None, ge=0, le=100_000_000)
    contact_name: str | None = Field(default=None, max_length=120)
    contact: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, description="Ô bẫy chống máy gửi: người thật không thấy, để trống")


class VoteIn(BaseModel):
    contact: str | None = Field(default=None, max_length=200)


class ReminderIn(BaseModel):
    contact: str = Field(min_length=6, max_length=200)


# ---- đầu ra công khai --------------------------------------------------------------------------------------------


class ImageSet(BaseModel):
    id: str
    alt: str | None = None
    is_primary: bool = False
    status: str
    src: str | None = None
    src_large: str | None = None
    src_small: str | None = None
    webp: dict[str, str] = Field(default_factory=dict)


class SealOut(BaseModel):
    chosen: int
    total: int | None


class CategoryRef(BaseModel):
    slug: str
    name: str


class DropRef(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    title: str
    closes_at: datetime | None
    expected_arrival_date: date | None
    price_vnd: int
    slots_total: int | None
    slots_left: int | None
    max_per_order: int | None


class ProductCard(BaseModel):
    id: str
    slug: str
    name: str
    subtitle: str | None
    price_vnd: int
    list_price_vnd: int
    compare_at_price_vnd: int | None
    image: ImageSet | None
    trial_days: int | None
    origin: str | None
    proof: str | None
    category: CategoryRef | None
    rating_avg: float | None
    review_count: int
    drop: DropRef | None
    stock: int
    available: bool


class Chip(BaseModel):
    slug: str
    name: str
    count: int


class ShelfOut(BaseModel):
    total: int
    chips: list[Chip]
    items: list[ProductCard]
    query: str | None
    category: str | None


class ReviewPhoto(BaseModel):
    src: str | None
    thumb: str | None


class PublicReview(BaseModel):
    id: str
    display_name: str
    rating: int | None
    body: str | None
    photos: list[ReviewPhoto]
    published_at: datetime | None
    owner_reply: str | None


class Funnel(BaseModel):
    viewed: int | None = None
    compared: int | None = None
    tried: int | None = None
    selected: int | None = None


class ProductDetail(ProductCard):
    short_description: str | None
    description: str | None
    specs: list[dict[str, Any]]
    faq: list[dict[str, Any]]
    reason_selected: list[str]
    not_satisfied: str | None
    images: list[ImageSet]
    weight_grams: int | None
    brand: str | None
    gtin: str | None
    shipping_notes: list[Any]
    sale_mode: str
    seo_title: str | None
    seo_description: str | None
    published_at: datetime | None
    updated_at: datetime
    ai_generated: bool
    reviews: list[PublicReview]
    url: str
    picker_name: str | None = None


class Alternative(BaseModel):
    label: str
    origin: str | None = None
    price_vnd: int | None = None
    summary: str | None = None
    reason: str | None = None
    tags: list[str] = Field(default_factory=list)
    stage: str = "compared"


class RejectGroup(BaseModel):
    key: str
    label: str
    count: int


class DossierProduct(BaseModel):
    slug: str
    name: str
    price_vnd: int
    origin: str | None
    summary: str
    image: ImageSet | None
    seal: SealOut
    trial_days: int | None
    reason_selected: list[str]
    not_satisfied: str | None


class DossierOut(BaseModel):
    product: DossierProduct
    funnel: Funnel
    alternatives: list[Alternative]
    reject_groups: list[RejectGroup]
    screened_out: int
    reviews_read: int
    review_languages: list[str]
    picker_name: str | None


class DropSummary(BaseModel):
    id: str
    slug: str
    code: str
    label: str
    title: str
    description: str | None
    status: str
    opens_at: datetime | None
    closes_at: datetime | None
    expected_arrival_date: date | None
    actual_arrival_date: date | None
    item_count: int
    slots_total: int | None
    slots_reserved: int
    cover: ImageSet | None
    product_names: list[str]
    order_count: int = 0
    rating_avg: float | None = None
    review_count: int = 0


class DropItemCard(ProductCard):
    slots_total: int | None
    slots_left: int | None
    max_per_order: int | None


class DropDetail(DropSummary):
    deposit_pct: int | None
    items: list[DropItemCard]


class DropsOverview(BaseModel):
    open: list[DropSummary]
    upcoming: list[DropSummary]
    arrived: list[DropSummary]
    closed: list[DropSummary]


class AboutOut(BaseModel):
    store_name: str
    tagline: str
    picker_name: str
    intro: str
    not_selling: str
    not_selling_rules: list[str]
    ai_help: str
    how_we_choose: list[str]


class PublicStatus(BaseModel):
    key: str
    label: str


class FindRequestPublic(BaseModel):
    slug: str
    title: str
    description: str | None
    budget_vnd: int | None
    vote_count: int
    vote_threshold: int
    status: PublicStatus
    voted: bool = False
    product_slug: str | None = None
    created_at: datetime


class FindRequestsPage(BaseModel):
    items: list[FindRequestPublic]
    total: int
    threshold: int


class FindCreated(BaseModel):
    request: FindRequestPublic
    duplicate: bool
    visible: bool


class VoteOut(BaseModel):
    request: FindRequestPublic
    added: bool


class ReminderOut(BaseModel):
    added: bool


class ReviewInvite(BaseModel):
    status: ReviewStatus
    product_name: str
    product_slug: str
    product_image: ImageSet | None
    display_name: str | None
    rating: int | None
    body: str | None


class SitemapEntry(BaseModel):
    path: str
    lastmod: datetime | None
    priority: float


# ---- đầu ra desk -------------------------------------------------------------------------------------------------


class VoiceIssue(BaseModel):
    """Chỗ trên trang còn gọi người bán là «chị» (khách đọc): đăng sẽ bị chặn tới khi sửa."""

    path: str = Field(description="name | description | faq.0.q | specs.1.value ...")
    field: str
    quote: str
    suggestion: str


class DeskProduct(ProductOut):
    images: list[ImageSet] = Field(default_factory=list)
    candidate_title: str | None = None
    voice_issues: list[VoiceIssue] = Field(default_factory=list)


class DeskProductRow(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: ProductStatus
    price_vnd: int
    selected_count: int
    considered_count: int | None
    image: ImageSet | None
    approval_item_id: uuid.UUID | None
    ai_generated: bool
    review_count: int
    rating_avg: float | None
    updated_at: datetime


class SelectableCandidate(BaseModel):
    id: uuid.UUID
    title_vi: str
    stage_changed_at: datetime | None


class DeskDrop(DropOut):
    label: str
    items: list[DropItemOut]
    reminder_count: int = 0
    product_names: dict[str, str] = Field(default_factory=dict)


class DeskReview(ReviewOut):
    product_name: str | None = None
    photo_urls: list[str | None] = Field(default_factory=list)


class DeskFindRequest(FindRequestOut):
    public_status: PublicStatus
