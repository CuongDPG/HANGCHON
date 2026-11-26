"""Cài đặt → Mạng xã hội: xem / lưu tài khoản từng kênh, kiểm tra kết nối, «Kết nối» (OAuth). Chỉ chị (owner).

Cơ chế lưu và thứ tự Cài đặt > biến môi trường: `app.integrations.channel_config`. Gọi nền tảng: `channel_oauth`.
Mọi thay đổi ghi `audit_log` (chỉ tên ô đã đổi, không bao giờ ghi giá trị khoá).
"""

from __future__ import annotations

import hmac
import time
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import Actor
from app.core.errors import BadRequest, NotFound
from app.core.timeutil import now_utc
from app.integrations import channel_config as cc
from app.integrations import channel_oauth
from app.modules.control.models import User
from app.modules.control.service import audit


def _spec(channel: str) -> cc.ChannelSpec:
    spec = cc.SPECS.get(channel)
    if spec is None:
        raise NotFound("Không có kênh này.")
    return spec


def mask4(secret: str | None) -> str | None:
    """Dạng che chỉ giữ 4 ký tự cuối (khoá kênh không có tiền tố nhận dạng như khoá AI)."""
    if not secret:
        return None
    return "••••" + secret[-4:] if len(secret) > 8 else "••••"


def env_mode(channel: str) -> str:
    spec = _spec(channel)
    if spec.kind == "marketplaces":
        return "mock" if settings.marketplaces_driver == "mock" else "real"
    if spec.kind == "social":
        from app.integrations.social import canonical_driver

        mapping = dict(p.split("=", 1) for p in settings.social_channel_drivers.replace(" ", "").split(",") if "=" in p)
        return "mock" if canonical_driver(mapping.get(channel) or settings.social_driver) == "mock" else "real"
    return "mock"


def effective_mode(channel: str) -> str:
    return cc.mode(channel) or env_mode(channel)


def view(channel: str) -> dict[str, Any]:
    spec = _spec(channel)
    raw = cc._snap.raw.get(channel) or {}
    fields = []
    for f in spec.fields:
        v = cc.value(channel, f.key)
        fields.append(
            {
                "key": f.key,
                "label": f.label,
                "secret": f.secret,
                "required": f.required,
                "oauth": f.oauth,
                "hint": f.hint,
                "value": None if f.secret else v,
                "masked": mask4(v) if f.secret else None,
                "is_set": bool(v),
                "source": cc.source(channel, f.key),
            }
        )
    shared = [
        {"channel": ch, "key": key, "label": cc.SPECS[ch].field(key).label, "is_set": bool(cc.value(ch, key))}  # type: ignore[union-attr]
        for ch, key in spec.uses
    ]
    ready = all(x["is_set"] for x in fields if x["required"]) and all(x["is_set"] for x in shared)
    mode = effective_mode(channel)
    if spec.kind == "manual":
        status = "manual"
    elif mode == "real":
        status = "connected" if ready else "not_connected"
    else:
        status = "mock"
    meta = raw.get("meta") or {}
    check = raw.get("check")
    return {
        "channel": channel,
        "label": spec.label,
        "kind": spec.kind,
        "driver": spec.driver,
        "mode": mode,
        "mode_source": "settings" if cc.mode(channel) else "env",
        "status": status,
        "ready": ready,
        "account_name": meta.get("account_name") or (check or {}).get("account_name"),
        "fields": fields,
        "shared": shared,
        "check": check,
        "oauth": {
            "supported": spec.oauth,
            "redirect_uri": channel_oauth.redirect_uri(channel) if spec.oauth else None,
            "connected": bool(cc.value(channel, "access_token")) if spec.oauth else False,
            "expires_at": meta.get("expires_at"),
            "refresh_expires_at": meta.get("refresh_expires_at"),
        },
        "guide": {
            "needs": list(spec.needs),
            "steps": list(spec.steps),
            "limits": list(spec.limits),
            "links": [{"label": link.label, "url": link.url} for link in spec.links],
        },
    }


async def list_views(db: AsyncSession) -> list[dict[str, Any]]:
    await cc.refresh(db)
    return [view(c) for c in cc.SPECS]


async def save(
    db: AsyncSession,
    channel: str,
    *,
    mode: str | None,
    values: dict[str, str],
    clear: list[str],
    user: User,
) -> dict[str, Any]:
    spec = _spec(channel)
    if spec.kind == "manual" and (mode or values or clear):
        raise BadRequest(f"{spec.label} làm tay, không có gì để lưu.")
    for key in values:
        f = spec.field(key)
        if f is None:
            raise BadRequest(f"Kênh {spec.label} không có ô «{key}».")
        if f.oauth:
            raise BadRequest(f"«{f.label}» do nút «Kết nối» điền, chị không nhập tay.")
    raw = await cc.load_raw(db, channel)
    old_mode = raw.get("mode")
    try:
        changed = cc.apply_changes(raw, spec, values=values, clear=clear)
    except KeyError as e:
        raise BadRequest(f"Kênh {spec.label} không có ô «{e.args[0]}».") from e
    if mode is not None:
        raw["mode"] = mode
    if "access_token" in clear:  # ngắt kết nối: bỏ luôn hạn token và tên tài khoản cũ
        raw["meta"] = {}
    if changed:
        raw["check"] = None  # khoá đổi thì kết quả kiểm tra cũ không còn đúng
        if any(k in ("access_token", "page_token") for k in changed):
            raw["meta"] = {**(raw.get("meta") or {}), "token_saved_at": time.time(), "refreshed_at": None}
    if not changed and mode == old_mode:
        await cc.refresh(db)
        return view(channel)
    await cc.write_raw(db, channel, raw, user.id)
    await audit(
        db,
        "control.channel_account_saved",
        user=user,
        entity_type="channel_account",
        entity_id=channel,
        summary=f"Đổi tài khoản kênh {spec.label}"
        + (f": {'chạy thật' if mode == 'real' else 'giả lập'}" if mode is not None and mode != old_mode else ""),
        data={
            "mode": {"from": old_mode, "to": raw.get("mode")},
            "changed": [k for k in changed if k not in clear],
            "cleared": clear,
        },
    )
    await db.commit()
    await cc.refresh(db)
    return view(channel)


async def run_check(db: AsyncSession, channel: str, overrides: dict[str, str], user: User) -> dict[str, Any]:
    spec = _spec(channel)
    await cc.refresh(db)
    res = await channel_oauth.check(channel, overrides)
    raw = await cc.load_raw(db, channel)
    raw["check"] = {"ok": res.ok, "message": res.message, "account_name": res.account_name, "at": now_utc().isoformat()}
    if res.ok and res.account_name:
        raw["meta"] = {**(raw.get("meta") or {}), "account_name": res.account_name}
    await cc.write_raw(db, channel, raw, user.id)
    await audit(
        db,
        "control.channel_account_checked",
        user=user,
        entity_type="channel_account",
        entity_id=channel,
        summary=f"Kiểm tra kết nối {spec.label}: {'được' if res.ok else 'lỗi'}",
        data={"ok": res.ok},
    )
    await db.commit()
    await cc.refresh(db)
    return {"ok": res.ok, "message": res.message, "account_name": res.account_name}


async def start_connect(db: AsyncSession, channel: str, user: User) -> dict[str, str]:
    spec = _spec(channel)
    if not spec.oauth:
        raise BadRequest(f"{spec.label} không cần «Kết nối»: chị dán khoá vào thẻ.")
    await cc.refresh(db)
    state = channel_oauth.new_state()
    try:
        url = channel_oauth.authorize_url(channel, state)
    except Exception as e:  # thiếu khoá ứng dụng
        raise BadRequest(str(getattr(e, "message", e))) from e
    raw = await cc.load_raw(db, channel)
    raw["oauth"] = {"state": state, "at": time.time(), "by": str(user.id)}
    await cc.write_raw(db, channel, raw, user.id)
    await db.commit()
    return {"url": url, "redirect_uri": channel_oauth.redirect_uri(channel)}


def settings_url(**q: str) -> str:
    return f"{settings.web_base_url.rstrip('/')}/desk/cai-dat/mang-xa-hoi?{urlencode(q)}"


async def finish_connect(db: AsyncSession, channel: str, params: dict[str, str]) -> str:
    """Nền tảng chuyển chị về đây kèm mã cấp quyền. Trả URL trang Cài đặt để chuyển tiếp (kèm kết quả)."""
    spec = cc.SPECS.get(channel)
    if spec is None or not spec.oauth:
        return settings_url(kenh=channel, ket_qua="loi", loi="Không có kênh này.")
    raw = await cc.load_raw(db, channel)
    pending = raw.get("oauth") or {}
    state = params.get("state") or ""
    if (
        not pending.get("state")
        or not hmac.compare_digest(str(pending["state"]), state)
        or time.time() - float(pending.get("at") or 0) > channel_oauth.STATE_TTL
    ):
        return settings_url(
            kenh=channel, ket_qua="loi", loi="Phiên kết nối đã hết hạn hoặc không khớp, chị bấm «Kết nối» lại."
        )
    raw["oauth"] = None  # dùng một lần
    await cc.write_raw(db, channel, raw)
    await db.commit()
    await cc.refresh(db)
    try:
        name = await channel_oauth.exchange(channel, params)
    except Exception as e:
        msg = str(getattr(e, "message", e))[:300]
        await audit(
            db, "control.channel_account_connected", actor=Actor.SYSTEM, entity_type="channel_account",
            entity_id=channel, summary=f"Kết nối {spec.label} không thành", data={"ok": False},
        )  # fmt: skip
        await db.commit()
        return settings_url(kenh=channel, ket_qua="loi", loi=msg)
    raw = await cc.load_raw(db, channel)
    raw["check"] = {"ok": True, "message": "Đã kết nối.", "account_name": name, "at": now_utc().isoformat()}
    if name:
        raw["meta"] = {**(raw.get("meta") or {}), "account_name": name}
    await cc.write_raw(db, channel, raw)
    await audit(
        db, "control.channel_account_connected", actor=Actor.SYSTEM, entity_type="channel_account",
        entity_id=channel, summary=f"Đã kết nối {spec.label}" + (f" ({name})" if name else ""), data={"ok": True},
    )  # fmt: skip
    await db.commit()
    await cc.refresh(db)
    return settings_url(kenh=channel, ket_qua="ok")
