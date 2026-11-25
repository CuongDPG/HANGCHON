"""Soát lời quảng cáo (f5) — phần kiểm bằng luật, chạy trước và cùng với AI.

Mỗi bản nháp có một danh sách mục soát (chip ✓/!):
  numbers   «Đúng số liệu trong hồ sơ»   giá, số ngày thử, số món đã thử phải khớp hồ sơ
  claims    «Không nói quá công dụng»     từ cấm trong quảng cáo (chữa bệnh, tốt nhất, 100%...)
  length    «Độ dài hợp kênh»             theo giới hạn của từng kênh
  voice     «Xưng hô với khách»           người bán xưng «mình», gọi khách «bạn»; không gọi người bán là «chị»
                                         (lời khách trích trong ngoặc «…» không tính)
  ai_label  «Nhãn nội dung AI»            có phần do AI tạo → gắn nhãn khi đăng (luôn ✓, chỉ báo)

Mục không đạt (`ok=False`) chặn nút «Duyệt» cho tới khi sửa, hoặc chị xác nhận bỏ qua có lý do (`overridden`).
"""

from __future__ import annotations

import re
from typing import Any

from app.core.enums import Channel
from app.modules.catalog.textutil import seller_address_issues
from app.modules.content.ai_io import CheckOut, DropFacts, ProductFacts
from app.modules.content.channels import LENGTH_LIMITS, MAX_HASHTAGS, VIDEO_SECONDS
from app.modules.content.models import CheckStatus

CHECK_LABELS = {
    "numbers": "Đúng số liệu trong hồ sơ",
    "claims": "Không nói quá công dụng",
    "length": "Độ dài hợp kênh",
    "voice": "Xưng hô với khách",
    "ai_label": "Nhãn nội dung AI",
}

# Cụm từ không được dùng trong quảng cáo (nói quá công dụng, so sánh tuyệt đối, hứa hẹn chữa bệnh).
BANNED_PHRASES = [
    "chữa bệnh",
    "chữa khỏi",
    "chữa trị",
    "điều trị",
    "trị dứt",
    "trị bệnh",
    "đặc trị",
    "phòng bệnh",
    "tốt nhất",
    "số 1",
    "số một",
    "hàng đầu",
    "rẻ nhất",
    "bán chạy nhất",
    "duy nhất",
    "100%",
    "100 %",
    "tuyệt đối",
    "vĩnh viễn",
    "thần kỳ",
    "thần thánh",
    "cam kết khỏi",
    "hiệu quả ngay",
    "diệt 99",
    "kháng khuẩn 99",
    "không bao giờ hỏng",
    "giảm cân",
]

_MONEY = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)\s*(k|nghìn|ngàn|đồng|đ|vnđ|vnd|₫|tr|triệu)(?![\w])",
    re.IGNORECASE,
)
_TRIAL = re.compile(r"(?:thử|dùng)[^.\n]{0,25}?(\d+)\s*(ngày|tuần|tháng)", re.IGNORECASE)
_TRIED = re.compile(r"thử\s+(\d+)\s+(?:chiếc|mẫu|loại|món|cái|kiểu|bộ)", re.IGNORECASE)


def _money_value(num: str, unit: str) -> int | None:
    unit = unit.lower()
    raw = num.replace(" ", "")
    try:
        if unit in ("k", "nghìn", "ngàn"):
            return round(float(raw.replace(",", ".")) * 1000) if raw.count(".") <= 1 else None
        if unit in ("tr", "triệu"):
            return round(float(raw.replace(",", ".")) * 1_000_000)
        return int(raw.replace(".", "").replace(",", ""))
    except ValueError:
        return None


def money_mentions(text: str) -> list[tuple[str, int]]:
    out = []
    for m in _MONEY.finditer(text):
        v = _money_value(m.group(1), m.group(2))
        if v is not None and v >= 1000:
            out.append((m.group(0).strip(), v))
    return out


def _fmt(v: int) -> str:
    return f"{v:,}".replace(",", ".") + "đ"


def allowed_prices(product: ProductFacts | None, drop: DropFacts | None) -> set[int]:
    vals: set[int] = set()
    if product:
        if product.price_vnd:
            vals.add(product.price_vnd)
        if product.compare_at_price_vnd:
            vals.add(product.compare_at_price_vnd)
            if product.price_vnd:
                vals.add(product.compare_at_price_vnd - product.price_vnd)
    if drop:
        for it in drop.items:
            vals.add(it.price_vnd)
    return {v for v in vals if v > 0}


def check_numbers(text: str, product: ProductFacts | None, drop: DropFacts | None) -> list[str]:
    problems: list[str] = []
    allowed = allowed_prices(product, drop)
    for quote, value in money_mentions(text):
        # sai lệch dưới 0,5% coi như cách viết tròn (vd 385k = 385.000đ)
        if not any(abs(value - a) <= max(500, a * 0.005) for a in allowed):
            ref = ", ".join(_fmt(a) for a in sorted(allowed)) or "chưa có giá"
            problems.append(f"Bài ghi «{quote}», hồ sơ ghi {ref}.")
    if product and product.trial_days:
        for m in _TRIAL.finditer(text):
            n, unit = int(m.group(1)), m.group(2).lower()
            days = n * {"ngày": 1, "tuần": 7, "tháng": 30}[unit]
            if abs(days - product.trial_days) > max(3, product.trial_days * 0.25):
                problems.append(f"Bài ghi thử «{m.group(1)} {unit}», hồ sơ ghi {product.trial_days} ngày.")
    if product and product.considered_count:
        for m in _TRIED.finditer(text):
            if int(m.group(1)) != product.considered_count:
                problems.append(f"Bài ghi «{m.group(0)}», hồ sơ ghi đã cân nhắc {product.considered_count} món.")
    return problems


def check_claims(text: str) -> list[str]:
    low = text.lower()
    hits = [p for p in BANNED_PHRASES if p in low]
    if not hits:
        return []
    return ["Có cụm " + ", ".join(f"«{p}»" for p in hits) + " — nói quá công dụng hoặc bị cấm trong quảng cáo."]


def check_length(channel: Channel, body: str, hashtags: list[str], scenes: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    lo, hi = LENGTH_LIMITS.get(channel, (0, 5000))
    n = len(body.strip())
    if n < lo:
        problems.append(f"Bài hơi ngắn ({n} ký tự, nên từ {lo}).")
    if n > hi:
        problems.append(f"Bài dài quá giới hạn kênh ({n}/{hi} ký tự).")
    cap = MAX_HASHTAGS.get(channel)
    if cap is not None and len(hashtags) > cap:
        problems.append(f"Nhiều hashtag quá ({len(hashtags)}/{cap}).")
    if channel == Channel.TIKTOK:
        total = sum(int(s.get("seconds") or 0) for s in scenes)
        if not scenes:
            problems.append("Chưa có kịch bản cảnh cho video.")
        elif not (VIDEO_SECONDS[0] <= total <= VIDEO_SECONDS[1]):
            problems.append(f"Video dài {total} giây, nên {VIDEO_SECONDS[0]}–{VIDEO_SECONDS[1]} giây.")
    return problems


def check_voice(text: str) -> tuple[list[str], str | None]:
    """Câu còn gọi người bán là «chị» → (vấn đề, gợi ý sửa câu đầu tiên)."""
    hits = seller_address_issues(text)
    problems = [f"«{h['quote']}» gọi người bán là «chị»." for h in hits]
    suggestion = f"Đổi thành «{hits[0]['suggestion']}» (xưng «mình», gọi khách «bạn»)." if hits else None
    return problems, suggestion


def full_text(body: str, title: str | None, scenes: list[dict[str, Any]], slides: list[dict[str, Any]]) -> str:
    parts = [title or "", body]
    for s in scenes:
        parts += [str(s.get("voiceover") or ""), str(s.get("on_screen_text") or "")]
    for s in slides:
        parts.append(str(s.get("caption") or ""))
    return "\n".join(p for p in parts if p)


def build_findings(
    *,
    channel: Channel,
    title: str | None,
    body: str,
    hashtags: list[str],
    script: list[dict[str, Any]],
    product: ProductFacts | None,
    drop: DropFacts | None,
    ai_generated: bool,
    ai: CheckOut | None,
    previous: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Gộp kết quả luật + AI thành danh sách chip. Giữ lại lần «bỏ qua có lý do» nếu nội dung mục đó không đổi."""
    scenes = [s for s in script if "voiceover" in s]
    slides = [s for s in script if "caption" in s and "voiceover" not in s]
    text = full_text(body, title, scenes, slides)
    numbers = check_numbers(text, product, drop) + [f"{i.quote}: {i.detail}" for i in (ai.number_issues if ai else [])]
    claims = check_claims(text) + [f"{i.quote}: {i.detail}" for i in (ai.claim_issues if ai else [])]
    length = check_length(channel, body, hashtags, scenes)
    voice, voice_fix = check_voice(text)
    suggestions = {
        "numbers": next((i.suggestion for i in (ai.number_issues if ai else []) if i.suggestion), None)
        or "Sửa số cho khớp hồ sơ, hoặc bỏ con số.",
        "claims": next((i.suggestion for i in (ai.claim_issues if ai else []) if i.suggestion), None)
        or "Kể trải nghiệm thật thay cho lời khẳng định.",
        "length": "Bấm «Ngắn hơn» hoặc sửa tay cho vừa kênh.",
        "voice": voice_fix,
    }
    items = []
    for key, problems in (("numbers", numbers), ("claims", claims), ("length", length), ("voice", voice)):
        items.append(
            {
                "key": key,
                "label": CHECK_LABELS[key],
                "ok": not problems,
                "detail": " ".join(dict.fromkeys(problems)) if problems else _ok_detail(key),
                "suggestion": suggestions[key] if problems else None,
            }
        )
    items.append(
        {
            "key": "ai_label",
            "label": CHECK_LABELS["ai_label"],
            "ok": True,
            "detail": "Có phần do AI soạn — sẽ gắn nhãn khi đăng." if ai_generated else "Chị tự viết, không cần nhãn.",
            "suggestion": None,
        }
    )
    prev = {f.get("key"): f for f in previous or []}
    for it in items:
        old = prev.get(it["key"])
        if not it["ok"] and old and old.get("overridden") and old.get("detail") == it["detail"]:
            it["overridden"] = True
            it["override_reason"] = old.get("override_reason")
    return items


def _ok_detail(key: str) -> str:
    return {
        "numbers": "Giá và số liệu khớp hồ sơ sản phẩm.",
        "claims": "Không có lời nói quá công dụng.",
        "length": "Độ dài vừa với kênh.",
        "voice": "Xưng «mình», gọi khách «bạn».",
    }[key]


def status_of(findings: list[dict[str, Any]]) -> CheckStatus:
    if not findings:
        return CheckStatus.UNCHECKED
    bad = [f for f in findings if not f.get("ok")]
    if not bad:
        return CheckStatus.PASSED
    if all(f.get("overridden") for f in bad):
        return CheckStatus.WARNINGS  # còn mục chưa đạt nhưng chị đã xác nhận bỏ qua có lý do
    return CheckStatus.FAILED


def can_approve(status: CheckStatus) -> bool:
    return status in (CheckStatus.PASSED, CheckStatus.WARNINGS)
