"""Ước tính chi phí một lần gọi AI theo bảng giá cấu hình được (USD / 1 triệu token) rồi quy ra VND."""

from __future__ import annotations

import math
from decimal import Decimal

from app.ai.types import Usage
from app.core.config import settings


def _price(model: str) -> dict[str, float]:
    pricing = settings.pricing
    if model in pricing:
        return pricing[model]
    # model có hậu tố ngày/phiên bản: khớp theo tiền tố dài nhất
    best = max((k for k in pricing if model.startswith(k)), key=len, default=None)
    return pricing[best] if best else pricing.get(settings.ai_model_smart, {})


def _tokens_usd(model: str, inp: int, out: int, cache_read: int, cache_write: int) -> Decimal:
    p = _price(model)
    total = (
        inp * p.get("input", 0)
        + out * p.get("output", 0)
        + cache_read * p.get("cache_read", 0)
        + cache_write * p.get("cache_write", 0)
    )
    return Decimal(str(total)) / Decimal(1_000_000)


def estimate_cost(model: str, usage: Usage) -> tuple[Decimal, int]:
    """Trả (cost_usd, cost_vnd). VND làm tròn lên tới đồng."""
    if usage.per_model:
        usd = sum((_tokens_usd(m, i, o, cr, cw) for m, i, o, cr, cw in usage.per_model), Decimal(0))
    else:
        usd = _tokens_usd(
            model, usage.input_tokens, usage.output_tokens, usage.cache_read_tokens, usage.cache_write_tokens
        )
    usd += Decimal(str(settings.ai_web_search_usd_per_1k)) * usage.web_search_requests / Decimal(1000)
    vnd = math.ceil(usd * settings.ai_usd_vnd_rate) if usd > 0 else 0
    return usd.quantize(Decimal("0.000001")), int(vnd)
