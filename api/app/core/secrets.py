"""Mã hoá bí mật lưu trong CSDL (khoá API của nhà cung cấp AI…) bằng Fernet (AES-128-CBC + HMAC-SHA256, có xác thực).

Khoá mã hoá lấy từ `SECRETS_ENCRYPTION_KEY` (riêng, không suy ra từ JWT_SECRET). Nhiều khoá cách nhau dấu phẩy để
xoay khoá: khoá ĐẦU dùng để mã hoá, mọi khoá đều thử khi giải mã. Production thiếu biến này thì không khởi động
(`app/core/config.py`); dev/test dùng khoá dev cố định và ghi cảnh báo.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import DEV_SECRETS_ENCRYPTION_KEY, settings
from app.core.errors import AppError

log = logging.getLogger("app.secrets")


class SecretDecryptError(AppError):
    status_code = 500
    code = "secret_decrypt_failed"
    message = (
        "Không giải mã được khoá đã lưu: SECRETS_ENCRYPTION_KEY khác với lúc lưu khoá. "
        "Đặt lại đúng biến này, hoặc nhập lại khoá ở Cài đặt → AI và khoá API."
    )


@lru_cache
def _fernet(raw: str | None) -> MultiFernet:
    if not raw:
        log.warning("Chưa đặt SECRETS_ENCRYPTION_KEY: dùng khoá dev cố định (chỉ chấp nhận ở dev/test).")
        raw = DEV_SECRETS_ENCRYPTION_KEY
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except ValueError as e:
        raise ValueError(
            "SECRETS_ENCRYPTION_KEY không đúng dạng khoá Fernet (32 byte, base64 url-safe). Sinh khoá bằng: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        ) from e


def encrypt(plain: str) -> str:
    return _fernet(settings.secrets_encryption_key).encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet(settings.secrets_encryption_key).decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise SecretDecryptError() from e


def mask(secret: str | None) -> str | None:
    """Dạng che để hiển thị: `sk-ant-…8AAA` (giữ tiền tố nhận dạng + 4 ký tự cuối)."""
    if not secret:
        return None
    s = secret.strip()
    if len(s) <= 12:
        return "…" + s[-2:]
    head = s[:7] if s.startswith("sk-") else s[:3]
    return f"{head}…{s[-4:]}"


def redact(text: str, *secrets: str | None) -> str:
    """Xoá mọi lần xuất hiện của bí mật trong chuỗi (thông báo lỗi, log)."""
    for s in secrets:
        if s and len(s) >= 6:
            text = text.replace(s, "***")
    return text
