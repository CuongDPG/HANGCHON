"""Tạo dữ liệu thử cho test bàn chọn / nguồn cung (ví dụ, không phải dữ liệu thật)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from typing import Any

from app.core import events
from app.core.db import SessionLocal
from app.core.enums import SourcePlatform
from app.core.timeutil import now_utc
from app.modules.sourcing.models import Candidate, CandidateStage, SourcingBrief


async def make_brief(title: str = "Giá phơi gọn cho ban công") -> SourcingBrief:
    async with SessionLocal() as s:
        b = SourcingBrief(title=title, raw_text=title)
        s.add(b)
        await s.commit()
        return b


async def make_candidate(
    title: str = "Giá phơi chữ X",
    *,
    stage: CandidateStage = CandidateStage.CANDIDATE,
    days_in_stage: float = 0,
    brief_id: uuid.UUID | None = None,
    **kw: Any,
) -> Candidate:
    async with SessionLocal() as s:
        c = Candidate(
            title_vi=title,
            title_original=kw.pop("title_original", "X型晾衣架"),
            source_platform=kw.pop("source_platform", SourcePlatform.ALIBABA_1688),
            source_external_id=uuid.uuid4().hex[:12],
            source_url=kw.pop("source_url", "https://example.com/item/1"),
            price_amount=kw.pop("price_amount", Decimal("31")),
            price_currency=kw.pop("price_currency", "CNY"),
            weight_grams=kw.pop("weight_grams", 2100),
            stage=stage,
            stage_changed_at=now_utc() - timedelta(days=days_in_stage) if stage != CandidateStage.CANDIDATE else None,
            brief_id=brief_id,
            **kw,
        )
        s.add(c)
        await s.commit()
        return c


@contextmanager
def capture(*names: str) -> Iterator[list[tuple[str, dict]]]:
    """Ghi lại sự kiện được phát trong khối `with`."""
    seen: list[tuple[str, dict]] = []
    fns = []
    for n in names:

        async def fn(db, payload, _n=n):
            seen.append((_n, payload))

        events.on(n)(fn)
        fns.append((n, fn))
    try:
        yield seen
    finally:
        for n, fn in fns:
            events._handlers[n].remove(fn)
