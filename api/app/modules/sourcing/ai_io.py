"""Khuôn vào/ra của các tác vụ AI trong module sourcing (dùng cho structured output)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.ai.schema import OptStr

Origin = Literal["cn", "jp", "kr", "other"]


# ---- a1: ra đề bằng lời ------------------------------------------------------------------------------------------


class ParseBriefIn(BaseModel):
    text: str = Field(description="Nguyên văn chị nói hoặc gõ")
    categories: list[str] = Field(default_factory=list, description="Tên các nhóm hàng đang có")
    today: str


class BriefParse(BaseModel):
    title: str = Field(description="Tên đề ngắn, 2–6 từ, vd «Giá phơi gấp gọn»")
    interpretation: str = Field(description="Một hai câu «Em hiểu là chị cần…» để chị kiểm")
    product_type: str = Field(description="Loại hàng, danh từ chung tiếng Việt")
    category: OptStr = Field(default=None, description="Một trong các nhóm hàng đã cho, hoặc chuỗi rỗng")
    materials: list[str] = Field(default_factory=list)
    must: list[str] = Field(default_factory=list, description="Điều bắt buộc")
    must_not: list[str] = Field(default_factory=list, description="Điều không chấp nhận")
    prefer: list[str] = Field(default_factory=list, description="Điều ưu tiên")
    landed_cost_max_vnd: int | None = Field(default=None, description="Trần giá vốn về tay (VND), nếu chị nói")
    price_max_vnd: int | None = Field(default=None, description="Giá bán dự kiến tối đa ở VN (VND), nếu chị nói")
    origins: list[Origin] = Field(default_factory=list, description="Xuất xứ ưu tiên")
    min_rating: float | None = Field(default=None, ge=0, le=5)
    min_reviews: int | None = Field(default=None, ge=0)
    keywords_vi: list[str] = Field(default_factory=list)
    keywords_zh: list[str] = Field(
        default_factory=list, description="Từ khoá tiếng Trung giản thể như người bán 1688/Taobao viết"
    )
    keywords_ja: list[str] = Field(
        default_factory=list, description="Từ khoá tiếng Nhật như người bán Rakuten/Amazon Nhật viết"
    )
    keywords_en: list[str] = Field(default_factory=list)
    unclear: list[str] = Field(default_factory=list, description="Điều chưa rõ, chị nên nói thêm")


# ---- a4: xếp hạng ứng viên ---------------------------------------------------------------------------------------


class RankBrief(BaseModel):
    title: str
    product_type: str
    materials: list[str] = Field(default_factory=list)
    must: list[str] = Field(default_factory=list)
    must_not: list[str] = Field(default_factory=list)
    prefer: list[str] = Field(default_factory=list)
    landed_cost_max_vnd: int | None = None
    price_max_vnd: int | None = Field(default=None, description="Giá bán dự kiến tối đa ở VN")
    min_rating: float | None = None
    min_reviews: int | None = None


class RankItemIn(BaseModel):
    ref: str
    platform: str
    title: str = Field(description="Tên gốc ở nguồn (tiếng Trung/Nhật…)")
    price: str = Field(description="Giá gốc kèm tiền tệ")
    landed_estimate_vnd: int | None = None
    rating: float | None = None
    review_count: int | None = None
    sales_count: int | None = None
    seller_name: str | None = None


class RankIn(BaseModel):
    brief: RankBrief
    items: list[RankItemIn]


class RankItemOut(BaseModel):
    ref: str
    title_vi: str = Field(description="Tên tiếng Việt ngắn, đúng món, không quảng cáo")
    keep: bool = Field(description="Khớp đề và đáng để chị xem")
    score: int = Field(ge=0, le=100, description="Độ khớp đề 0–100")
    reason: str = Field(description="Một câu «Đáng xem vì…» dựa trên dữ liệu đã cho; nếu loại thì nói vì sao")
    same_model_key: str | None = Field(
        default=None, description="Khoá ngắn giống nhau cho các tin rao CÙNG một mẫu ở nhiều shop"
    )


class RankOut(BaseModel):
    items: list[RankItemOut]


# ---- a2: dịch hồ sơ sản phẩm -------------------------------------------------------------------------------------


class TranslateIn(BaseModel):
    platform: str
    language: str
    title: str
    description: str | None = None
    specs: dict[str, str] = Field(default_factory=dict)
    variants: list[dict[str, str]] = Field(default_factory=list)


class SpecVi(BaseModel):
    name: str
    value: str


class TranslateOut(BaseModel):
    title_vi: str
    description_vi: str = Field(description="Tóm tắt mô tả bằng tiếng Việt, giữ số liệu gốc, không thêm công dụng")
    specs_vi: list[SpecVi] = Field(default_factory=list)
    variants_vi: list[str] = Field(default_factory=list)
    product_type: str | None = None


# ---- a3: tìm bằng ảnh --------------------------------------------------------------------------------------------


class DescribeImageIn(BaseModel):
    note: str | None = Field(default=None, description="Lời chị ghi kèm ảnh (nếu có)")
    image_sha: str = Field(description="Mã băm ảnh, chỉ để tham chiếu")


class DescribeImageOut(BaseModel):
    title: str = Field(description="Tên món ngắn, tiếng Việt")
    description_vi: str = Field(description="Mô tả món trong ảnh: hình dáng, chất liệu nhìn thấy, công dụng")
    product_type: str
    materials: list[str] = Field(default_factory=list)
    keywords_vi: list[str] = Field(default_factory=list)
    keywords_zh: list[str] = Field(default_factory=list)
    keywords_ja: list[str] = Field(default_factory=list)
    keywords_en: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1, description="Mức chắc chắn nhận ra đúng món")


# ---- a5: radar xu hướng ------------------------------------------------------------------------------------------


class TrendItemIn(BaseModel):
    ref: str
    platform: str
    title: str
    language: str
    metrics: dict[str, float] = Field(default_factory=dict)
    snippet: str | None = None


class TrendIn(BaseModel):
    items: list[TrendItemIn]
    shop_focus: str = Field(description="Nhóm hàng cửa hàng đang bán")


class TrendItemOut(BaseModel):
    ref: str
    title_vi: str
    keep: bool = Field(description="Hợp với cửa hàng và đáng để chị xem")
    score: int = Field(ge=0, le=100)
    reason: str = Field(description="Vì sao đáng xem, dựa trên số liệu đã cho")


class TrendOut(BaseModel):
    items: list[TrendItemOut]


# ---- a6: nghe khách muốn gì --------------------------------------------------------------------------------------


class ExistingDemand(BaseModel):
    key: str
    title: str


class ExtractDemandIn(BaseModel):
    text: str = Field(description="Lời khách (tin nhắn, bình luận, lời nhờ tìm)")
    source: str
    existing: list[ExistingDemand] = Field(default_factory=list, description="Nhu cầu đã gom, để gộp nếu trùng")


class ExtractDemandOut(BaseModel):
    is_demand: bool = Field(description="Khách có đang muốn tìm/mua một MÓN HÀNG cụ thể không")
    title: str | None = Field(default=None, description="Tên món khách muốn, danh từ chung, không thương hiệu")
    match_key: str | None = Field(default=None, description="key của nhu cầu đã có nếu là cùng một món")
    detail: str | None = Field(default=None, description="Chi tiết khách nêu: cỡ, giá, công dụng")
