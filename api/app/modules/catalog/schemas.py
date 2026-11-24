"""Schema đọc cơ bản của catalog (sinh từ models.py — một lớp `<Model>Out` cho mỗi bảng).

Module tự thêm schema tạo/sửa và schema công khai (store) khi viết router; giữ tên `<Model>Out` cho bản đầy đủ.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

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
    """Trang Nhờ chị tìm (e9): khách gửi nhu cầu, người khác bấm «cùng cần»; đủ người thì mở tìm."""

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
