"""Soát lời quảng cáo (f5) — phần kiểm bằng luật, chạy trước và cùng với AI.

Mỗi bản nháp có một danh sách mục soát (chip ✓/!):
  numbers   «Đúng số liệu trong hồ sơ»   giá, số ngày thử phải khớp hồ sơ
  claims    «Không nói quá công dụng»     từ cấm trong quảng cáo (chữa bệnh, tốt nhất, 100%...)
  length    «Độ dài hợp kênh»             theo giới hạn của từng kênh
  voice     «Xưng hô với khách»           người bán xưng «mình», gọi khách «bạn»; không gọi người bán là «chị»
                                         (lời khách trích trong ngoặc «…» không tính)
  process   «Không kể quá trình chọn»     khách chỉ đọc nội dung cuối: không «hồ sơ chọn», mẫu bị loại, số món đã xem/thử
  reason    «Có «Vì sao mình chọn món này»» luật của chị: mọi bài về một sản phẩm, mọi kênh (TikTok: trong lời thoại)
  safety    «Giữ cảnh báo an toàn»        hồ sơ có cảnh báo an toàn (vd chi tiết nhỏ dễ nuốt) thì bài phải nhắc
  ai_label  «Nhãn nội dung AI»            có phần do AI tạo → gắn nhãn khi đăng (luôn ✓, chỉ báo)

Mục không đạt (`ok=False`) chặn nút «Duyệt» cho tới khi sửa, hoặc chị xác nhận bỏ qua có lý do (`overridden`).
"""

from __future__ import annotations

import re
import unicodedata
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
    "process": "Không kể quá trình chọn",
    "reason": "Có «Vì sao mình chọn món này»",
    "safety": "Giữ cảnh báo an toàn",
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
# Dấu vết quá trình chọn — nội bộ ở desk, bài cho khách không nhắc (vd «hồ sơ chọn», «mẫu bị loại», «thử 6 mẫu»).
_PROCESS = [
    re.compile(r"hồ sơ chọn", re.IGNORECASE),
    re.compile(r"(?:mẫu|món|chiếc|cái|loại)\s+(?:đã\s+)?bị\s+loại", re.IGNORECASE),
    re.compile(r"\bso kỹ\b", re.IGNORECASE),
    re.compile(r"chọn\s+\d+\s+trong\s+\d+", re.IGNORECASE),
    re.compile(
        r"(?:xem|thử|so sánh|so|cân nhắc|loại)\s+(?:qua\s+)?\d+\s+(?:chiếc|mẫu|loại|món|cái|kiểu|bộ|sản phẩm)",
        re.IGNORECASE,
    ),
]


# «Vì sao mình chọn món này» — chấp nhận «vì sao/tại sao/lý do mình chọn …».
_REASON = re.compile(r"(?:vì sao|tại sao|lý do|lí do)\s+mình\s+(?:lại\s+)?chọn", re.IGNORECASE)

# Lời hứa / ưu đãi / dịch vụ cho khách: chỉ được nói khi hồ sơ có (bài đầu tiên tự thêm «đóng túi zip cho bạn»).
_PROMISE_WORDS = [
    "tặng kèm", "quà tặng", "miễn phí", "freeship", "free ship", "bảo hành", "đổi trả", "hoàn tiền", "bao đổi",
    "cam kết", "giao ngay", "giao hoả tốc", "giao hỏa tốc",
]  # fmt: skip
_SERVICE_FOR_YOU = re.compile(
    r"\b(?:đóng|gói|bọc|tặng|kèm|thêm|gửi kèm|chuẩn bị|làm sẵn)\b[^.!?\n]{0,40}?\bcho\s+(?:bạn|cả nhà|khách)\b",
    re.IGNORECASE,
)

# Nhóm từ của từng loại cảnh báo an toàn: cảnh báo có từ của nhóm nào thì bài phải có ít nhất một từ của nhóm đó.
_SAFETY_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("hóc/nuốt", ("hóc", "nuốt", "xa tầm tay", "ngoài tầm tay")),
    ("dị ứng", ("dị ứng",)),
    ("bỏng/nóng", ("bỏng", "nóng")),
    ("cạnh sắc", ("sắc", "cứa", "cắt tay")),
]


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
    return problems


def check_process(text: str) -> list[str]:
    """Bài nhắc quá trình chọn (hồ sơ chọn, mẫu bị loại, số món đã xem/thử) → mỗi chỗ một vấn đề."""
    quotes = [m.group(0) for rx in _PROCESS for m in rx.finditer(unicodedata.normalize("NFC", text))]
    return [f"«{q}» kể quá trình chọn — khách chỉ cần biết vì sao mình chọn món này." for q in dict.fromkeys(quotes)]


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


def dossier_text(product: ProductFacts | None, drop: DropFacts | None) -> str:
    """Mọi chữ trong hồ sơ — nguồn để biết một lời hứa có thật hay bài tự thêm."""
    parts: list[str] = []
    if product:
        parts += [product.name, product.subtitle or "", product.short_description or "", product.reason_selected or ""]
        parts += [product.not_satisfied or "", *product.trial_notes, *product.safety_warnings]
        parts += [q.text for q in product.customer_reasons]
        parts += product.public_trial_notes
        parts += [" ".join(str(v) for v in s.values()) for s in product.specs]
    if drop:
        parts += [drop.title, drop.description or ""]
    return _norm("\n".join(parts))


def check_promises(text: str, product: ProductFacts | None, drop: DropFacts | None) -> list[str]:
    """Lời hứa/ưu đãi/dịch vụ cho khách mà hồ sơ không ghi → mỗi chỗ một vấn đề."""
    low, src = _norm(text), dossier_text(product, drop)
    problems = [f"«{w}» — hồ sơ không có lời hứa/ưu đãi này." for w in _PROMISE_WORDS if w in low and w not in src]
    for m in _SERVICE_FOR_YOU.finditer(unicodedata.normalize("NFC", text)):
        who = re.sub(r"\s+", " ", m.group(0).lower().rsplit("cho", 1)[-1].strip())
        if f"cho {who}" not in src:
            problems.append(f"«{m.group(0)}» — hồ sơ không hứa việc này với khách (chỉ kể việc mình đã làm khi thử).")
    return problems


def check_reason(channel: Channel, body: str, scenes: list[dict[str, Any]], product: ProductFacts | None,
                 drop: DropFacts | None) -> list[str]:  # fmt: skip
    """Luật của chị: bài về một sản phẩm phải có «Vì sao mình chọn món này» (TikTok: trong lời thoại)."""
    if product is None or drop is not None:
        return []
    if channel == Channel.TIKTOK:
        spoken = " ".join(str(s.get("voiceover") or "") for s in scenes)
        if not _REASON.search(_norm(spoken)):
            return ["Lời thoại chưa có câu «Vì sao mình chọn món này…» kèm lý do chọn."]
        return []
    if not _REASON.search(_norm(body)):
        return ["Bài chưa có phần «Vì sao mình chọn món này» kèm lý do chọn."]
    return []


def check_safety(text: str, product: ProductFacts | None) -> list[str]:
    """Hồ sơ có cảnh báo an toàn thì bài phải nhắc (soát theo nhóm từ; cảnh báo không thuộc nhóm nào thì để AI soát)."""
    if product is None or not product.safety_warnings:
        return []
    low = _norm(text)
    problems = []
    for warning in product.safety_warnings:
        w = _norm(warning)
        for label, words in _SAFETY_GROUPS:
            if any(x in w for x in words) and not any(x in low for x in words):
                problems.append(f"Bài thiếu cảnh báo {label}: «{warning}».")
    return list(dict.fromkeys(problems))


# Lời giải thích tự nói «không phải lỗi» thì mục đó không phải lỗi (lần chạy thật: verdict fail nhưng giải thích
# «khớp hồ sơ, không phải lỗi»).
_SELF_CLEARED = ("không phải lỗi", "không phải là lỗi", "không sai", "không vi phạm", "khớp hồ sơ", "đúng hồ sơ")


def _self_cleared(issue: Any) -> bool:
    return any(p in _norm(issue.detail) for p in _SELF_CLEARED)


def is_real_issue(issue: Any) -> bool:
    return getattr(issue, "severity", "fail") == "fail" and not _self_cleared(issue)


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
    ai_numbers = [i for i in (ai.number_issues if ai else []) if is_real_issue(i)]
    ai_claims = [i for i in (ai.claim_issues if ai else []) if is_real_issue(i)]
    # góp ý = mục AI ghi severity=note mà lời giải thích không tự gỡ («khớp hồ sơ», «không phải lỗi») — không chặn duyệt
    every = [*(ai.number_issues if ai else []), *(ai.claim_issues if ai else [])]
    ai_notes = [i for i in every if not is_real_issue(i) and not _self_cleared(i)]
    numbers = check_numbers(text, product, drop) + [f"{i.quote}: {i.detail}" for i in ai_numbers]
    claims = check_claims(text) + check_promises(text, product, drop) + [f"{i.quote}: {i.detail}" for i in ai_claims]
    length = check_length(channel, body, hashtags, scenes)
    voice, voice_fix = check_voice(text)
    process = check_process(text)
    reason = check_reason(channel, body, scenes, product, drop)
    safety = check_safety(text, product)
    suggestions = {
        "numbers": next((i.suggestion for i in ai_numbers if i.suggestion), None)
        or "Sửa số cho khớp hồ sơ, hoặc bỏ con số.",
        "claims": next((i.suggestion for i in ai_claims if i.suggestion), None)
        or "Kể trải nghiệm thật thay cho lời khẳng định; bỏ lời hứa hồ sơ không có.",
        "length": "Bấm «Ngắn hơn» hoặc sửa tay cho vừa kênh.",
        "voice": voice_fix,
        "process": "Bỏ phần kể quá trình chọn; giữ lý do chọn và điều chưa ưng.",
        "reason": "Thêm «Vì sao mình chọn món này: …» kèm lý do chọn"
        + (" vào lời thoại một cảnh." if channel == Channel.TIKTOK else "."),
        "safety": "Thêm câu cảnh báo ngắn, vd «Chi tiết nhỏ, bạn để xa tầm tay bé nhỏ».",
    }
    items = []
    for key, problems in (
        ("numbers", numbers),
        ("claims", claims),
        ("length", length),
        ("voice", voice),
        ("process", process),
        ("reason", reason),
        ("safety", safety),
    ):
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
    if ai_notes:  # góp ý của AI (không phải lỗi): hiện kèm, không chặn duyệt
        claims_item = next(it for it in items if it["key"] == "claims")
        if claims_item["ok"]:
            claims_item["detail"] += " Góp ý: " + " ".join(f"«{i.quote}»: {i.detail}" for i in ai_notes[:3])
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
        "process": "Không nhắc quá trình chọn, chỉ kể vì sao mình chọn.",
        "reason": "Có phần «Vì sao mình chọn món này».",
        "safety": "Giữ đủ cảnh báo an toàn của hồ sơ.",
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
