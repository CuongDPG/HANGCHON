"""Cấu hình AI hiệu lực cho mỗi lần gọi: **Cài đặt (CSDL) > biến môi trường > mặc định**.

- Provider: dòng `ai_provider_configs.is_active` nếu chị đã lưu, không thì `AI_PROVIDER`.
- Với provider đó, từng trường (khoá, base URL, model smart/fast, effort smart/fast): giá trị trong dòng của provider
  nếu có, không thì biến môi trường (`<PROVIDER>_API_KEY`, `AI_MODEL_*`, `AI_EFFORT_*`), không thì mặc định.
- Đọc lại tối đa mỗi `CACHE_SECONDS` giây (API và worker arq là hai tiến trình: lưu ở Cài đặt thì tiến trình đang lưu
  xoá cache ngay, tiến trình kia thấy sau ≤ CACHE_SECONDS).
- Khoá đã giải mã chỉ nằm trong bộ nhớ (`Connection.api_key`, không có trong repr), không ghi log / ai_runs / audit.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import Connection, provider_classes
from app.ai.types import Tier
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.errors import AppError
from app.core.secrets import decrypt, encrypt, mask
from app.core.timeutil import now_utc

CACHE_SECONDS = 5.0
EFFORTS = ("low", "medium", "high", "max")

Source = Literal["settings", "env"]  # env = biến môi trường hoặc mặc định trong code


@dataclass(frozen=True)
class TierConfig:
    model: str
    effort: str | None


@dataclass(frozen=True)
class AIConfig:
    """Cấu hình đã hợp nhất cho provider đang dùng (hoặc cấu hình nhập tay khi «Kiểm tra kết nối»)."""

    provider: str
    source: Source  # nguồn của lựa chọn provider
    connection: Connection
    smart: TierConfig
    fast: TierConfig
    key_source: Source | None = None
    error: AppError | None = field(default=None, repr=False)  # vd không giải mã được khoá → báo khi gọi

    def tier(self, tier: Tier) -> TierConfig:
        return self.smart if tier == "smart" else self.fast


_cache: tuple[float, AIConfig] | None = None


def invalidate() -> None:
    global _cache
    _cache = None


def env_key(provider: str) -> str | None:
    cls = provider_classes().get(provider)
    return getattr(settings, cls.key_env, None) if cls and cls.key_env else None


def env_base_url(provider: str) -> str | None:
    cls = provider_classes().get(provider)
    return getattr(settings, cls.base_url_env, None) if cls and cls.base_url_env else None


def _row_dict(row: Any) -> dict[str, Any]:
    return {c: getattr(row, c) for c in ("model_smart", "model_fast", "effort_smart", "effort_fast", "base_url")}


def build_config(
    provider: str,
    *,
    source: Source,
    row: Any = None,
    api_key: str | None = None,
    overrides: dict[str, Any] | None = None,
    resolve_key: bool = True,
) -> AIConfig:
    """Hợp nhất một provider: `overrides` (form đang nhập) > dòng CSDL > biến môi trường > mặc định.
    `api_key` = khoá rõ đã có (nhập tay hoặc đã giải mã); None thì lấy theo dòng / biến môi trường."""
    vals = {**(_row_dict(row) if row is not None else {}), **{k: v for k, v in (overrides or {}).items() if v}}
    error: AppError | None = None
    key_source: Source | None = None
    if api_key:
        key_source = "settings"
    elif row is not None and row.api_key_encrypted and resolve_key:
        try:
            api_key, key_source = decrypt(row.api_key_encrypted), "settings"
        except AppError as e:
            error = e
    if not api_key and error is None and resolve_key and (k := env_key(provider)):
        api_key, key_source = k, "env"
    return AIConfig(
        provider=provider,
        source=source,
        connection=Connection(api_key=api_key or None, base_url=vals.get("base_url") or env_base_url(provider)),
        smart=TierConfig(
            vals.get("model_smart") or settings.ai_model_smart, vals.get("effort_smart") or settings.ai_effort_smart
        ),
        fast=TierConfig(
            vals.get("model_fast") or settings.ai_model_fast, vals.get("effort_fast") or settings.ai_effort_fast
        ),
        key_source=key_source,
        error=error,
    )


async def load_config(db: AsyncSession | None = None) -> AIConfig:
    """Đọc thẳng CSDL (không cache)."""
    from app.modules.control.models import AIProviderConfig

    async def _read(s: AsyncSession) -> Any:
        return (await s.execute(select(AIProviderConfig).where(AIProviderConfig.is_active))).scalar_one_or_none()

    if db is not None:
        row = await _read(db)
    else:
        async with SessionLocal() as s:
            row = await _read(s)
    if row is not None and row.provider in provider_classes():
        return build_config(row.provider, source="settings", row=row)
    return build_config(settings.ai_provider, source="env")


_forced: str | None = None


def force_provider(name: str | None) -> None:
    """Ép mọi lần gọi dùng một provider bất kể Cài đặt (dữ liệu mẫu luôn chạy AI giả). None = bỏ ép."""
    global _forced
    _forced = name
    invalidate()


async def current_config() -> AIConfig:
    """Cấu hình cho `ai.run` — cache ngắn."""
    global _cache
    if _forced:
        return build_config(_forced, source="env")
    now = time.monotonic()
    if _cache is not None and _cache[0] > now:
        return _cache[1]
    cfg = await load_config()
    _cache = (now + CACHE_SECONDS, cfg)
    return cfg


# ---- ghi (màn Cài đặt + lệnh nhập khoá) --------------------------------------------------------------------------


async def get_row(db: AsyncSession, provider: str) -> Any:
    from app.modules.control.models import AIProviderConfig

    return await db.get(AIProviderConfig, provider)


async def list_rows(db: AsyncSession) -> dict[str, Any]:
    from app.modules.control.models import AIProviderConfig

    return {r.provider: r for r in (await db.execute(select(AIProviderConfig))).scalars()}


async def upsert_row(db: AsyncSession, provider: str, user_id: uuid.UUID | None) -> Any:
    from app.modules.control.models import AIProviderConfig

    row = await get_row(db, provider)
    if row is None:
        row = AIProviderConfig(provider=provider, is_active=False)
        db.add(row)
    row.updated_at = now_utc()
    row.updated_by_id = user_id
    return row


def set_key(row: Any, api_key: str | None, user_id: uuid.UUID | None) -> None:
    """Lưu khoá mới (mã hoá) hoặc xoá khoá (None). Không bao giờ giữ khoá rõ trên dòng."""
    row.api_key_encrypted = encrypt(api_key) if api_key else None
    row.api_key_hint = mask(api_key)
    row.key_updated_at = now_utc()
    row.key_updated_by_id = user_id


async def activate(db: AsyncSession, provider: str) -> None:
    from app.modules.control.models import AIProviderConfig

    await db.execute(update(AIProviderConfig).where(AIProviderConfig.provider != provider).values(is_active=False))
    await db.flush()
    row = await get_row(db, provider)
    row.is_active = True
    await db.flush()
