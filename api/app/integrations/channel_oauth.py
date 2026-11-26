"""Gọi nền tảng cho thẻ kênh ở Cài đặt: «Kiểm tra kết nối», «Kết nối» (OAuth) và tự làm mới token.

Mọi điểm cuối dưới đây đọc từ tài liệu chính thức ngày 26/11/2026 (đường dẫn ở `channel_config.SPECS[...].links` và
docs/channel-accounts.md). ⚠️ CHƯA THỬ VỚI TÀI KHOẢN THẬT — mọi test dùng httpx giả.

- Facebook: `GET graph.facebook.com/{v}/{page-id}?fields=id,name` (mã Trang).
- Instagram: `GET graph.facebook.com/{v}/{ig-user-id}?fields=id,username` (mã Trang của thẻ Facebook).
- Threads: `GET graph.threads.net/v1.0/{threads-user-id}?fields=id,username`; làm mới
  `GET graph.threads.net/refresh_access_token?grant_type=th_refresh_token&access_token=…` (mã ≥ 24 giờ tuổi, còn hạn).
- TikTok: cấp quyền `https://www.tiktok.com/v2/auth/authorize/` (client_key, response_type=code, scope, redirect_uri, state);
  đổi mã / làm mới `POST open.tiktokapis.com/v2/oauth/token/` (form; access 2 giờ, refresh 180 ngày, refresh token đổi
  mới mỗi lần); kiểm tra `GET /v2/user/info/?fields=open_id,display_name` (scope user.info.basic).
- Shopee: link cấp quyền `GET partner.shopeemobile.com/api/v2/shop/auth_partner?partner_id&timestamp&sign&redirect`
  (sign = HMAC-SHA256(partner_key, partner_id + path + timestamp)); chuyển về kèm `code` + `shop_id`; đổi mã
  `POST /api/v2/auth/token/get` `{code, partner_id, shop_id}`; làm mới `POST /api/v2/auth/access_token/get`
  `{refresh_token, partner_id, shop_id}` (access 4 giờ, refresh 30 ngày, dùng một lần); kiểm tra `GET /api/v2/shop/get_shop_info`.
- TikTok Shop: link `https://services.tiktokshop.com/open/authorize?service_id=…&state=…`; đổi mã
  `GET auth.tiktok-shops.com/api/v2/token/get?app_key&app_secret&auth_code&grant_type=authorized_code`; làm mới
  `…/api/v2/token/refresh?…&grant_type=refresh_token` (access 7 ngày); kiểm tra + lấy shop cipher
  `GET open-api.tiktokglobalshop.com/authorization/202309/shops` (ký như driver).
- Zalo OA: KHÔNG đọc lại được tài liệu hôm nay (trang dựng bằng JavaScript). «Kiểm tra» = làm mới token một lần bằng điểm
  cuối đã có trong `app/integrations/_zalo_token.py` (đọc 25/11/2026); chưa lấy tên OA.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets as pysecrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.core.secrets import redact
from app.integrations import channel_config as cc
from app.integrations.base import IntegrationError, IntegrationNotConfigured

log = logging.getLogger("app.channels")

GRAPH = "https://graph.facebook.com"
THREADS = "https://graph.threads.net"
TIKTOK_AUTH = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_API = "https://open.tiktokapis.com/v2"
TIKTOK_SCOPES = "user.info.basic,video.upload,video.list"
SHOPEE = "https://partner.shopeemobile.com"
TTS_AUTH = "https://services.tiktokshop.com/open/authorize"
TTS_TOKEN = "https://auth.tiktok-shops.com/api/v2/token"
TTS_API = "https://open-api.tiktokglobalshop.com"
STATE_TTL = 15 * 60
EARLY_REFRESH = 10 * 60

_transport: httpx.AsyncBaseTransport | None = None  # test gắn transport giả


def set_transport(t: httpx.AsyncBaseTransport | None) -> None:
    global _transport
    _transport = t


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20, transport=_transport)


@dataclass
class CheckResult:
    ok: bool
    message: str
    account_name: str | None = None


def redirect_uri(channel: str) -> str:
    """Địa chỉ nền tảng chuyển chị về sau khi cấp quyền (web chuyển /api/* sang API)."""
    return f"{settings.web_base_url.rstrip('/')}/api/hooks/oauth/{channel}"


def _need(values: dict[str, str | None], *keys: str) -> list[str]:
    missing = [k for k in keys if not values.get(k)]
    if missing:
        spec_labels = []
        for k in missing:
            for s in cc.SPECS.values():
                if (f := s.field(k)) is not None:
                    spec_labels.append(f.label)
                    break
        raise IntegrationNotConfigured("Còn thiếu: " + ", ".join(dict.fromkeys(spec_labels or missing)) + ".")
    return [str(values[k]) for k in keys]


async def _json(r: httpx.Response) -> dict[str, Any]:
    try:
        d = r.json()
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _meta_error(d: dict[str, Any], status: int) -> str:
    e = d.get("error")
    if isinstance(e, dict):
        return str(e.get("message") or status)
    return str(e or status)


# ---- kiểm tra kết nối --------------------------------------------------------------------------------------------


def effective_values(channel: str, overrides: dict[str, str] | None = None) -> dict[str, str | None]:
    spec = cc.SPECS[channel]
    vals: dict[str, str | None] = {f.key: cc.value(channel, f.key) for f in spec.fields}
    for ch, key in spec.uses:
        vals[f"{ch}.{key}"] = cc.value(ch, key)
    for k, v in (overrides or {}).items():
        if v and v.strip():
            vals[k] = v.strip()
    return vals


async def check(channel: str, overrides: dict[str, str] | None = None) -> CheckResult:
    """Gọi điểm cuối đọc rẻ nhất của kênh bằng giá trị đang lưu (hoặc đang nhập). Không ném lỗi: trả kết quả để hiện."""
    vals = effective_values(channel, overrides)
    secret_keys = {f.key for f in cc.SPECS[channel].fields if f.secret} | {
        f"{c}.{k}" for c, k in cc.SPECS[channel].uses
    }
    secrets_in = [v for k, v in vals.items() if v and k in secret_keys]
    try:
        fn = _CHECKS.get(channel)
        if fn is None:
            return CheckResult(False, "Kênh này không có kết nối tự động.")
        res = await fn(vals)
        res.message = redact(res.message, *secrets_in)  # nền tảng hay lặp lại token trong câu báo lỗi
        return res
    except (IntegrationError, IntegrationNotConfigured) as e:
        return CheckResult(False, redact(str(e.message if hasattr(e, "message") else e), *secrets_in))
    except httpx.HTTPError as e:
        return CheckResult(False, redact(f"Không kết nối được: {e}", *secrets_in))


async def _check_facebook(v: dict[str, str | None]) -> CheckResult:
    page_id, token = _need(v, "page_id", "page_token")
    async with _client() as c:
        r = await c.get(
            f"{GRAPH}/{settings.meta_graph_version}/{page_id}", params={"fields": "id,name", "access_token": token}
        )
    d = await _json(r)
    if r.status_code != 200 or "error" in d:
        return CheckResult(False, f"Facebook báo lỗi: {_meta_error(d, r.status_code)}")
    return CheckResult(True, f"Đã nối Trang «{d.get('name')}».", d.get("name"))


async def _check_instagram(v: dict[str, str | None]) -> CheckResult:
    v = {**v, "page_token": v.get("facebook.page_token")}
    if not v.get("page_token"):
        raise IntegrationNotConfigured("Thẻ Trang Facebook chưa có mã Trang — Instagram dùng chung mã đó.")
    ig, token = _need(v, "ig_user_id", "page_token")
    async with _client() as c:
        r = await c.get(
            f"{GRAPH}/{settings.meta_graph_version}/{ig}", params={"fields": "id,username", "access_token": token}
        )
    d = await _json(r)
    if r.status_code != 200 or "error" in d:
        return CheckResult(False, f"Instagram báo lỗi: {_meta_error(d, r.status_code)}")
    name = f"@{d['username']}" if d.get("username") else None
    return CheckResult(True, f"Đã nối Instagram {name or ig}.", name)


async def _check_threads(v: dict[str, str | None]) -> CheckResult:
    uid, token = _need(v, "user_id", "access_token")
    async with _client() as c:
        r = await c.get(f"{THREADS}/v1.0/{uid}", params={"fields": "id,username", "access_token": token})
    d = await _json(r)
    if r.status_code != 200 or "error" in d:
        return CheckResult(False, f"Threads báo lỗi: {_meta_error(d, r.status_code)}")
    name = f"@{d['username']}" if d.get("username") else None
    return CheckResult(True, f"Đã nối Threads {name or uid}.", name)


async def _check_tiktok(v: dict[str, str | None]) -> CheckResult:
    token = await tiktok_access_token()
    async with _client() as c:
        r = await c.get(
            f"{TIKTOK_API}/user/info/",
            params={"fields": "open_id,display_name"},
            headers={"Authorization": f"Bearer {token}"},
        )
    d = await _json(r)
    err = d.get("error") or {}
    if r.status_code != 200 or err.get("code") not in (None, "ok"):
        return CheckResult(False, f"TikTok báo lỗi: {err.get('message') or err.get('code') or r.status_code}")
    name = ((d.get("data") or {}).get("user") or {}).get("display_name")
    return CheckResult(True, f"Đã nối TikTok {name or ''}".strip() + ".", name)


async def _check_zalo(v: dict[str, str | None]) -> CheckResult:
    from app.integrations._zalo_token import ZaloTokenStore

    store = ZaloTokenStore(transport=_transport)
    if not store.can_refresh():
        _need(v, "app_id", "app_secret", "refresh_token")
    await store.refresh(stale=str(v.get("access_token") or ""), force=True)
    return CheckResult(
        True,
        "Zalo đã cấp access token mới bằng refresh token: khoá đúng. (Chưa lấy tên OA — chưa đọc lại tài liệu getoa.)",
        None,
    )


def shopee_sign(partner_key: str, base: str) -> str:
    return hmac.new(partner_key.encode(), base.encode(), hashlib.sha256).hexdigest()


async def _check_shopee(v: dict[str, str | None]) -> CheckResult:
    pid, key, shop = _need(v, "partner_id", "partner_key", "shop_id")
    token = await shopee_access_token()
    path = "/api/v2/shop/get_shop_info"
    ts = int(time.time())
    q = {
        "partner_id": pid,
        "timestamp": ts,
        "access_token": token,
        "shop_id": shop,
        "sign": shopee_sign(key, f"{pid}{path}{ts}{token}{shop}"),
    }
    async with _client() as c:
        r = await c.get(f"{SHOPEE}{path}", params=q)
    d = await _json(r)
    if r.status_code != 200 or d.get("error"):
        return CheckResult(False, f"Shopee báo lỗi: {d.get('message') or d.get('error') or r.status_code}")
    name = d.get("shop_name") or (d.get("response") or {}).get("shop_name")
    return CheckResult(True, f"Đã nối shop «{name}».", name)


async def tts_shops(app_key: str, app_secret: str, token: str) -> list[dict[str, Any]]:
    from app.integrations.marketplaces.tiktok_shop import sign

    path = "/authorization/202309/shops"
    q: dict[str, Any] = {"app_key": app_key, "timestamp": int(time.time())}
    q["sign"] = sign(app_secret, path, q)
    async with _client() as c:
        r = await c.get(
            f"{TTS_API}{path}", params=q, headers={"x-tts-access-token": token, "content-type": "application/json"}
        )
    d = await _json(r)
    if r.status_code != 200 or d.get("code") not in (0, None):
        raise IntegrationError(f"TikTok Shop báo lỗi: {d.get('message') or r.status_code}")
    return list((d.get("data") or {}).get("shops") or [])


async def _check_tiktok_shop(v: dict[str, str | None]) -> CheckResult:
    key, secret = _need(v, "app_key", "app_secret")
    token = await tts_access_token()
    shops = await tts_shops(key, secret, token)
    if not shops:
        return CheckResult(False, "TikTok Shop chưa có cửa hàng nào cấp quyền cho ứng dụng.")
    name = shops[0].get("name")
    if shops[0].get("cipher") and shops[0]["cipher"] != cc.value("tiktok_shop", "shop_cipher"):
        await cc.store_tokens("tiktok_shop", {"shop_cipher": str(shops[0]["cipher"])}, {"account_name": name})
    return CheckResult(True, f"Đã nối cửa hàng «{name}».", name)


_CHECKS = {
    "facebook": _check_facebook,
    "instagram": _check_instagram,
    "threads": _check_threads,
    "tiktok": _check_tiktok,
    "zalo_oa": _check_zalo,
    "shopee": _check_shopee,
    "tiktok_shop": _check_tiktok_shop,
}


# ---- «Kết nối»: link cấp quyền + nhận mã ---------------------------------------------------------------------------


def new_state() -> str:
    return pysecrets.token_urlsafe(24)


def authorize_url(channel: str, state: str) -> str:
    vals = effective_values(channel)
    if channel == "tiktok":
        (client_key,) = _need(vals, "client_key")
        _need(vals, "client_secret")
        q = {
            "client_key": client_key,
            "response_type": "code",
            "scope": TIKTOK_SCOPES,
            "redirect_uri": redirect_uri(channel),
            "state": state,
        }
        return f"{TIKTOK_AUTH}?{urlencode(q)}"
    if channel == "shopee":
        pid, key = _need(vals, "partner_id", "partner_key")
        path = "/api/v2/shop/auth_partner"
        ts = int(time.time())
        back = f"{redirect_uri(channel)}?{urlencode({'state': state})}"  # link kiểu cũ không có tham số state
        q = {"partner_id": pid, "timestamp": ts, "sign": shopee_sign(key, f"{pid}{path}{ts}"), "redirect": back}
        return f"{SHOPEE}{path}?{urlencode(q)}"
    if channel == "tiktok_shop":
        (service_id,) = _need(vals, "service_id")
        _need(vals, "app_key", "app_secret")
        return f"{TTS_AUTH}?{urlencode({'service_id': service_id, 'state': state})}"
    raise IntegrationNotConfigured("Kênh này không có nút «Kết nối».")


async def exchange(channel: str, params: dict[str, str]) -> str | None:
    """Đổi mã cấp quyền lấy token và lưu. Trả tên tài khoản nếu biết."""
    vals = effective_values(channel)
    code = params.get("code") or ""
    if not code or code == "null":
        raise IntegrationError(params.get("error_description") or params.get("error") or "Chị chưa đồng ý cấp quyền.")
    if channel == "tiktok":
        key, secret = _need(vals, "client_key", "client_secret")
        async with _client() as c:
            r = await c.post(
                f"{TIKTOK_API}/oauth/token/",
                data={
                    "client_key": key,
                    "client_secret": secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri(channel),
                },
            )
        d = await _json(r)
        if not d.get("access_token"):
            raise IntegrationError(
                f"TikTok không cấp token: {d.get('error_description') or d.get('error') or r.status_code}"
            )
        await _save_tiktok(d)
        try:
            res = await _check_tiktok({})
            return res.account_name
        except Exception:  # thiếu scope user.info.basic: vẫn đã nối
            return None
    if channel == "shopee":
        pid, key = _need(vals, "partner_id", "partner_key")
        shop = params.get("shop_id") or ""
        if not shop:
            raise IntegrationError(
                "Shopee không gửi Shop ID (chị cấp quyền bằng tài khoản shop, không phải tài khoản chính)."
            )
        path = "/api/v2/auth/token/get"
        ts = int(time.time())
        async with _client() as c:
            r = await c.post(
                f"{SHOPEE}{path}",
                params={"partner_id": pid, "timestamp": ts, "sign": shopee_sign(key, f"{pid}{path}{ts}")},
                json={"code": code, "partner_id": int(pid), "shop_id": int(shop)},
            )
        d = await _json(r)
        if not d.get("access_token"):
            raise IntegrationError(f"Shopee không cấp token: {d.get('message') or d.get('error') or r.status_code}")
        await cc.store_tokens(
            "shopee",
            {"shop_id": shop, "access_token": d["access_token"], "refresh_token": d.get("refresh_token")},
            {"expires_at": time.time() + int(d.get("expire_in") or 14400), "connected_at": time.time()},
        )
        try:
            return (await _check_shopee(effective_values("shopee"))).account_name
        except Exception:
            return None
    if channel == "tiktok_shop":
        key, secret = _need(vals, "app_key", "app_secret")
        async with _client() as c:
            r = await c.get(
                f"{TTS_TOKEN}/get",
                params={"app_key": key, "app_secret": secret, "auth_code": code, "grant_type": "authorized_code"},
            )
        d = await _json(r)
        data = d.get("data") or {}
        if d.get("code") not in (0, None) or not data.get("access_token"):
            raise IntegrationError(f"TikTok Shop không cấp token: {d.get('message') or r.status_code}")
        await _save_tts(data)
        name = data.get("seller_name")
        try:
            shops = await tts_shops(key, secret, data["access_token"])
            if shops:
                name = shops[0].get("name") or name
                await cc.store_tokens(
                    "tiktok_shop", {"shop_cipher": str(shops[0].get("cipher") or "")}, {"account_name": name}
                )
        except IntegrationError as e:
            log.warning("TikTok Shop: chưa lấy được shop cipher: %s", e)
        return name
    raise IntegrationNotConfigured("Kênh này không có nút «Kết nối».")


async def _save_tiktok(d: dict[str, Any]) -> None:
    now = time.time()
    await cc.store_tokens(
        "tiktok",
        {"access_token": d["access_token"], "refresh_token": d.get("refresh_token"), "open_id": d.get("open_id")},
        {
            "expires_at": now + int(d.get("expires_in") or 7200),
            "refresh_expires_at": now + int(d.get("refresh_expires_in") or 0) if d.get("refresh_expires_in") else None,
            "scope": d.get("scope"),
            "connected_at": now,
        },
    )


async def _save_tts(data: dict[str, Any]) -> None:
    await cc.store_tokens(
        "tiktok_shop",
        {"access_token": data["access_token"], "refresh_token": data.get("refresh_token")},
        {
            "expires_at": data.get("access_token_expire_in"),
            "refresh_expires_at": data.get("refresh_token_expire_in"),
            "account_name": data.get("seller_name"),
            "connected_at": time.time(),
        },
    )


# ---- token tự làm mới ---------------------------------------------------------------------------------------------


async def _locked_refresh(channel: str, still_fresh: Any, do_refresh: Any) -> None:
    """Khoá liên tiến trình (advisory lock Postgres) để API và worker không cùng tiêu một refresh token dùng một lần."""
    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        await s.execute(text("SELECT pg_advisory_lock(hashtext(:k))"), {"k": f"channel_refresh:{channel}"})
        try:
            await cc.refresh(s)  # tiến trình khác có thể vừa làm mới xong
            if still_fresh():
                return
            await do_refresh()
        finally:
            await s.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": f"channel_refresh:{channel}"})
            await s.commit()


def _expiring(channel: str, margin: float = EARLY_REFRESH) -> bool:
    exp = cc.meta(channel).get("expires_at")
    try:
        return bool(exp) and float(exp) - time.time() < margin
    except (TypeError, ValueError):
        return False


async def tiktok_access_token(margin: float = EARLY_REFRESH) -> str:
    tok = cc.value("tiktok", "access_token")
    if tok and not _expiring("tiktok", margin):
        return tok
    if cc.value("tiktok", "refresh_token") and cc.value("tiktok", "client_key") and cc.value("tiktok", "client_secret"):

        async def _do() -> None:
            async with _client() as c:
                r = await c.post(
                    f"{TIKTOK_API}/oauth/token/",
                    data={
                        "client_key": cc.value("tiktok", "client_key"),
                        "client_secret": cc.value("tiktok", "client_secret"),
                        "grant_type": "refresh_token",
                        "refresh_token": cc.value("tiktok", "refresh_token"),
                    },
                )
            d = await _json(r)
            if not d.get("access_token"):
                raise IntegrationNotConfigured(
                    "TikTok không làm mới được token "
                    f"({d.get('error_description') or d.get('error') or r.status_code}): chị bấm «Kết nối TikTok» lại."
                )
            await _save_tiktok(d)

        await _locked_refresh("tiktok", lambda: not _expiring("tiktok", margin), _do)
        return str(cc.value("tiktok", "access_token"))
    if tok:
        return tok
    raise IntegrationNotConfigured("TikTok chưa nối: chị vào Cài đặt → Mạng xã hội, bấm «Kết nối TikTok».")


async def shopee_access_token(margin: float = EARLY_REFRESH) -> str:
    tok = cc.value("shopee", "access_token")
    if tok and not _expiring("shopee", margin):
        return tok
    pid, key, shop, rt = (cc.value("shopee", k) for k in ("partner_id", "partner_key", "shop_id", "refresh_token"))
    if pid and key and shop and rt:

        async def _do() -> None:
            path = "/api/v2/auth/access_token/get"
            ts = int(time.time())
            async with _client() as c:
                r = await c.post(
                    f"{SHOPEE}{path}",
                    params={"partner_id": pid, "timestamp": ts, "sign": shopee_sign(key, f"{pid}{path}{ts}")},
                    json={
                        "refresh_token": cc.value("shopee", "refresh_token"),
                        "partner_id": int(pid),
                        "shop_id": int(shop),
                    },
                )
            d = await _json(r)
            if not d.get("access_token"):
                raise IntegrationNotConfigured(
                    f"Shopee không làm mới được token ({d.get('message') or d.get('error') or r.status_code}): "
                    "chị bấm «Kết nối Shopee» lại."
                )
            await cc.store_tokens(
                "shopee",
                {"access_token": d["access_token"], "refresh_token": d.get("refresh_token")},
                {"expires_at": time.time() + int(d.get("expire_in") or 14400)},
            )

        await _locked_refresh("shopee", lambda: not _expiring("shopee", margin), _do)
        return str(cc.value("shopee", "access_token"))
    if tok:
        return tok
    raise IntegrationNotConfigured("Shopee chưa nối: chị vào Cài đặt → Mạng xã hội, bấm «Kết nối Shopee».")


async def tts_access_token(margin: float = EARLY_REFRESH) -> str:
    tok = cc.value("tiktok_shop", "access_token")
    if tok and not _expiring("tiktok_shop", margin):
        return tok
    key, secret, rt = (cc.value("tiktok_shop", k) for k in ("app_key", "app_secret", "refresh_token"))
    if key and secret and rt:

        async def _do() -> None:
            async with _client() as c:
                r = await c.get(
                    f"{TTS_TOKEN}/refresh",
                    params={
                        "app_key": key,
                        "app_secret": secret,
                        "refresh_token": cc.value("tiktok_shop", "refresh_token"),
                        "grant_type": "refresh_token",
                    },
                )
            d = await _json(r)
            data = d.get("data") or {}
            if d.get("code") not in (0, None) or not data.get("access_token"):
                raise IntegrationNotConfigured(
                    f"TikTok Shop không làm mới được token ({d.get('message') or r.status_code}): chị bấm «Kết nối» lại."
                )
            await _save_tts(data)

        await _locked_refresh("tiktok_shop", lambda: not _expiring("tiktok_shop", margin), _do)
        return str(cc.value("tiktok_shop", "access_token"))
    if tok:
        return tok
    raise IntegrationNotConfigured("TikTok Shop chưa nối: chị vào Cài đặt → Mạng xã hội, bấm «Kết nối TikTok Shop».")


THREADS_REFRESH_AFTER = 7 * 86400


async def refresh_threads_if_old() -> bool:
    """Mã Threads dài hạn (60 ngày) do chị dán: làm mới khi đã cũ hơn 7 ngày. Chỉ làm với mã lưu ở Cài đặt."""
    if cc.source("threads", "access_token") != "settings":
        return False
    m = cc.meta("threads")
    last = m.get("refreshed_at") or m.get("token_saved_at")
    if last and time.time() - float(last) < THREADS_REFRESH_AFTER:
        return False
    if not last:  # mã vừa dán (chưa rõ tuổi): đánh dấu, lần sau mới làm mới (mã phải ≥ 24 giờ tuổi)
        await cc.store_tokens("threads", {}, {"token_saved_at": time.time()})
        return False
    async with _client() as c:
        r = await c.get(
            f"{THREADS}/refresh_access_token",
            params={"grant_type": "th_refresh_token", "access_token": cc.value("threads", "access_token")},
        )
    d = await _json(r)
    if not d.get("access_token"):
        log.warning("Threads không làm mới được mã: %s", _meta_error(d, r.status_code))
        await cc.store_tokens("threads", {}, {"refresh_error": _meta_error(d, r.status_code)})
        return False
    await cc.store_tokens(
        "threads",
        {"access_token": d["access_token"]},
        {
            "refreshed_at": time.time(),
            "expires_at": time.time() + int(d.get("expires_in") or 5184000),
            "refresh_error": None,
        },
    )
    return True


async def refresh_due_tokens() -> dict[str, str]:
    """Việc nền hằng ngày: giữ token còn sống kể cả khi lâu không đăng (refresh token Shopee chỉ sống 30 ngày)."""
    await cc.refresh()
    out: dict[str, str] = {}
    jobs = {
        "tiktok": (tiktok_access_token, "refresh_token"),
        "shopee": (shopee_access_token, "refresh_token"),
        "tiktok_shop": (tts_access_token, "refresh_token"),
    }
    for ch, (fn, key) in jobs.items():
        if cc.source(ch, key) != "settings":
            continue
        try:
            await fn(margin=36 * 3600)  # còn dưới 36 giờ thì làm mới luôn
            out[ch] = "ok"
        except Exception as e:  # ghi lại, việc khác vẫn chạy
            out[ch] = f"lỗi: {e}"
    try:
        out["threads"] = "ok" if await refresh_threads_if_old() else "bỏ qua"
    except Exception as e:
        out["threads"] = f"lỗi: {e}"
    return out
