"""Quy đổi giá nguồn và ước tính sơ bộ giá vốn về tay.

Đây chỉ là **ước tính sơ bộ** để xếp hạng và hiện trên hồ sơ khi chưa có bảng giá vốn của module supply
(`cost_sheets`). Tỷ giá lấy từ cài đặt `sourcing.fx_rates` (chị sửa được), cước và phí là giả định ghi rõ trong
`assumptions`. Hàm thuần, không ghi CSDL — module assessment dùng lại."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

FX_SETTING_KEY = "sourcing.fx_rates"
DEFAULT_FX: dict[str, int] = {"CNY": 3650, "JPY": 172, "USD": 26000, "VND": 1}

# (cước nội địa bên bán mỗi món, % phí mua hộ, cước về VN mỗi kg) theo tiền tệ nguồn
_ROUTE: dict[str, tuple[int, float, int, str]] = {
    "CNY": (8_000, 0.05, 15_000, "đường bộ gom hàng Trung Quốc"),
    "JPY": (15_000, 0.08, 150_000, "đường bay Nhật"),
    "USD": (20_000, 0.08, 200_000, "đường bay"),
}
DEFAULT_WEIGHT_GRAMS = 500
TAX_LOSS_PCT = 0.10


def fx_rate(currency: str | None, rates: dict[str, Any] | None = None) -> int:
    table = {**DEFAULT_FX, **{k.upper(): int(v) for k, v in (rates or {}).items() if v}}
    return int(table.get((currency or "VND").upper(), 0))


def to_vnd_estimate(
    amount: Decimal | float | int | None, currency: str | None, rates: dict[str, Any] | None = None
) -> int | None:
    if amount is None:
        return None
    rate = fx_rate(currency, rates)
    if not rate:
        return None
    return int(Decimal(str(amount)) * rate)


def _round_k(v: float) -> int:
    return round(v / 1000.0) * 1000


@dataclass
class LandedEstimate:
    total_vnd: int
    lines: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


def estimate_landed(
    price_amount: Decimal | float | int | None,
    currency: str | None,
    *,
    weight_grams: int | None = None,
    rates: dict[str, Any] | None = None,
) -> LandedEstimate | None:
    """Giá gốc → giá vốn về tay cho một cái (ước tính sơ bộ)."""
    unit_vnd = to_vnd_estimate(price_amount, currency, rates)
    if unit_vnd is None:
        return None
    cur = (currency or "VND").upper()
    if cur == "VND":
        return LandedEstimate(total_vnd=unit_vnd, lines=[{"label": "Giá mua", "amount_vnd": unit_vnd}])
    domestic, agent_pct, per_kg, route = _ROUTE.get(cur, _ROUTE["USD"])
    assumptions = [f"Tỷ giá {fx_rate(cur, rates):,} đ/{cur}".replace(",", ".")]
    grams = weight_grams
    if not grams:
        grams = DEFAULT_WEIGHT_GRAMS
        assumptions.append(f"Chưa rõ cân nặng, tạm tính {DEFAULT_WEIGHT_GRAMS} g")
    agent = _round_k(unit_vnd * agent_pct) + domestic
    intl = _round_k(per_kg * grams / 1000)
    tax_loss = _round_k((unit_vnd + agent + intl) * TAX_LOSS_PCT)
    assumptions.append(f"Phí mua hộ {int(agent_pct * 100)}%, cước {route} {per_kg // 1000}k/kg, thuế + hao hụt 10%")
    lines = [
        {"label": f"Giá gốc {Decimal(str(price_amount)).normalize():f} {cur}", "amount_vnd": unit_vnd},
        {"label": "Mua hộ, cước nội địa", "amount_vnd": agent},
        {"label": f"Cước về Việt Nam ({grams / 1000:.1f} kg)".replace(".", ","), "amount_vnd": intl},
        {"label": "Thuế, hao hụt", "amount_vnd": tax_loss},
    ]
    return LandedEstimate(total_vnd=_round_k(unit_vnd + agent + intl + tax_loss), lines=lines, assumptions=assumptions)


def landed_total(
    price_amount: Decimal | float | int | None,
    currency: str | None,
    *,
    weight_grams: int | None = None,
    rates: dict[str, Any] | None = None,
) -> int | None:
    est = estimate_landed(price_amount, currency, weight_grams=weight_grams, rates=rates)
    return est.total_vnd if est else None


def source_price_ceiling(landed_max_vnd: int, currency: str, rates: dict[str, Any] | None = None) -> Decimal | None:
    """Trần giá về tay → trần giá gốc gần đúng ở nguồn (để lọc sớm khi tìm)."""
    rate = fx_rate(currency, rates)
    if not rate:
        return None
    domestic, agent_pct, per_kg, _ = _ROUTE.get(currency.upper(), _ROUTE["USD"])
    base = (landed_max_vnd / (1 + TAX_LOSS_PCT) - domestic - per_kg * DEFAULT_WEIGHT_GRAMS / 1000) / (1 + agent_pct)
    return Decimal(max(base, 0) / rate).quantize(Decimal("0.01"))
