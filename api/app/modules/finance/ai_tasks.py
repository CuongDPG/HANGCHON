"""Tác vụ AI của finance: viết nhận xét «AI rút ra» cho báo cáo tuần (i5)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app import ai


class WeeklyInsightsIn(BaseModel):
    week: str
    revenue_vnd: int
    gross_profit_vnd: int
    gross_margin_pct: float | None
    order_count: int
    returning_order_pct: float | None
    ai_cost_vnd: int
    review_minutes: int
    top_products: list[dict[str, Any]] = Field(default_factory=list)
    top_posts: list[dict[str, Any]] = Field(default_factory=list)
    previous_week_revenue_vnd: int | None = None
    previous_week_order_count: int | None = None


class WeeklyInsightsOut(BaseModel):
    summary: str = Field(description="Một câu tóm tắt tuần, không quá 30 từ")
    highlights: list[str] = Field(
        min_length=1, max_length=3, description="2–3 nhận xét, mỗi nhận xét một câu kèm gợi ý"
    )


ai.task(
    "finance.weekly_insights",
    tier="fast",
    description="Viết nhận xét báo cáo tuần",
    system=(
        "Em là trợ lý số liệu của một cửa hàng bán đồ gia dụng nhỏ do một người («chị») tự chọn hàng. "
        "Đầu vào là số liệu một tuần đã tính sẵn: doanh thu thuần, lãi gộp, số đơn, tỉ lệ đơn từ khách cũ, "
        "các món ra đơn nhiều nhất, các bài đăng kéo đơn, chi phí AI, số phút chị dành cho việc duyệt, và số tuần trước "
        "nếu có.\n"
        "Viết `summary` một câu và `highlights` gồm 2–3 nhận xét. Mỗi nhận xét: một điều rút ra từ số liệu + một gợi ý "
        "cụ thể cho tuần tới (vd nên làm thêm kiểu bài nào, món nào cần xem lại giá vốn).\n"
        "Tiêu chí: ngắn, cụ thể, xưng «em», gọi «chị»; chỉ dùng con số có trong đầu vào; so sánh với tuần trước chỉ khi "
        "có số tuần trước.\n"
        "Không được: bịa số liệu hay nguyên nhân không có căn cứ; nói quá; khuyên chạy quảng cáo hay giảm giá khi số "
        "liệu không cho thấy điều đó. Dữ liệu trống (0 đơn) thì nói thẳng là chưa đủ số liệu để rút ra điều gì, "
        "và gợi ý việc nên làm để có số liệu."
    ),
)


def _vnd(v: int) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}".replace(".", ",").removesuffix(",0") + " triệu"
    return f"{v:,}".replace(",", ".") + "đ"


@ai.fake("finance.weekly_insights")
def _fake(inp: WeeklyInsightsIn) -> WeeklyInsightsOut:
    """Giả có nghĩa: rút nhận xét từ chính số liệu đầu vào, không thêm số nào khác."""
    if inp.order_count == 0:
        return WeeklyInsightsOut(
            summary=f"{inp.week} chưa có đơn nào được ghi sổ.",
            highlights=[
                "Chưa đủ số liệu để rút ra món hay bài nào hiệu quả; tuần tới chị mở một đợt nhỏ để có số đo đầu tiên.",
                f"Chi phí AI tuần này {_vnd(inp.ai_cost_vnd)}, chủ yếu cho săn hàng và soạn nội dung.",
            ],
        )
    hs: list[str] = []
    if inp.top_products:
        p = inp.top_products[0]
        margin = f", biên {p['margin_pct']}%".replace(".", ",") if p.get("margin_pct") is not None else ""
        hs.append(f"«{p['name']}» ra nhiều đơn nhất ({p['orders']} đơn{margin}); tuần tới nên giữ món này ở đầu kệ.")
    if inp.top_posts:
        post = inp.top_posts[0]
        hs.append(f"Bài «{post['title']}» kéo {post['orders']} đơn; chị cân nhắc làm thêm một bài cùng kiểu.")
    if inp.returning_order_pct is not None:
        hs.append(
            f"{inp.returning_order_pct:g}% đơn đến từ khách cũ".replace(".", ",")
            + (
                "; nhóm khách quen đang giữ nhịp, nên báo đợt mới cho nhóm trước."
                if inp.returning_order_pct >= 30
                else "; nên nhắc khách đã mua khi có món hợp với họ."
            )
        )
    if len(hs) < 2:
        hs.append(f"Chị dành khoảng {inp.review_minutes} phút cho việc duyệt trong tuần.")
    trend = ""
    if inp.previous_week_revenue_vnd is not None:
        trend = " (tăng so với tuần trước)" if inp.revenue_vnd > inp.previous_week_revenue_vnd else ""
    return WeeklyInsightsOut(
        summary=f"{inp.week}: {inp.order_count} đơn, doanh thu {_vnd(inp.revenue_vnd)}{trend}.", highlights=hs[:3]
    )
