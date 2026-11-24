"""Giới hạn tần suất cho các ô khách gửi (nhờ tìm, bình chọn, đánh giá, nhắc đợt) — đếm chung trên Redis
(`app.core.ratelimit`), có dự phòng trong tiến trình khi test hoặc Redis tạm mất."""

from __future__ import annotations

from app.core import ratelimit
from app.core.errors import AppError


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Bạn thao tác nhanh quá, đợi một chút rồi thử lại nhé."


async def limit(key: str, max_hits: int, window_seconds: float) -> None:
    if not await ratelimit.hit(f"catalog:{key}", max_hits, window_seconds):
        raise RateLimited()


def reset() -> None:
    """Chỉ dùng trong test."""
    ratelimit.reset()
