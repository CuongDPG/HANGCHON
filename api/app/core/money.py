"""Tiền: số nguyên VND. Ngoại tệ lưu amount + currency + fx_rate rồi quy đổi bằng `to_vnd`."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def to_vnd(amount: Decimal | float | int | str, fx_rate: Decimal | float | int | str = 1) -> int:
    """Quy đổi về VND, làm tròn tới đồng (half-up)."""
    value = Decimal(str(amount)) * Decimal(str(fx_rate))
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def round_vnd(value: int | float | Decimal, step: int = 1000) -> int:
    """Làm tròn tới bội số `step` (mặc định nghìn đồng), dùng cho giá bán."""
    d = Decimal(str(value)) / Decimal(step)
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * step


def pct_of(value: int, pct: Decimal | float | int) -> int:
    return to_vnd(Decimal(value) * Decimal(str(pct)) / Decimal(100))


def margin_pct(price_vnd: int, cost_vnd: int) -> float:
    """Biên lợi nhuận gộp theo giá bán (%)."""
    if price_vnd <= 0:
        return 0.0
    return round((price_vnd - cost_vnd) * 100 / price_vnd, 2)


def format_vnd(value: int | None, *, suffix: str = " ₫") -> str:
    """123456 -> '123.456 ₫'."""
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(int(value)):,}".replace(",", ".") + suffix


def format_vnd_short(value: int) -> str:
    """Rút gọn cho giao diện: 1.250.000 -> '1,25tr'; 85.000 -> '85k'."""
    v = abs(value)
    sign = "-" if value < 0 else ""
    if v >= 1_000_000_000:
        return f"{sign}{v / 1_000_000_000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "tỷ"
    if v >= 1_000_000:
        return f"{sign}{v / 1_000_000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "tr"
    if v >= 1_000:
        return f"{sign}{v / 1_000:.1f}".rstrip("0").rstrip(".").replace(".", ",") + "k"
    return f"{sign}{v}"
