"""Giới hạn tần suất đơn giản trong bộ nhớ tiến trình (chống spam cơ bản cho các ô khách gửi).

Không chia sẻ giữa nhiều tiến trình API — đủ cho một máy chủ nhỏ; muốn chặt hơn thì chuyển sang Redis."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from app.core.errors import AppError


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Bạn thao tác nhanh quá, đợi một chút rồi thử lại nhé."


_hits: dict[str, deque[float]] = defaultdict(deque)


def limit(key: str, max_hits: int, window_seconds: float) -> None:
    now = time.monotonic()
    q = _hits[key]
    while q and q[0] <= now - window_seconds:
        q.popleft()
    if len(q) >= max_hits:
        raise RateLimited()
    q.append(now)


def reset() -> None:
    """Chỉ dùng trong test."""
    _hits.clear()
