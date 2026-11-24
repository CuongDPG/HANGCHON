"""Giới hạn tần suất phía mình cho các driver đăng bài (đặt dưới hạn mức của nền tảng để không bị khoá).

Bộ đếm cửa sổ trượt trong bộ nhớ tiến trình (worker đăng bài chạy một tiến trình). Vượt hạn → IntegrationError
`rate_limited`; nơi gọi (job đăng bài) tự hẹn giờ thử lại."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from app.integrations.base import IntegrationError


class RateLimited(IntegrationError):
    status_code = 429
    code = "rate_limited"
    message = "Đã chạm giới hạn đăng bài của kênh, hệ thống sẽ thử lại sau."


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, *, limit: int, per_seconds: float, label: str) -> None:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] >= per_seconds:
            q.popleft()
        if len(q) >= limit:
            wait = int(per_seconds - (now - q[0])) + 1
            raise RateLimited(f"{label}: đã dùng hết {limit} lượt trong {_span(per_seconds)}, thử lại sau {wait} giây.")
        q.append(now)


def _span(seconds: float) -> str:
    if seconds >= 3600:
        return f"{int(seconds // 3600)} giờ"
    if seconds >= 60:
        return f"{int(seconds // 60)} phút"
    return f"{int(seconds)} giây"


limiter = RateLimiter()
