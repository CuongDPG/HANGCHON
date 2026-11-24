"""Sự kiện nghiệp vụ giữa các module (trong tiến trình).

Module không gọi thẳng service của module khác. Module phát sự kiện, module quan tâm thì đăng ký nghe
trong tệp `events.py` của mình (được tự nạp như `actions.py`).

    from app.core import events

    @events.on("candidate.selected")
    async def make_draft_product(db, payload):   # payload là dict, chỉ chứa id và dữ liệu gọn
        ...

    await events.emit("candidate.selected", {"candidate_id": str(c.id)}, db=db)

Người nghe chạy lần lượt trong cùng phiên DB với người phát, mỗi người nghe trong một savepoint riêng:
người nghe lỗi thì chỉ phần việc của nó bị huỷ và được ghi log, việc của người phát vẫn giữ nguyên.
Danh sách sự kiện chuẩn: docs/ARCHITECTURE.md mục «Sự kiện giữa các module».
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("app.events")

Handler = Callable[[AsyncSession, dict[str, Any]], Awaitable[None]]

_handlers: dict[str, list[Handler]] = defaultdict(list)


def on(name: str) -> Callable[[Handler], Handler]:
    """Đăng ký người nghe cho sự kiện `name`."""

    def deco(fn: Handler) -> Handler:
        if fn not in _handlers[name]:
            _handlers[name].append(fn)
        return fn

    return deco


def handlers(name: str) -> list[Handler]:
    return list(_handlers.get(name, []))


async def emit(name: str, payload: dict[str, Any], *, db: AsyncSession) -> int:
    """Phát sự kiện. Trả về số người nghe chạy thành công."""
    ok = 0
    for fn in handlers(name):
        try:
            async with db.begin_nested():
                await fn(db, payload)
            ok += 1
        except Exception:
            log.exception("Người nghe %s.%s lỗi khi xử lý sự kiện %s", fn.__module__, fn.__name__, name)
    return ok


def clear(name: str | None = None) -> None:
    """Chỉ dùng trong test."""
    if name is None:
        _handlers.clear()
    else:
        _handlers.pop(name, None)
