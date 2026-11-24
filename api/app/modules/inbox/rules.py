"""Luật cứng của hộp thư: nhận ra tin rủi ro (khiếu nại, hàng lỗi, sức khoẻ) và rút số điện thoại.

Dùng cho hai việc: (1) lưới an toàn sau AI — tin có dấu hiệu rủi ro thì KHÔNG BAO GIỜ tự trả lời, kể cả khi model
phân loại nhầm; (2) hàm giả của tác vụ AI (provider `fake`) để giao diện và dữ liệu mẫu chạy như thật.
Từ khoá so trên chuỗi đã bỏ dấu (`textsearch.fold`).
"""

from __future__ import annotations

import re

from app.modules.inbox.textsearch import fold

# Khiếu nại / hàng lỗi / đòi tiền — chuyển chị (h3)
DEFECT_WORDS = (
    "bi loi", "hang loi", "loi roi", "bi hong", "hong roi", "bi mop", "mop", "bi vo", "vo roi", "bi nut", "nut vo",
    "ro ri", "bi ri", "bi xuoc", "tray xuoc", "thieu hang", "giao thieu", "giao sai", "sai mau", "sai hang",
    "khong giong hinh", "khong nhu mo ta", "bi gay", "gay roi", "bung keo", "mat nap",
)  # fmt: skip
COMPLAINT_WORDS = (
    "khieu nai", "that vong", "buc minh", "lua dao", "qua te", "chan qua", "hoan tien", "tra hang", "doi tra",
    "boi thuong", "phan nan", "kem chat luong", "khong hai long", "to cao",
)  # fmt: skip
HEALTH_WORDS = (
    "di ung", "mang thai", "dang bau", "ba bau", "cho con bu", "suc khoe", "ngo doc", "doc hai", "co doc",
    "phat ban", "noi man", "bi ngua", "benh", "uong thuoc", "bac si", "tre so sinh", "so sinh", "chay mau",
    "bong da", "bi bong", "nuot phai", "bi hoc", "hoc xuong", "kich ung",
)  # fmt: skip


def _has(text: str, words: tuple[str, ...]) -> bool:
    padded = f" {text} "
    return any(f" {w} " in padded or (len(w) > 4 and w in text) for w in words)


def risk_reason(text: str) -> str | None:
    """'defect' | 'complaint' | 'health' | None — chỉ dựa vào từ khoá, không đoán."""
    t = fold(text)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    if _has(t, HEALTH_WORDS):
        return "health"
    if _has(t, DEFECT_WORDS):
        return "defect"
    if _has(t, COMPLAINT_WORDS):
        return "complaint"
    return None


_PHONE_RE = re.compile(r"(?<!\d)(?:\+?84|0)(?:[\s.\-]?\d){9}(?!\d)")


def extract_phone(text: str | None) -> str | None:
    """Số điện thoại Việt Nam đầu tiên trong tin, chuẩn hoá về dạng 0xxxxxxxxx."""
    if not text:
        return None
    m = _PHONE_RE.search(text)
    if not m:
        return None
    d = re.sub(r"\D", "", m.group(0))
    if d.startswith("84"):
        d = "0" + d[2:]
    return d if len(d) == 10 and d.startswith("0") else None


_ORDER_CODE_RE = re.compile(r"\b(HC[-\s]?\d{3,12})\b", re.IGNORECASE)


def extract_order_code(text: str | None) -> str | None:
    if not text:
        return None
    m = _ORDER_CODE_RE.search(text)
    return re.sub(r"[-\s]", "", m.group(1)).upper() if m else None
