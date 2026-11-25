"""Tìm đối tượng theo lời chị (lệnh bằng lời i6): so từ đã bỏ dấu giữa câu nói và tên món / tên đợt / tên khách.

Dùng chung cho các module đăng ký lệnh (qua `app.control.match_names`), để không module nào phải tự viết lại."""

from __future__ import annotations

import re
from collections.abc import Iterable

from unidecode import unidecode

# Từ chức năng và từ ra lệnh («tìm khách tên…», «mở đợt…»): không dùng để phân biệt món / khách / đợt với nhau.
_STOP = {
    "ai", "bai", "ban", "cai", "chi", "chiec", "cho", "co", "cua", "da", "di", "dong", "dot", "dum", "em", "giup",
    "gium", "hay", "khach", "la", "lai", "mo", "mon", "mot", "nao", "nay", "nhe", "nhung", "so", "soan", "ten", "the",
    "tim", "va", "viet", "voi", "xem",
}  # fmt: skip


def tokens(s: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", unidecode(s or "").lower())) - _STOP


def match_names[T](text: str, options: Iterable[tuple[T, str]]) -> list[T]:
    """Các lựa chọn khớp nhất với `text` (rỗng = không khớp; nhiều hơn một = chưa rõ, nên hỏi lại chị).

    Khớp khi tên nằm trọn trong câu, hoặc trùng ít nhất 2 từ, hoặc từ trùng chiếm nửa tên / nửa lời chị trở lên
    («Lan» khớp «Trần Thị Lan»). Xếp: tên nằm trọn trong câu > trùng nhiều từ hơn; bằng nhau thì trả hết để hỏi lại."""
    q = tokens(text)
    norm_text = " ".join(re.findall(r"[a-z0-9]+", unidecode(text or "").lower()))
    best: list[T] = []
    best_score: tuple[int, int] = (0, 0)
    for key, name in options:
        n = tokens(name)
        if not n or not q:
            continue
        hit = len(q & n)
        ratio = hit / len(n)
        whole = " ".join(re.findall(r"[a-z0-9]+", unidecode(name).lower()))
        contained = 1 if whole and f" {whole} " in f" {norm_text} " else 0
        if not contained and (hit == 0 or (hit < 2 and ratio < 0.5 and hit / len(q) < 0.5)):
            continue
        score = (contained, hit)
        if score > best_score:
            best, best_score = [key], score
        elif score == best_score:
            best.append(key)
    return best
