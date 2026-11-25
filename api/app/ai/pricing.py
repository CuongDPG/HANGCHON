"""Ước tính chi phí một lần gọi AI theo bảng giá cấu hình được (USD / 1 triệu token) rồi quy ra VND."""

from __future__ import annotations

import logging
import math
from decimal import Decimal

from app.ai.types import Usage
from app.core.config import settings

log = logging.getLogger("app.ai.pricing")
_warned: set[str] = set()


def _price(model: str, smart_model: str | None = None) -> dict[str, float]:
    pricing = settings.pricing
    if model in pricing:
        return pricing[model]
    # model có hậu tố ngày/phiên bản: khớp theo tiền tố dài nhất
    best = max((k for k in pricing if model.startswith(k)), key=len, default=None)
    if best:
        return pricing[best]
    # model lạ: tính theo giá model smart (đang cấu hình, rồi tới AI_MODEL_SMART)
    smart = smart_model if smart_model in pricing else settings.ai_model_smart
    if model not in _warned:
        _warned.add(model)
        log.warning("Model «%s» không có trong bảng giá AI_PRICING: tạm tính theo giá «%s».", model, smart)
    return pricing.get(smart, {})


def _tokens_usd(model: str, inp: int, out: int, cache_read: int, cache_write: int, smart: str | None = None) -> Decimal:
    p = _price(model, smart)
    total = (
        inp * p.get("input", 0)
        + out * p.get("output", 0)
        + cache_read * p.get("cache_read", 0)
        + cache_write * p.get("cache_write", 0)
    )
    return Decimal(str(total)) / Decimal(1_000_000)


def estimate_cost(model: str, usage: Usage, *, smart_model: str | None = None) -> tuple[Decimal, int]:
    """Trả (cost_usd, cost_vnd). VND làm tròn lên tới đồng. Provider tự báo chi phí (`reported_cost_usd`) thì dùng số
    đó; không thì tính theo bảng giá (model lạ → giá của `smart_model`)."""
    if usage.reported_cost_usd is not None:
        usd = Decimal(str(usage.reported_cost_usd))
    elif usage.per_model:
        usd = sum((_tokens_usd(m, i, o, cr, cw, smart_model) for m, i, o, cr, cw in usage.per_model), Decimal(0))
    else:
        usd = _tokens_usd(
            model,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_tokens,
            usage.cache_write_tokens,
            smart_model,
        )
    if usage.reported_cost_usd is None:
        usd += Decimal(str(settings.ai_web_search_usd_per_1k)) * usage.web_search_requests / Decimal(1000)
    vnd = math.ceil(usd * settings.ai_usd_vnd_rate) if usd > 0 else 0
    return usd.quantize(Decimal("0.000001")), int(vnd)
