"""Cài đặt → «AI và khoá API»: đọc / lưu / kiểm tra cấu hình provider AI (chỉ owner).

Khoá API chỉ đi một chiều vào CSDL (mã hoá); API trả dạng che. Lưu vết ghi ai đổi, lúc nào, đổi trường nào —
không ghi giá trị khoá.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai
from app.ai import config as ai_config
from app.ai.providers import provider_classes
from app.ai.runner import BUDGET_SETTING_KEY, monthly_budget_vnd
from app.core.config import settings
from app.core.errors import BadRequest, NotFound
from app.core.secrets import mask
from app.modules.control import service
from app.modules.control.ai_tasks import PING_TASK, PingIn, PingOut
from app.modules.control.models import AppSetting, User
from app.modules.control.schemas import AIConfigIn

TRACKED = ("base_url", "model_smart", "model_fast", "effort_smart", "effort_fast")
TIER_LABELS = {"smart": "thông minh", "fast": "nhanh"}


def _cls(provider: str) -> Any:
    cls = provider_classes().get(provider)
    if cls is None:
        raise BadRequest(f"Không có nhà cung cấp AI «{provider}».")
    return cls


def _default_models_apply(provider: str) -> bool:
    """Model mặc định (AI_MODEL_*) chỉ có nghĩa cho provider của biến môi trường hoặc provider có danh sách gợi ý
    trùng tên (Anthropic); provider gõ tự do (OpenRouter) phải tự nhập."""
    cls = _cls(provider)
    return provider == settings.ai_provider or bool(cls.model_suggestions)


def _ordered() -> list[str]:
    return sorted(provider_classes(), key=lambda n: (n == "fake", n))


async def get_config(db: AsyncSession) -> dict[str, Any]:
    rows = await ai_config.list_rows(db)
    active = next((r.provider for r in rows.values() if r.is_active and r.provider in provider_classes()), None)
    names = {u.id: u.name for u in (await db.execute(select(User))).scalars()}
    providers = []
    for name in _ordered():
        cls, row = provider_classes()[name], rows.get(name)
        saved_key = bool(row and row.api_key_encrypted)
        env_key = ai_config.env_key(name)
        cfg = ai_config.build_config(name, source="settings", row=row, resolve_key=False)
        defaults = _default_models_apply(name)
        providers.append(
            {
                "name": name,
                "label": cls.label,
                "needs_key": cls.needs_key,
                "supports_web": cls.supports_web,
                "needs_base_url": cls.base_url_env is not None,
                "default_base_url": ai_config.env_base_url(name),
                "model_suggestions": list(cls.model_suggestions),
                "key_placeholder": cls.key_placeholder,
                "saved": row is not None,
                "has_key": saved_key or bool(env_key),
                "key_hint": row.api_key_hint if saved_key else mask(env_key),
                "key_source": "settings" if saved_key else ("env" if env_key else None),
                "key_updated_at": row.key_updated_at if saved_key else None,
                "key_updated_by": names.get(row.key_updated_by_id) if saved_key and row.key_updated_by_id else None,
                "base_url": row.base_url if row else None,
                "model_smart": (row.model_smart if row and row.model_smart else cfg.smart.model if defaults else ""),
                "model_fast": (row.model_fast if row and row.model_fast else cfg.fast.model if defaults else ""),
                "effort_smart": cfg.smart.effort,
                "effort_fast": cfg.fast.effort,
            }
        )
    return {
        "provider": active or settings.ai_provider,
        "source": "settings" if active else "env",
        "providers": providers,
        "efforts": list(ai_config.EFFORTS),
        "monthly_budget_vnd": await monthly_budget_vnd(),
        "budget_source": "settings" if await db.get(AppSetting, BUDGET_SETTING_KEY) else "env",
    }


def _check_models(body: AIConfigIn, row: Any) -> None:
    if body.provider == "fake" or _default_models_apply(body.provider):
        return
    for tier in ("smart", "fast"):
        if not (getattr(body, f"model_{tier}") or (row and getattr(row, f"model_{tier}"))):
            raise BadRequest(f"Nhập tên model cho tầng {TIER_LABELS[tier]}.")


async def save_config(db: AsyncSession, body: AIConfigIn, user: User) -> None:
    cls = _cls(body.provider)
    row = await ai_config.get_row(db, body.provider)
    _check_models(body, row)
    was_active = bool(row and row.is_active)
    row = await ai_config.upsert_row(db, body.provider, user.id)
    changed = [f for f in TRACKED if getattr(row, f) != getattr(body, f)]
    for f in TRACKED:
        setattr(row, f, getattr(body, f) if (f != "base_url" or cls.base_url_env) else None)
    if body.api_key and cls.needs_key:
        ai_config.set_key(row, body.api_key, user.id)
        await service.audit(
            db, "ai.key_changed", user=user, entity_type="ai_provider", entity_id=body.provider,
            summary=f"Đổi khoá API {cls.label}",
        )  # fmt: skip
    await db.flush()
    activated = body.activate and not was_active
    if activated:
        await ai_config.activate(db, body.provider)
    if changed or activated:
        await service.audit(
            db, "ai.config_changed", user=user, entity_type="ai_provider", entity_id=body.provider,
            summary=f"Đổi cấu hình AI: {cls.label}" + (" (chuyển sang dùng)" if activated else ""),
            data={"changed": changed, "activated": activated},
        )  # fmt: skip
    if body.monthly_budget_vnd is not None and body.monthly_budget_vnd != await monthly_budget_vnd():
        await service.set_budget(db, body.monthly_budget_vnd, user)


async def clear_key(db: AsyncSession, provider: str, user: User) -> None:
    cls = _cls(provider)
    row = await ai_config.get_row(db, provider)
    if row is None or not row.api_key_encrypted:
        raise NotFound("Chưa có khoá nào lưu ở Cài đặt cho nhà cung cấp này.")
    ai_config.set_key(row, None, user.id)
    row.updated_by_id = user.id
    await service.audit(
        db, "ai.key_cleared", user=user, entity_type="ai_provider", entity_id=provider,
        summary=f"Xoá khoá API {cls.label}",
    )  # fmt: skip
    await db.flush()


async def test_connection(db: AsyncSession, body: AIConfigIn) -> dict[str, Any]:
    """Gửi một lệnh rất ngắn tới từng tầng bằng cấu hình đang nhập (chưa lưu). Gọi thật — chỉ khi chị bấm.
    Mỗi lượt đi qua `ai.run` nên có dòng ai_runs và tính vào chi phí tháng như lượt gọi thường."""
    _cls(body.provider)
    row = await ai_config.get_row(db, body.provider)
    _check_models(body, row)
    overrides = {f: getattr(body, f) for f in TRACKED}
    cfg = ai_config.build_config(body.provider, source="settings", row=row, api_key=body.api_key, overrides=overrides)
    results = []
    for tier in ("fast", "smart"):
        started = time.perf_counter()
        model = "fake" if body.provider == "fake" else cfg.tier(tier).model
        try:
            res = await ai.run(PING_TASK, PingIn(), PingOut, tier=tier, config=cfg, max_tokens=1024)
        except ai.AIError as e:
            results.append(
                {
                    "tier": tier,
                    "ok": False,
                    "model": model,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "error": e.message,
                    "code": e.code,
                }
            )
            continue
        results.append(
            {
                "tier": tier,
                "ok": True,
                "model": res.model,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "cost_vnd": res.cost_vnd,
            }
        )
    return {"provider": body.provider, "results": results}
