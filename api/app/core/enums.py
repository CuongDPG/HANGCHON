"""Enum dùng chung giữa nhiều module và tích hợp. Enum riêng của một module đặt trong `models.py` của module đó."""

from __future__ import annotations

import enum


class StrEnum(enum.StrEnum):
    """Enum giá trị chuỗi; dùng cho mọi enum nghiệp vụ (lưu bằng `enum_col`, giá trị chữ thường)."""


class SourcePlatform(StrEnum):
    """Nơi lấy hàng / nơi có tín hiệu."""

    ALIBABA_1688 = "1688"
    ALIBABA = "alibaba"  # Alibaba.com (bán sỉ quốc tế)
    TAOBAO = "taobao"
    TMALL = "tmall"
    PINDUODUO = "pinduoduo"
    RAKUTEN = "rakuten"
    AMAZON_JP = "amazon_jp"
    AMAZON = "amazon"
    XIAOHONGSHU = "xiaohongshu"  # Tiểu Hồng Thư
    COSME = "cosme"  # @cosme
    TIKTOK_SHOP_VN = "tiktok_shop_vn"
    SHOPEE_VN = "shopee_vn"
    LAZADA_VN = "lazada_vn"
    TIKI = "tiki"
    WEB = "web"  # trang bất kỳ
    OFFLINE = "offline"  # thấy ngoài đời
    OTHER = "other"


class Language(StrEnum):
    VI = "vi"
    ZH = "zh"
    JA = "ja"
    EN = "en"
    KO = "ko"
    OTHER = "other"


class Channel(StrEnum):
    """Kênh giao tiếp / bán hàng với khách."""

    WEB = "web"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    THREADS = "threads"
    TIKTOK = "tiktok"
    ZALO_OA = "zalo_oa"
    ZALO_GROUP = "zalo_group"
    ZALO = "zalo"  # Zalo cá nhân / chung
    TIKTOK_SHOP = "tiktok_shop"
    SHOPEE = "shopee"
    EMAIL = "email"
    SMS = "sms"
    PHONE = "phone"
    MANUAL = "manual"


class ShippingStatus(StrEnum):
    PENDING = "pending"  # chưa tạo vận đơn
    CREATED = "created"  # đã tạo vận đơn, chờ lấy
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    FAILED_DELIVERY = "failed_delivery"
    RETURNING = "returning"
    RETURNED = "returned"
    CANCELLED = "cancelled"


class Carrier(StrEnum):
    GHN = "ghn"
    GHTK = "ghtk"
    VIETTEL_POST = "viettel_post"
    MOCK = "mock"
    SELF = "self"  # tự giao / gặp trực tiếp
    OTHER = "other"


class Actor(StrEnum):
    """Ai làm việc này."""

    OWNER = "owner"
    HELPER = "helper"
    AI = "ai"
    SYSTEM = "system"
    CUSTOMER = "customer"


class ReviewStatus(StrEnum):
    """Trạng thái chung cho thứ AI soạn cần chị duyệt (bản nháp nội dung, trả lời, tin nhắn...)."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
