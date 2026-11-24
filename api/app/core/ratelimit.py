"""Giới hạn tần suất dùng chung (ô khách gửi: nhờ tìm, đánh giá, nhắc đợt, trợ lý hỏi đáp).

Cửa sổ trượt trên Redis (sorted set `rl:<khoá>`) để mọi tiến trình API cùng đếm. Khi chạy test, hoặc Redis tạm không
tới được, dùng bộ đếm trong tiến trình (vẫn chặn spam ở mức một tiến trình, không làm hỏng yêu cầu của khách).

    if not await ratelimit.hit(f"find:{ip}", 20, 3600):
        raise RateLimited()
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque
from typing import Any

from app.core.config import settings

log = logging.getLogger("app.ratelimit")

_local: dict[str, deque[float]] = defaultdict(deque)
_client: Any = None
_down_until = 0.0
_force_local = False


def _hit_local(key: str, max_hits: int, window: float) -> bool:
    now = time.monotonic()
    q = _local[key]
    while q and q[0] <= now - window:
        q.popleft()
    if len(q) >= max_hits:
        return False
    q.append(now)
    return True


async def _redis() -> Any:
    global _client
    if _client is None:
        from redis.asyncio import from_url

        _client = from_url(settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)
    return _client


async def hit(key: str, max_hits: int, window_seconds: float) -> bool:
    """Ghi một lượt; trả False nếu đã vượt `max_hits` lượt trong `window_seconds` giây gần nhất."""
    global _down_until
    if settings.is_test or _force_local or time.monotonic() < _down_until:
        return _hit_local(key, max_hits, window_seconds)
    rk = f"rl:{key}"
    now = time.time()
    try:
        r = await _redis()
        async with r.pipeline(transaction=True) as p:
            p.zremrangebyscore(rk, 0, now - window_seconds)
            p.zcard(rk)
            _, count = await p.execute()
        if int(count) >= max_hits:
            return False
        async with r.pipeline(transaction=True) as p:
            p.zadd(rk, {f"{now}:{uuid.uuid4().hex[:6]}": now})
            p.expire(rk, int(window_seconds) + 1)
            await p.execute()
        return True
    except Exception:
        _down_until = time.monotonic() + 30  # thử lại Redis sau 30 giây
        log.warning("Redis không tới được, tạm đếm giới hạn trong tiến trình", exc_info=True)
        return _hit_local(key, max_hits, window_seconds)


def force_local(on: bool) -> None:
    """Đếm trong tiến trình (dựng dữ liệu mẫu: không để lượt thử của máy ảnh hưởng tới Redis dùng chung)."""
    global _force_local
    _force_local = on


def reset() -> None:
    """Chỉ dùng trong test."""
    _local.clear()
