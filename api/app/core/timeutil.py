"""Thời gian: lưu UTC, hiển thị và tính ngày/tháng theo giờ Việt Nam."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(VN_TZ)


def local_today() -> date:
    return now_utc().astimezone(VN_TZ).date()


def local_day_bounds_utc(day: date | None = None) -> tuple[datetime, datetime]:
    """[đầu ngày, đầu ngày hôm sau) theo giờ VN, trả về UTC."""
    day = day or local_today()
    start = datetime.combine(day, time.min, tzinfo=VN_TZ)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def month_key(dt: datetime | None = None) -> str:
    """'YYYY-MM' theo giờ VN."""
    return to_local(dt or now_utc()).strftime("%Y-%m")


def local_month_bounds_utc(key: str | None = None) -> tuple[datetime, datetime]:
    """Khoảng [đầu tháng, đầu tháng sau) theo giờ VN cho khoá 'YYYY-MM'."""
    key = key or month_key()
    year, month = (int(x) for x in key.split("-"))
    start = datetime(year, month, 1, tzinfo=VN_TZ)
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=VN_TZ)
    return start.astimezone(UTC), end.astimezone(UTC)


def week_start(day: date | None = None) -> date:
    """Thứ Hai của tuần chứa `day` (giờ VN)."""
    day = day or local_today()
    return day - timedelta(days=day.weekday())


def format_local(dt: datetime, fmt: str = "%H:%M %d/%m/%Y") -> str:
    return to_local(dt).strftime(fmt)
