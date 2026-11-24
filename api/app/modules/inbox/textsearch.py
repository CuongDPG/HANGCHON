"""Tìm kiếm tiếng Việt không dấu trong SQL (dùng chung cho inbox và crm).

Không cần extension `unaccent`: bỏ dấu bằng `translate(lower(x), 'àá…đ', 'aa…d')`. Chuỗi tìm được bỏ dấu
phía Python bằng cùng bảng, nên «ha noi» khớp «Hà Nội», «Đào» khớp «dao».
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import ColumnElement, func

VI_FROM = "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ"
VI_TO = "a" * 17 + "e" * 11 + "i" * 5 + "o" * 17 + "u" * 11 + "y" * 5 + "d"
assert len(VI_FROM) == len(VI_TO)

_TABLE = str.maketrans(VI_FROM, VI_TO)


def fold(text: str | None) -> str:
    """Chữ thường, bỏ dấu tiếng Việt, gộp khoảng trắng."""
    if not text:
        return ""
    s = unicodedata.normalize("NFC", text).lower().translate(_TABLE)
    return re.sub(r"\s+", " ", s).strip()


def sql_fold(expr: ColumnElement[str] | object) -> ColumnElement[str]:
    """Biểu thức SQL tương ứng `fold` (NULL → '')."""
    return func.translate(func.lower(func.coalesce(expr, "")), VI_FROM, VI_TO)


def like_pattern(q: str) -> str:
    """Mẫu ILIKE cho chuỗi đã fold (thoát %, _)."""
    s = fold(q).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{s}%"


def digits(q: str | None) -> str:
    return re.sub(r"\D+", "", q or "")


def email_local(expr: ColumnElement[str] | object) -> ColumnElement[str]:
    """Phần trước @ của email — tên miền ai cũng giống nhau nên không đem ra so."""
    return func.split_part(func.coalesce(expr, ""), "@", 1)
