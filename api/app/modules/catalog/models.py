"""catalog — website (e1–e3, e6, e8–e10): nhóm hàng, sản phẩm + phân loại + ảnh, đợt mở bán, tồn kho nhỏ,
đánh giá của khách, trang Nhờ tìm."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, Index, Integer, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import (
    Base,
    CreatedAt,
    Timestamps,
    UUIDPk,
    count,
    enum_col,
    fk,
    flag,
    json_list,
    json_obj,
    money,
    money_opt,
)
from app.core.enums import StrEnum


class ProductStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"  # AI dựng trang xong, chờ chị duyệt (e1)
    PUBLISHED = "published"
    PAUSED = "paused"  # tạm ẩn
    STOPPED = "stopped"  # chị ngừng bán trên mọi kênh (web, bài đăng, sàn); «Mở bán lại» trả về như trước
    ARCHIVED = "archived"


class SaleMode(StrEnum):
    DROP = "drop"  # chỉ bán theo đợt
    IN_STOCK = "in_stock"  # giữ sẵn
    BOTH = "both"


class ImageKind(StrEnum):
    OWNER_PHOTO = "owner_photo"  # ảnh thật chị chụp (chính)
    SUPPLIER = "supplier"  # ảnh nhà cung cấp chị chọn dùng lại (chép từ hồ sơ ứng viên, link gốc ở `source_url`)
    BUYER = "buyer"  # ảnh khách
    DETAIL = "detail"


class ImageStatus(StrEnum):
    RAW = "raw"
    PROCESSING = "processing"
    PROCESSED = "processed"  # AI cắt, cân sáng, làm sạch nền (e6) — không tạo ảnh giả
    APPROVED = "approved"
    FAILED = "failed"


class DropStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"  # AI soạn đợt, chờ chị (e3)
    SCHEDULED = "scheduled"
    OPEN = "open"  # đang nhận đặt
    CLOSED = "closed"  # hết hạn / hết suất
    SOURCING = "sourcing"  # đã tổng hợp, đặt nguồn (g3)
    ARRIVING = "arriving"  # hàng đang về
    FULFILLING = "fulfilling"  # đang giao cho khách
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MovementReason(StrEnum):
    PURCHASE_RECEIVED = "purchase_received"
    ORDER_RESERVED = "order_reserved"
    ORDER_RELEASED = "order_released"
    ORDER_SHIPPED = "order_shipped"
    RETURN_RESTOCK = "return_restock"
    ADJUSTMENT = "adjustment"
    DAMAGED = "damaged"
    SAMPLE_USE = "sample_use"


class ReviewStatus(StrEnum):
    REQUESTED = "requested"  # đã xin đánh giá, chờ khách
    SUBMITTED = "submitted"  # khách gửi, AI đang lọc
    PENDING_REVIEW = "pending_review"  # chờ chị duyệt hiển thị (e8)
    PUBLISHED = "published"
    REJECTED = "rejected"
    HIDDEN = "hidden"
    EXPIRED = "expired"


class FindRequestStatus(StrEnum):
    PENDING_REVIEW = "pending_review"  # chờ duyệt trước khi hiện công khai
    OPEN = "open"  # đang gom người cùng cần
    THRESHOLD_REACHED = "threshold_reached"  # đủ người → mở tìm
    SEARCHING = "searching"
    FOUND = "found"
    CLOSED = "closed"
    REJECTED = "rejected"


class Category(UUIDPk, Timestamps, Base):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140), unique=True)
    parent_id: Mapped[uuid.UUID | None] = fk("categories")
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = count()
    is_active: Mapped[bool] = flag(True)
    is_consumable: Mapped[bool] = flag(comment="Đồ tiêu hao → nhắc mua lại (h6)")
    default_reorder_days: Mapped[int | None] = mapped_column(Integer)
    default_target_margin_pct: Mapped[int | None] = mapped_column(Integer)


class Product(UUIDPk, Timestamps, Base):
    """Sản phẩm trên website — chỉ sinh ra từ ứng viên `selected`. Mang «hồ sơ chọn» (e2): tỉ lệ chọn, thời gian thử,
    lý do chọn, điều chưa ưng, các món đã loại."""

    __tablename__ = "products"
    __table_args__ = (Index("ix_products_status_published", "status", "published_at"),)

    candidate_id: Mapped[uuid.UUID | None] = fk("candidates", unique=True, index=False)
    category_id: Mapped[uuid.UUID | None] = fk("categories")
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    sku: Mapped[str | None] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    subtitle: Mapped[str | None] = mapped_column(String(300))
    short_description: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, comment="Markdown")
    specs: Mapped[list[Any]] = json_list(comment='[{"label","value"}]')
    faq: Mapped[list[Any]] = json_list(comment='[{"q","a","source"}]')
    status: Mapped[ProductStatus] = mapped_column(enum_col(ProductStatus), default=ProductStatus.DRAFT)
    published_at: Mapped[datetime | None]
    sale_mode: Mapped[SaleMode] = mapped_column(enum_col(SaleMode), default=SaleMode.DROP)
    price_vnd: Mapped[int] = money()
    compare_at_price_vnd: Mapped[int | None] = money_opt()
    landed_cost_vnd: Mapped[int | None] = money_opt(comment="Ảnh chụp giá vốn lúc đặt giá (biên lợi nhuận i5)")
    # hồ sơ chọn (e2)
    selected_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1", comment="Tử số con dấu")
    considered_count: Mapped[int | None] = mapped_column(Integer, comment="Mẫu số: số ứng viên cùng đề")
    trial_days: Mapped[int | None] = mapped_column(Integer)
    reason_selected: Mapped[str | None] = mapped_column(Text)
    not_satisfied: Mapped[str | None] = mapped_column(Text)
    rejected_alternatives: Mapped[list[Any]] = json_list(
        comment='Ảnh chụp các món đã loại: [{"title","reason","image_url"}]'
    )
    dossier: Mapped[dict[str, Any]] = json_obj(
        comment='Ảnh chụp dải số sàng lọc + nhóm lý do loại (e2): {"funnel":{viewed,compared,tried,selected},'
        '"reject_groups":[{key,label,count}],"reviews_read","review_languages","built_at"}'
    )
    # vận chuyển / an toàn
    weight_grams: Mapped[int | None] = mapped_column(Integer)
    dimensions_cm: Mapped[dict[str, Any]] = json_obj()
    origin_country: Mapped[str | None] = mapped_column(String(2))
    brand: Mapped[str | None] = mapped_column(String(120))
    gtin: Mapped[str | None] = mapped_column(String(20))
    shipping_notes: Mapped[list[Any]] = json_list(comment="Pin, chất lỏng, dễ vỡ... (từ b6)")
    is_consumable: Mapped[bool] = flag()
    reorder_days: Mapped[int | None] = mapped_column(Integer, comment="Bao lâu thì hết (h6)")
    # SEO / để AI đọc được (e10)
    seo_title: Mapped[str | None] = mapped_column(String(200))
    seo_description: Mapped[str | None] = mapped_column(String(400))
    feed_enabled: Mapped[bool] = flag(True, comment="Có trong nguồn cấp Google / trợ lý mua sắm")
    # kiểm duyệt
    ai_generated: Mapped[bool] = flag(comment="Có phần nội dung do AI viết (k3)")
    content_approved_at: Mapped[datetime | None]
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    rating_avg: Mapped[float | None] = mapped_column(comment="Trung bình đánh giá đã hiển thị")
    review_count: Mapped[int] = count()

    variants: Mapped[list[ProductVariant]] = relationship(
        back_populates="product", lazy="selectin", cascade="all, delete-orphan", order_by="ProductVariant.position"
    )
    images: Mapped[list[ProductImage]] = relationship(
        back_populates="product", lazy="selectin", cascade="all, delete-orphan", order_by="ProductImage.position"
    )


class ProductVariant(UUIDPk, Timestamps, Base):
    """Phân loại (màu, cỡ). Sản phẩm một loại vẫn có thể không có dòng nào ở đây."""

    __tablename__ = "product_variants"

    product_id: Mapped[uuid.UUID] = fk("products", ondelete="CASCADE", nullable=False)
    name: Mapped[str] = mapped_column(String(120))
    sku: Mapped[str | None] = mapped_column(String(60), unique=True)
    options: Mapped[dict[str, Any]] = json_obj(comment='{"Màu": "Xám"}')
    price_vnd: Mapped[int | None] = money_opt(comment="Null = theo giá sản phẩm")
    position: Mapped[int] = count()
    is_active: Mapped[bool] = flag(True)

    product: Mapped[Product] = relationship(back_populates="variants", lazy="raise")


class ProductImage(UUIDPk, Timestamps, Base):
    """Ảnh sản phẩm (e6): ảnh gốc chị chụp + bản đã xử lý (cắt, cân sáng, làm sạch nền)."""

    __tablename__ = "product_images"

    product_id: Mapped[uuid.UUID] = fk("products", ondelete="CASCADE", nullable=False)
    variant_id: Mapped[uuid.UUID | None] = fk("product_variants")
    kind: Mapped[ImageKind] = mapped_column(enum_col(ImageKind), default=ImageKind.OWNER_PHOTO)
    status: Mapped[ImageStatus] = mapped_column(enum_col(ImageStatus), default=ImageStatus.RAW)
    original_key: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(
        Text, comment="kind=supplier: link ảnh gốc của nhà cung cấp (chỉ desk, không ra website)"
    )
    processed_key: Mapped[str | None] = mapped_column(String(300))
    processing_ops: Mapped[list[Any]] = json_list(comment='[{"op":"crop"|"brightness"|"bg_clean", ...}]')
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    alt: Mapped[str | None] = mapped_column(String(300))
    position: Mapped[int] = count()
    is_primary: Mapped[bool] = flag()
    ai_processed: Mapped[bool] = flag()

    product: Mapped[Product] = relationship(back_populates="images", lazy="raise")


class Drop(UUIDPk, Timestamps, Base):
    """Đợt mở bán (e3): gom đơn có hạn chót, số suất, ngày hàng về dự kiến."""

    __tablename__ = "drops"
    __table_args__ = (Index("ix_drops_status_closes", "status", "closes_at"),)

    code: Mapped[str] = mapped_column(String(30), unique=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DropStatus] = mapped_column(enum_col(DropStatus), default=DropStatus.DRAFT)
    opens_at: Mapped[datetime | None]
    closes_at: Mapped[datetime | None] = mapped_column(comment="Hạn chót đặt")
    expected_arrival_date: Mapped[date | None] = mapped_column(Date)
    actual_arrival_date: Mapped[date | None] = mapped_column(Date)
    deposit_pct: Mapped[int | None] = mapped_column(SmallInteger, comment="Đặt cọc % (null = trả đủ)")
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)
    announced_at: Mapped[datetime | None]
    summary: Mapped[dict[str, Any]] = json_obj(comment="Tổng hợp khi đóng đợt (g3): số lượng theo món")
    ai_generated: Mapped[bool] = flag()

    items: Mapped[list[DropItem]] = relationship(
        back_populates="drop", lazy="selectin", cascade="all, delete-orphan", order_by="DropItem.position"
    )


class DropItem(UUIDPk, Timestamps, Base):
    __tablename__ = "drop_items"
    __table_args__ = (
        UniqueConstraint(
            "drop_id", "product_id", "variant_id", name="uq_drop_items_product", postgresql_nulls_not_distinct=True
        ),
        CheckConstraint("slots_reserved >= 0", name="slots_reserved_nonneg"),
    )

    drop_id: Mapped[uuid.UUID] = fk("drops", ondelete="CASCADE", nullable=False)
    product_id: Mapped[uuid.UUID] = fk("products", ondelete="CASCADE", nullable=False)
    variant_id: Mapped[uuid.UUID | None] = fk("product_variants")
    price_vnd: Mapped[int] = money(comment="Giá trong đợt")
    slots_total: Mapped[int | None] = mapped_column(Integer, comment="Số suất (null = không giới hạn)")
    slots_reserved: Mapped[int] = count(comment="Đã đặt")
    min_total_to_order: Mapped[int | None] = mapped_column(Integer, comment="Đủ số này mới đặt nguồn")
    max_per_order: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int] = count()

    drop: Mapped[Drop] = relationship(back_populates="items", lazy="raise")


class DropReminder(UUIDPk, CreatedAt, Base):
    """«Nhắc mình» ở đợt sắp mở (e3): khách để lại SĐT/Zalo, đợt mở thì báo một lần."""

    __tablename__ = "drop_reminders"
    __table_args__ = (UniqueConstraint("drop_id", "contact_key", name="uq_drop_reminders_contact"),)

    drop_id: Mapped[uuid.UUID] = fk("drops", ondelete="CASCADE", nullable=False)
    contact: Mapped[str] = mapped_column(String(200), comment="SĐT hoặc Zalo khách để lại")
    contact_key: Mapped[str] = mapped_column(String(64), comment="Băm liên hệ đã chuẩn hoá (chống trùng)")
    channel: Mapped[str] = mapped_column(String(20), default="zalo", server_default="zalo")
    notified_at: Mapped[datetime | None]


class InventoryItem(UUIDPk, Timestamps, Base):
    """Tồn kho nhỏ (g8): số lượng các món giữ sẵn, báo khi sắp hết."""

    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "variant_id", name="uq_inventory_items_product", postgresql_nulls_not_distinct=True
        ),
    )

    product_id: Mapped[uuid.UUID] = fk("products", ondelete="CASCADE", nullable=False)
    variant_id: Mapped[uuid.UUID | None] = fk("product_variants")
    on_hand: Mapped[int] = count()
    reserved: Mapped[int] = count()
    low_stock_threshold: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str | None] = mapped_column(String(120))
    unit_cost_vnd: Mapped[int | None] = money_opt(comment="Giá vốn bình quân")
    last_counted_at: Mapped[datetime | None]
    low_stock_alerted_at: Mapped[datetime | None]

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


class InventoryMovement(UUIDPk, CreatedAt, Base):
    __tablename__ = "inventory_movements"

    inventory_item_id: Mapped[uuid.UUID] = fk("inventory_items", ondelete="CASCADE", nullable=False)
    delta_on_hand: Mapped[int] = count()
    delta_reserved: Mapped[int] = count()
    reason: Mapped[MovementReason] = mapped_column(enum_col(MovementReason))
    ref_type: Mapped[str | None] = mapped_column(String(60))
    ref_id: Mapped[uuid.UUID | None]
    note: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = fk("users", index=False)


class Review(UUIDPk, Timestamps, Base):
    """Đánh giá có ảnh của khách (e8): tự xin sau khi nhận hàng, AI lọc, chị duyệt hiển thị."""

    __tablename__ = "reviews"
    __table_args__ = (
        Index("ix_reviews_product_status", "product_id", "status"),
        CheckConstraint("rating IS NULL OR (rating BETWEEN 1 AND 5)", name="rating_range"),
    )

    product_id: Mapped[uuid.UUID] = fk("products", ondelete="CASCADE", nullable=False, index=False)
    order_id: Mapped[uuid.UUID | None] = fk("orders")
    order_item_id: Mapped[uuid.UUID | None] = fk("order_items", unique=True, index=False)
    customer_id: Mapped[uuid.UUID | None] = fk("customers")
    token: Mapped[str] = mapped_column(String(64), unique=True, comment="Mã trong đường link xin đánh giá")
    status: Mapped[ReviewStatus] = mapped_column(enum_col(ReviewStatus), default=ReviewStatus.REQUESTED)
    display_name: Mapped[str | None] = mapped_column(String(120))
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    body: Mapped[str | None] = mapped_column(Text)
    choice_reason: Mapped[str | None] = mapped_column(
        Text, comment="«Vì sao bạn chọn món này?» (≤ 300 chữ, không bắt buộc)"
    )
    reason_public: Mapped[bool] = flag(True, comment="Chị tắt để ẩn riêng lý do chọn mà vẫn hiện đánh giá")
    photos: Mapped[list[Any]] = json_list(comment="storage key public/... sau khi duyệt")
    requested_at: Mapped[datetime | None]
    submitted_at: Mapped[datetime | None]
    published_at: Mapped[datetime | None]
    ai_flags: Mapped[dict[str, Any]] = json_obj(comment="spam, offensive, personal_info, off_topic, suspicious")
    ai_summary: Mapped[str | None] = mapped_column(Text)
    owner_reply: Mapped[str | None] = mapped_column(Text)
    approval_item_id: Mapped[uuid.UUID | None] = fk("approval_items", index=False)


class FindRequest(UUIDPk, Timestamps, Base):
    """Trang Nhờ tìm (e9): khách gửi nhu cầu, người khác bấm «cùng cần»; đủ người thì mở tìm."""

    __tablename__ = "find_requests"

    public_slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    images: Mapped[list[Any]] = json_list()
    budget_vnd: Mapped[int | None] = money_opt()
    status: Mapped[FindRequestStatus] = mapped_column(
        enum_col(FindRequestStatus), default=FindRequestStatus.PENDING_REVIEW, index=True
    )
    customer_id: Mapped[uuid.UUID | None] = fk("customers")
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact: Mapped[str | None] = mapped_column(String(200), comment="SĐT / Zalo / email để báo khi tìm được")
    vote_count: Mapped[int] = count()
    vote_threshold: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
    threshold_reached_at: Mapped[datetime | None]
    brief_id: Mapped[uuid.UUID | None] = fk("sourcing_briefs")
    product_id: Mapped[uuid.UUID | None] = fk("products", comment="Món đã tìm được")
    moderation_note: Mapped[str | None] = mapped_column(Text)
    submitter_key: Mapped[str | None] = mapped_column(String(64), index=True, comment="Băm thiết bị gửi (chống spam)")


class FindRequestVote(UUIDPk, CreatedAt, Base):
    __tablename__ = "find_request_votes"
    __table_args__ = (UniqueConstraint("find_request_id", "voter_key", name="uq_find_request_votes_voter"),)

    find_request_id: Mapped[uuid.UUID] = fk("find_requests", ondelete="CASCADE", nullable=False)
    voter_key: Mapped[str] = mapped_column(String(64), comment="Băm SĐT/cookie để chống bấm trùng")
    customer_id: Mapped[uuid.UUID | None] = fk("customers")
    contact: Mapped[str | None] = mapped_column(String(200))
    notify: Mapped[bool] = flag(True)
