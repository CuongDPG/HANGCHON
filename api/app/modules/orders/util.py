"""Tiện ích nhỏ của orders: chuẩn hoá số điện thoại, mã đơn đọc qua điện thoại được, mã tra cứu công khai,
tìm kiếm không dấu, gợi ý tỉnh/thành."""

from __future__ import annotations

import re
import secrets
import unicodedata
import uuid

import phonenumbers
from sqlalchemy import ColumnElement, func

from app.core.config import settings
from app.core.errors import BadRequest
from app.core.security import hmac_sha256

ORDER_CODE_PREFIX = "HC-"
RETURN_CODE_PREFIX = "DT-"
CODE_DIGITS = 5  # «HC-48213»: chỉ chữ số để đọc qua điện thoại không nhầm


def normalize_phone(raw: str | None, *, required: bool = True) -> str | None:
    """Số điện thoại Việt Nam → dạng `0xxxxxxxxx`. Nhận +84, 84, dấu cách, dấu chấm, gạch ngang."""
    if raw is None or not str(raw).strip():
        if required:
            raise BadRequest("Bạn cho mình xin số điện thoại nhé.", code="phone_required")
        return None
    text = re.sub(r"[^\d+]", "", str(raw))
    if text.startswith("84") and len(text) >= 11:
        text = "+" + text
    try:
        num = phonenumbers.parse(text, "VN")
    except phonenumbers.NumberParseException as e:
        raise BadRequest("Số điện thoại chưa đúng, bạn kiểm tra lại giúp mình.", code="phone_invalid") from e
    if num.country_code != 84 or not phonenumbers.is_valid_number(num):
        raise BadRequest("Số điện thoại chưa đúng, bạn kiểm tra lại giúp mình.", code="phone_invalid")
    national = str(num.national_number)
    if len(national) != 9:
        raise BadRequest("Số điện thoại chưa đúng, bạn kiểm tra lại giúp mình.", code="phone_invalid")
    return "0" + national


def try_normalize_phone(raw: str | None) -> str | None:
    try:
        return normalize_phone(raw, required=False)
    except BadRequest:
        return None


def new_code(prefix: str = ORDER_CODE_PREFIX, digits: int = CODE_DIGITS) -> str:
    """Mã ngẫu nhiên (không lộ số đơn đã bán), không bắt đầu bằng 0 để đọc rõ."""
    first = secrets.choice("123456789")
    rest = "".join(secrets.choice("0123456789") for _ in range(digits - 1))
    return f"{prefix}{first}{rest}"


def code_suffix(code: str) -> str:
    return code.split("-", 1)[-1]


def normalize_order_code(raw: str) -> str:
    """'hc 48213', 'HC48213', '48213' → 'HC-48213'."""
    digits = re.sub(r"\D", "", raw or "")
    return f"{ORDER_CODE_PREFIX}{digits}" if digits else (raw or "").strip().upper()


def find_codes_in_transfer(content: str | None) -> list[str]:
    """Rút mã đơn từ nội dung chuyển khoản. Ngân hàng hay bỏ dấu cách/gạch ngang hoặc chèn thêm chữ:
    «HC 48213», «HC-48213», «HC48213», «MBVCB.123.HC48213.CT tu ...» đều nhận ra «HC-48213»."""
    if not content:
        return []
    prefix = re.escape(settings.payment_code_prefix.upper())
    text = content.upper()
    out: list[str] = []
    for m in re.finditer(rf"(?<![A-Z0-9]){prefix}[\s\-_.:]*(\d{{{CODE_DIGITS}}})(?!\d)", text):
        code = f"{ORDER_CODE_PREFIX}{m.group(1)}"
        if code not in out:
            out.append(code)
    if not out:  # dính liền chữ phía trước, vd «...CTHC48213»
        for m in re.finditer(rf"{prefix}[\s\-_.:]*(\d{{{CODE_DIGITS}}})(?!\d)", text):
            code = f"{ORDER_CODE_PREFIX}{m.group(1)}"
            if code not in out:
                out.append(code)
    return out


def order_access_token(order_id: uuid.UUID) -> str:
    """Mã xem đơn công khai (đính vào link gửi khách); không lưu, tính lại từ khoá bí mật."""
    return hmac_sha256(settings.jwt_secret, f"order:{order_id}".encode())[:20]


def check_access_token(order_id: uuid.UUID, token: str | None) -> bool:
    return bool(token) and secrets.compare_digest(order_access_token(order_id), token or "")


# ---- tìm không dấu trong SQL (không cần extension unaccent) ------------------------------------------------------

_VI_FROM = "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ"
_VI_TO = "a" * 17 + "e" * 11 + "i" * 5 + "o" * 17 + "u" * 11 + "y" * 5 + "d"
assert len(_VI_FROM) == len(_VI_TO)


def unaccent_sql(col: ColumnElement[str]) -> ColumnElement[str]:
    return func.translate(func.lower(col), _VI_FROM, _VI_TO)


_VI_TABLE = str.maketrans(_VI_FROM, _VI_TO)


def unaccent(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower().translate(_VI_TABLE)


# ---- gợi ý tỉnh/thành (34 đơn vị cấp tỉnh từ 01/07/2025) ----------------------------------------------------------

PROVINCES = [
    "Hà Nội", "TP. Hồ Chí Minh", "Hải Phòng", "Đà Nẵng", "Huế", "Cần Thơ",
    "An Giang", "Bắc Ninh", "Cà Mau", "Cao Bằng", "Đắk Lắk", "Điện Biên", "Đồng Nai", "Đồng Tháp", "Gia Lai",
    "Hà Tĩnh", "Hưng Yên", "Khánh Hòa", "Lai Châu", "Lâm Đồng", "Lạng Sơn", "Lào Cai", "Nghệ An", "Ninh Bình",
    "Phú Thọ", "Quảng Ngãi", "Quảng Ninh", "Quảng Trị", "Sơn La", "Tây Ninh", "Thái Nguyên", "Thanh Hóa",
    "Tuyên Quang", "Vĩnh Long",
]  # fmt: skip


def suggest_provinces(q: str, limit: int = 6) -> list[str]:
    key = unaccent(q.strip())
    if not key:
        return PROVINCES[:limit]
    starts = [p for p in PROVINCES if unaccent(p).startswith(key) or unaccent(p).replace("tp. ", "").startswith(key)]
    contains = [p for p in PROVINCES if key in unaccent(p) and p not in starts]
    return (starts + contains)[:limit]
