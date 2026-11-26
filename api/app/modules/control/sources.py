"""Cài đặt → Nguồn hàng: mỗi sàn lấy hàng bằng cách nào, khoá dịch vụ lấy hàng, kiểm tra kết nối. Chỉ chị (owner).

Cơ chế lưu và thứ tự Cài đặt > biến môi trường: `app.integrations.source_config`. Mọi thay đổi ghi `audit_log`
(chỉ tên ô đã đổi, không bao giờ ghi giá trị khoá); lời báo lỗi của dịch vụ được lọc khoá trước khi hiện.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.config import load_config
from app.core.enums import SourcePlatform
from app.core.errors import BadRequest, NotFound
from app.core.secrets import redact
from app.core.timeutil import now_utc
from app.integrations import channel_config as cc
from app.integrations import source_config as sc
from app.integrations.base import IntegrationError, IntegrationNotConfigured, get_driver
from app.modules.control.channels import mask4
from app.modules.control.models import User
from app.modules.control.service import audit

log = logging.getLogger("app.sources")

DRIVER_LABELS = {"mock": "Giả lập", "web": "AI tìm trên web", "onebound": "Qua OneBound", "rakuten": "Qua Rakuten API"}


def _account(account: str) -> sc.AccountSpec:
    spec = sc.ACCOUNTS.get(account)
    if spec is None:
        raise NotFound("Không có dịch vụ nguồn hàng này.")
    return spec


def _platform(platform: str) -> SourcePlatform:
    try:
        p = SourcePlatform(platform)
    except ValueError as e:
        raise NotFound("Không có sàn này.") from e
    if p not in sc.PLATFORMS:
        raise NotFound("Không có sàn này.")
    return p


def account_view(account: str) -> dict[str, Any]:
    spec = _account(account)
    raw = sc._snap.raw.get(account) or {}
    fields = []
    for f in spec.fields:
        v = sc.value(account, f.key)
        fields.append(
            {
                "key": f.key,
                "label": f.label,
                "secret": f.secret,
                "required": f.required,
                "oauth": False,
                "hint": f.hint,
                "value": None if f.secret else v,
                "masked": mask4(v) if f.secret else None,
                "is_set": bool(v),
                "source": sc.source(account, f.key),
            }
        )
    used_by = [p.value for p in sc.PLATFORMS if sc.route(p) == spec.driver]
    return {
        "account": account,
        "label": spec.label,
        "driver": spec.driver,
        "platforms": [p.value for p in spec.platforms],
        "used_by": used_by,
        "ready": sc.ready(account),
        "verified": spec.verified,
        "fields": fields,
        "check": raw.get("check"),
        "guide": {
            "needs": list(spec.needs),
            "steps": list(spec.steps),
            "limits": list(spec.limits),
            "cost": list(spec.cost),
            "links": [{"label": link.label, "url": link.url} for link in spec.links],
        },
    }


def platform_view(p: SourcePlatform, *, ai_fake: bool) -> dict[str, Any]:
    spec = sc.PLATFORMS[p]
    driver = sc.route(p)
    acc = sc.account_of_driver(driver)
    if driver == "mock":
        status = "mock"
    elif driver == "web":
        status = "web"
    else:
        status = "connected" if acc and sc.ready(acc.account) else "not_connected"
    return {
        "platform": p.value,
        "label": spec.label,
        "driver": driver,
        "driver_source": "settings" if sc.db_route(p) else "env",
        "status": status,
        "account": acc.account if acc else None,
        "options": [{"driver": d, "label": DRIVER_LABELS.get(d, d)} for d in sc.options(p)],
        "notes": list(spec.notes),
        "warning": (
            "AI đang chạy giả lập (Cài đặt → AI): «AI tìm trên web» trả dữ liệu mẫu cho tới khi nối Claude hoặc OpenRouter."
            if driver == "web" and ai_fake
            else None
        ),
    }


async def overview(db: AsyncSession) -> dict[str, Any]:
    await cc.refresh(db)
    ai_fake = (await load_config(db)).provider == "fake"
    return {
        "platforms": [platform_view(p, ai_fake=ai_fake) for p in sc.PLATFORMS],
        "accounts": [account_view(a) for a in sc.ACCOUNTS],
        "general_driver": sc.general(),
    }


async def set_route(db: AsyncSession, platform: str, driver: str | None, user: User) -> dict[str, Any]:
    """Chọn cách lấy hàng cho một sàn; `None` = bỏ chọn (theo biến môi trường SOURCES_DRIVER)."""
    p = _platform(platform)
    if driver is not None and driver not in sc.options(p):
        raise BadRequest(f"{sc.PLATFORMS[p].label} không lấy được bằng «{driver}».")
    raw = await sc.load_raw(db, sc.ROUTES_KEY)
    routes = dict(raw.get("routes") or {})
    old = routes.get(p.value)
    if old != driver:
        if driver is None:
            routes.pop(p.value, None)
        else:
            routes[p.value] = driver
        await sc.write_raw(db, sc.ROUTES_KEY, {"routes": routes}, user.id)
        await audit(
            db,
            "control.source_route_saved",
            user=user,
            entity_type="source_route",
            entity_id=p.value,
            summary=f"Nguồn {sc.PLATFORMS[p].label}: {DRIVER_LABELS.get(driver or '', 'theo cấu hình máy chủ')}",
            data={"from": old, "to": driver},
        )
        await db.commit()
    return await overview(db)


async def save_account(
    db: AsyncSession, account: str, *, values: dict[str, str], clear: list[str], user: User
) -> dict[str, Any]:
    spec = _account(account)
    raw = await sc.load_raw(db, account)
    try:
        changed = cc.apply_changes(raw, spec, values=values, clear=clear)  # type: ignore[arg-type]
    except KeyError as e:
        raise BadRequest(f"{spec.label} không có ô «{e.args[0]}».") from e
    if changed:
        raw["check"] = None  # khoá đổi thì kết quả kiểm tra cũ không còn đúng
        await sc.write_raw(db, account, raw, user.id)
        await audit(
            db,
            "control.source_account_saved",
            user=user,
            entity_type="source_account",
            entity_id=account,
            summary=f"Đổi khoá nguồn hàng {spec.label}",
            data={"changed": [k for k in changed if k not in clear], "cleared": clear},
        )
        await db.commit()
    await cc.refresh(db)
    return account_view(account)


async def _probe(account: str, creds: dict[str, str]) -> str:
    driver_cls = type(get_driver("sources", _account(account).driver))
    return await driver_cls(creds=creds).check()  # type: ignore[call-arg]


async def run_check(db: AsyncSession, account: str, overrides: dict[str, str], user: User) -> dict[str, Any]:
    """Gọi thật một lần rẻ nhất (OneBound: item_get món mẫu; Rakuten: tìm 1 món) bằng khoá đang lưu hoặc đang nhập."""
    spec = _account(account)
    await cc.refresh(db)
    creds = {k: v.strip() for k, v in overrides.items() if v and v.strip() and spec.field(k)}
    secrets_in = [creds.get(f.key) or sc.value(account, f.key) for f in spec.fields if f.secret]
    try:
        ok, message = True, await _probe(account, creds)
    except (IntegrationError, IntegrationNotConfigured) as e:
        ok, message = False, str(getattr(e, "message", e))
    except httpx.HTTPError as e:
        ok, message = False, f"Không kết nối được: {e}"
    message = redact(message, *secrets_in)
    raw = await sc.load_raw(db, account)
    raw["check"] = {"ok": ok, "message": message, "at": now_utc().isoformat()}
    await sc.write_raw(db, account, raw, user.id)
    await audit(
        db,
        "control.source_account_checked",
        user=user,
        entity_type="source_account",
        entity_id=account,
        summary=f"Kiểm tra kết nối {spec.label}: {'được' if ok else 'lỗi'}",
        data={"ok": ok},
    )
    await db.commit()
    await cc.refresh(db)
    return {"ok": ok, "message": message}
