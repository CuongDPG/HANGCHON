"""Access token Zalo OA: đọc, tự làm mới bằng refresh token, lưu lại để API và worker dùng chung.

Theo tài liệu «Xác thực và uỷ quyền cho ứng dụng» (developers.zalo.me/docs/official-account/bat-dau/
xac-thuc-va-uy-quyen-cho-ung-dung-new, đọc 25/11/2026):
- `POST https://oauth.zaloapp.com/v4/oa/access_token`, `Content-Type: application/x-www-form-urlencoded`,
  header `secret_key: <khoá bí mật của ỨNG DỤNG>`, body `refresh_token`, `app_id`, `grant_type=refresh_token`
  → `{"access_token", "refresh_token", "expires_in": "90000"}` (giây, chuỗi).
- Access token hiệu lực 25 giờ; refresh token hiệu lực 3 tháng và **chỉ dùng một lần** — mỗi lần làm mới trả refresh
  token mới, access token cũ hết hiệu lực ngay. Vì vậy token mới phải được lưu (tệp `ZALO_TOKEN_FILE`, nằm trên volume
  chung của api + worker, NGOÀI thư mục `STORAGE_LOCAL_DIR` để không bị phục vụ qua `/api/files`).
- Lỗi khi làm mới: tài liệu không nêu dạng trả về; ở đây coi mọi phản hồi thiếu `access_token` là lỗi (CHƯA CHẮC dạng
  `{"error": ..., "error_name": ..., "error_description": ...}`).

Thứ tự lấy token: tệp đã lưu → env (`ZALO_OA_ACCESS_TOKEN`, `ZALO_OA_REFRESH_TOKEN`). Nếu người vận hành cấp refresh
token mới vào env (khác «hạt giống» đã ghi trong tệp) thì env thắng. Chưa đặt `ZALO_TOKEN_FILE` thì token làm mới chỉ
nằm trong bộ nhớ tiến trình (đủ cho máy dev, KHÔNG đủ cho prod).

Cài đặt → Mạng xã hội (thẻ Zalo OA) ghi đè biến môi trường (`channel_config.value("zalo_oa", …)`). Khi Zalo OA được cấu
hình ở Cài đặt, token làm mới được lưu luôn vào CSDL (mã hoá) nên driver `social/zalo_oa` (đọc
`channel_config.value("zalo_oa", "access_token")`), API và worker cùng thấy token mới mà không cần `ZALO_TOKEN_FILE`.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.integrations import channel_config as cc
from app.integrations.base import IntegrationNotConfigured

OAUTH_URL = "https://oauth.zaloapp.com/v4/oa/access_token"
EARLY_REFRESH_SECONDS = 600  # làm mới trước khi hết hạn 10 phút


class ZaloTokenStore:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, path: str | None = None) -> None:
        self._transport = transport
        self._path = Path(path) if path else (Path(settings.zalo_token_file) if settings.zalo_token_file else None)
        self._lock = asyncio.Lock()
        self._mem: dict[str, Any] | None = None

    # ---- lưu / đọc ----------------------------------------------------------------------------------------------

    def _env_state(self) -> dict[str, Any]:
        refresh = cc.value("zalo_oa", "refresh_token") or ""
        return {
            "access_token": cc.value("zalo_oa", "access_token") or "",
            "refresh_token": refresh,
            "expires_at": cc.meta("zalo_oa").get("expires_at"),
            "seed": refresh,
        }

    def _load(self) -> dict[str, Any]:
        env = self._env_state()
        saved: dict[str, Any] | None = self._mem
        if self._path and self._path.exists():
            with contextlib.suppress(OSError, ValueError):
                saved = json.loads(self._path.read_text("utf-8"))
        if not saved or (env["seed"] and saved.get("seed") != env["seed"]):
            return env  # chưa làm mới lần nào, hoặc người vận hành vừa cấp refresh token mới
        return saved

    def _save(self, state: dict[str, Any]) -> None:
        self._mem = state
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, self._path)

    @contextlib.contextmanager
    def _file_lock(self):  # type: ignore[no-untyped-def]
        """Khoá liên tiến trình (api + worker cùng volume) để hai bên không cùng tiêu một refresh token."""
        if not self._path:
            yield
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path.with_suffix(".lock"), "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    # ---- dùng ---------------------------------------------------------------------------------------------------

    def can_refresh(self) -> bool:
        return bool(
            cc.value("zalo_oa", "app_id") and cc.value("zalo_oa", "app_secret") and self._load().get("refresh_token")
        )

    async def access_token(self) -> str:
        state = self._load()
        exp = state.get("expires_at")
        if state.get("access_token") and not (exp and exp - time.time() < EARLY_REFRESH_SECONDS and self.can_refresh()):
            return str(state["access_token"])
        if self.can_refresh():
            return await self.refresh(stale=str(state.get("access_token") or ""))
        raise IntegrationNotConfigured(
            "Chưa có access token Zalo OA: đặt ZALO_OA_ACCESS_TOKEN, hoặc ZALO_OA_REFRESH_TOKEN + ZALO_APP_ID + "
            "ZALO_APP_SECRET để hệ thống tự làm mới."
        )

    async def refresh(self, stale: str, force: bool = False) -> str:
        """Làm mới token. `stale` = token vừa bị Zalo từ chối; nếu tiến trình khác đã làm mới thì dùng luôn token đó.
        `force` (nút «Kiểm tra kết nối»): luôn gọi Zalo để chắc khoá đúng."""
        async with self._lock:
            with self._file_lock():
                if cc.has_db_config("zalo_oa"):
                    await cc.refresh()  # tiến trình khác có thể vừa lưu token mới vào CSDL
                state = self._load()
                if not force and state.get("access_token") and state["access_token"] != stale:
                    return str(state["access_token"])
                if not self.can_refresh():
                    raise IntegrationNotConfigured(
                        "Access token Zalo OA hết hạn và chưa cấu hình làm mới tự động "
                        "(ZALO_OA_REFRESH_TOKEN, ZALO_APP_ID, ZALO_APP_SECRET)."
                    )
                async with httpx.AsyncClient(timeout=20, transport=self._transport) as client:
                    r = await client.post(
                        OAUTH_URL,
                        headers={"secret_key": cc.value("zalo_oa", "app_secret") or ""},
                        data={
                            "refresh_token": state["refresh_token"],
                            "app_id": cc.value("zalo_oa", "app_id") or "",
                            "grant_type": "refresh_token",
                        },
                    )
                try:
                    body = r.json()
                except ValueError:
                    body = {}
                if not isinstance(body, dict) or not body.get("access_token"):
                    detail = (body.get("error_description") or body.get("message")) if isinstance(body, dict) else None
                    raise IntegrationNotConfigured(
                        "Zalo không làm mới được access token"
                        + (f" ({detail})" if detail else f" (HTTP {r.status_code})")
                        + ": refresh token có thể đã dùng hoặc hết hạn 3 tháng — cấp lại ZALO_OA_REFRESH_TOKEN rồi Redeploy."
                    )
                try:
                    ttl = int(body.get("expires_in") or 90000)
                except (TypeError, ValueError):
                    ttl = 90000
                new = {
                    "access_token": body["access_token"],
                    "refresh_token": body.get("refresh_token") or state["refresh_token"],
                    "expires_at": time.time() + ttl,
                    "seed": state.get("seed") or cc.value("zalo_oa", "refresh_token") or "",
                }
                if cc.has_db_config("zalo_oa"):
                    # lưu vào Cài đặt: refresh token mới thành «hạt giống» mới, mọi tiến trình đọc được
                    await cc.store_tokens(
                        "zalo_oa",
                        {"access_token": new["access_token"], "refresh_token": new["refresh_token"]},
                        {"expires_at": new["expires_at"]},
                    )
                    new["seed"] = new["refresh_token"]
                self._save(new)
                return str(new["access_token"])
