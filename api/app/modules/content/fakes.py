"""Hàm giả cho provider `fake`: sinh bài tiếng Việt tự nhiên, khác nhau theo kênh, bám đúng hồ sơ sản phẩm.

Không gọi model — dùng cho test và chạy thử trên máy không có khoá. Mọi con số lấy từ hồ sơ, không bịa."""

from __future__ import annotations

import re
from collections import Counter
from itertools import pairwise

from app.modules.content.ai_io import (
    ChannelDraftOut,
    CheckIn,
    CheckOut,
    ComposeIn,
    ComposeOut,
    DropFacts,
    InsightFinding,
    InsightIn,
    InsightOut,
    LiveFaq,
    LiveIn,
    LiveItem,
    LiveOut,
    LiveSegment,
    MusicHint,
    PlanWeekIn,
    PlanWeekOut,
    ProductFacts,
    RewriteIn,
    Scene,
    Slide,
    SlotIdea,
    VideoPlanIn,
    VideoPlanOut,
    VideoSegment,
    VoiceLearnIn,
    VoiceLearnOut,
)


def vnd(v: int | None) -> str:
    return f"{(v or 0):,}".replace(",", ".") + "đ"


def _first_sentence(text: str | None, fallback: str = "") -> str:
    if not text:
        return fallback
    s = re.split(r"(?<=[.!?…])\s+", text.strip())[0]
    return s.rstrip(".!?… ")


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def _trial_text(p: ProductFacts) -> str:
    if not p.trial_days:
        return "một thời gian"
    if p.trial_days % 7 == 0 and p.trial_days >= 14:
        return f"{p.trial_days // 7} tuần"
    return f"{p.trial_days} ngày"


def _tags(p: ProductFacts | None, extra: list[str]) -> list[str]:
    base = ["#hangchon", "#dathuthat"]
    if p:
        word = re.sub(r"[^\wÀ-ỹ]", "", p.name.split()[0].lower()) if p.name else ""
        if word:
            base.append(f"#{word}")
    return base + extra


def _facebook(p: ProductFacts, notes: list[str], instruction: str | None) -> ChannelDraftOut:
    reason = _first_sentence(p.reason_selected, "dùng hằng ngày thấy tiện thật")
    meh = _first_sentence(p.not_satisfied, "")
    lines = [
        f"{p.name} — mình dùng {_trial_text(p)} rồi mới đưa lên kệ.",
        "",
        f"Vì sao mình chọn món này: {_lower_first(reason)}.",
    ]
    if notes:
        lines += ["", f"Ghi chú lúc thử: «{_first_sentence(notes[0])}.»"]
    if p.customer_reasons:  # trích nguyên văn lời một khách đã mua (chị đã duyệt), không bắt buộc
        q = p.customer_reasons[0]
        lines += ["", f"Bạn {q.name} đã mua kể: “{q.text}”"]
    if meh:
        lines += ["", f"Điều mình chưa ưng: {_lower_first(meh)}. Bạn cân nhắc giúp mình nhé."]
    lines += ["", f"Giá {vnd(p.price_vnd)}. Cần thì nhắn mình, hoặc xem chi tiết ở link bên dưới."]
    return ChannelDraftOut(
        channel="facebook",
        title=f"{_trial_text(p).capitalize()} thử {_lower_first(p.name)}",
        body="\n".join(lines),
        hashtags=_tags(p, [])[:3],
    )


def _instagram(p: ProductFacts) -> ChannelDraftOut:
    reason = _first_sentence(p.reason_selected, "dùng mỗi ngày thấy tiện")
    meh = _first_sentence(p.not_satisfied, "")
    body = f"{p.name}, mình dùng thật {_trial_text(p)} rồi mới chọn. Vì sao mình chọn: {_lower_first(reason)}."
    if meh:
        body += f" Chưa ưng: {_lower_first(meh)}."
    body += " Xem chi tiết ở link trên trang cá nhân."
    n = max(1, min(p.image_count or 3, 6))
    captions = [
        f"{p.name} — ảnh mình tự chụp",
        _first_sentence(p.reason_selected, "Dùng thật mỗi ngày"),
        "Chi tiết mình thích nhất",
        _first_sentence(p.not_satisfied, "Điều chưa ưng, nói thật"),
        f"Sau {_trial_text(p)} dùng thật",
        "Kích thước so với bàn tay",
    ]
    slides = [
        Slide(image_index=i, caption=(p.image_alts[i] if i < len(p.image_alts) and p.image_alts[i] else captions[i]))
        for i in range(n)
    ]
    return ChannelDraftOut(
        channel="instagram",
        title=f"{n} ảnh {_lower_first(p.name)}",
        body=body,
        hashtags=_tags(p, ["#giadung", "#donhabep", "#reviewthat", "#homeliving", "#tidyhome"]),
        slides=slides,
    )


def _threads(p: ProductFacts) -> ChannelDraftOut:
    meh = _first_sentence(p.not_satisfied, "")
    reason = _first_sentence(p.reason_selected, "dùng thật thấy tiện")
    body = f"{p.name}, mình dùng {_trial_text(p)} rồi mới chọn. Vì sao mình chọn: {_lower_first(reason)}."
    if meh:
        body += f" Mỗi tội {_lower_first(meh)}."
    body += " Bạn có món nào dùng mãi không chán không?"
    return ChannelDraftOut(channel="threads", title="Vì sao mình chọn món này", body=body[:480], hashtags=[])


def _tiktok(p: ProductFacts) -> ChannelDraftOut:
    reason = _first_sentence(p.reason_selected, "dùng mỗi ngày thấy tiện")
    meh = _first_sentence(p.not_satisfied, "có một điểm nhỏ chưa ưng")
    scenes = [
        Scene(
            scene=1,
            seconds=3,
            visual=f"Bàn tay đặt {p.name} lên bàn",
            voiceover="Vì sao mình chọn món này?",
            on_screen_text="Vì sao mình chọn",
        ),
        Scene(
            scene=2,
            seconds=7,
            visual=f"Cận cảnh dùng {p.name} như mọi ngày",
            voiceover=f"{reason}.",
            on_screen_text=_first_sentence(p.reason_selected, "Dùng thật")[:40],
        ),
        Scene(
            scene=3,
            seconds=6,
            visual="Tháo, rửa, lắp lại bằng tay",
            voiceover=f"Sau {_trial_text(p)} vẫn dùng đều.",
            on_screen_text=f"{_trial_text(p)} dùng thật",
        ),
        Scene(
            scene=4,
            seconds=5,
            visual="Chỉ vào điểm chưa ưng",
            voiceover=f"Chưa ưng: {_lower_first(meh)}.",
            on_screen_text="Nói thật điều chưa ưng",
        ),
        Scene(
            scene=5,
            seconds=4,
            visual="Đặt món hàng xuống, hiện giá",
            voiceover="Link chi tiết ở trang cá nhân nhé.",
            on_screen_text=f"{vnd(p.price_vnd)}",
        ),
    ]
    return ChannelDraftOut(
        channel="tiktok",
        title=f"Video {sum(s.seconds for s in scenes)} giây",
        body=f"Vì sao mình chọn {p.name}: {_lower_first(reason)}."
        + (" Có cả điều chưa ưng." if p.not_satisfied else ""),
        hashtags=["#hangchon", "#reviewthat", "#giadung"],
        scenes=scenes,
    )


def _zalo(p: ProductFacts) -> ChannelDraftOut:
    body = (
        f"Chào cả nhà, mình vừa lên kệ {p.name}, đã dùng {_trial_text(p)}. Vì sao mình chọn: "
        f"{_lower_first(_first_sentence(p.reason_selected, 'dùng thật thấy tiện'))}. "
        + (f"Chưa ưng: {_lower_first(_first_sentence(p.not_satisfied))}. " if p.not_satisfied else "")
        + f"Giá {vnd(p.price_vnd)}. Ai cần thì nhắn mình giữ suất nhé."
    )
    return ChannelDraftOut(channel="zalo_oa", title="Tin cho khách quen", body=body, hashtags=[])


def _drop_drafts(d: DropFacts, channels: list[str]) -> list[ChannelDraftOut]:
    names = ", ".join(i.name for i in d.items[:4]) or d.title
    price_lines = "\n".join(
        f"• {i.name}: {vnd(i.price_vnd)}" + (f" ({i.slots_total} suất)" if i.slots_total else "") for i in d.items
    )
    close = f" Đợt nhận đặt tới {d.closes_at_text}." if d.closes_at_text else ""
    arrive = f" Hàng dự kiến về {d.expected_arrival_text}." if d.expected_arrival_text else ""
    deposit = f" Đặt cọc {d.deposit_pct}% để giữ suất." if d.deposit_pct else ""
    out = []
    for ch in channels:
        if ch == "facebook":
            body = f"Mở {d.title}.{close}\n\nLần này có: {names}. Món nào mình cũng đã dùng thử rồi mới đưa vào.\n\n{price_lines}\n{arrive}{deposit}\n\nĐặt theo link bên dưới, hoặc nhắn mình."
            out.append(
                ChannelDraftOut(
                    channel="facebook", title=f"Mở {d.code}", body=body.strip(), hashtags=["#hangchon", "#dotgom"]
                )
            )
        elif ch == "instagram":
            slides = [
                Slide(image_index=i, caption=f"{it.name} · {vnd(it.price_vnd)}") for i, it in enumerate(d.items[:6])
            ]
            out.append(
                ChannelDraftOut(
                    channel="instagram",
                    title=f"Ảnh mở {d.code}",
                    body=f"{d.title} đã mở.{close} {names}. Link đặt trên trang cá nhân.",
                    hashtags=["#hangchon", "#dotgom", "#giadung", "#homeliving"],
                    slides=slides or [Slide(image_index=0, caption=d.title)],
                )
            )
        elif ch == "zalo_oa":
            out.append(
                ChannelDraftOut(
                    channel="zalo_oa",
                    title=f"Báo khách quen {d.code}",
                    body=f"Cả nhà ơi, mình mở {d.title}.{close} Có {names}.{deposit} Ai cần nhắn mình giữ suất trước nhé.",
                    hashtags=[],
                )
            )
    return out


BUILDERS = {"instagram": _instagram, "threads": _threads, "tiktok": _tiktok, "zalo_oa": _zalo}


def _add_warnings(d: ChannelDraftOut, p: ProductFacts) -> None:
    """Cảnh báo an toàn bắt buộc có trong mọi bài; TikTok nói trong lời thoại cảnh cuối."""
    if not p.safety_warnings:
        return
    line = f"Lưu ý: {_lower_first(_first_sentence(p.safety_warnings[0]))}."
    if d.scenes:
        d.scenes[-1].voiceover = f"{d.scenes[-1].voiceover} {line}"
    else:
        d.body = f"{d.body.rstrip()}\n\n{line}" if d.channel == "facebook" else f"{d.body.rstrip()} {line}"


def fake_compose(inp: ComposeIn) -> ComposeOut:
    if inp.kind == "drop" and inp.drop:
        return ComposeOut(drafts=_drop_drafts(inp.drop, list(inp.channels)))
    assert inp.product is not None
    drafts = []
    for ch in inp.channels:
        notes = inp.trial_notes or inp.product.trial_notes
        d = _facebook(inp.product, notes, inp.instruction) if ch == "facebook" else BUILDERS[ch](inp.product)
        _add_warnings(d, inp.product)
        if inp.instruction:
            d.body = f"{d.body}\n\n{_instruction_line(inp.instruction)}" if ch == "facebook" else d.body
        drafts.append(d)
    return ComposeOut(drafts=drafts)


def _instruction_line(instruction: str) -> str:
    # lời dặn nội bộ («Chị trả lại với lời nhắn: …») là chỉ dẫn cho AI, không chép tiền tố vào bài khách đọc
    text = re.sub(r"^chị trả lại với lời nhắn:\s*", "", instruction.strip(), flags=re.IGNORECASE).rstrip(".")
    return f"P.S. {text[:1].upper()}{text[1:]}."


def _sentences(body: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?…])\s+|\n+", body) if s.strip()]


def fake_rewrite(inp: RewriteIn) -> ChannelDraftOut:
    cur = inp.current.model_copy(deep=True)
    ins = inp.instruction.lower()
    if "ngắn" in ins:
        sents = _sentences(cur.body)
        keep = max(1, round(len(sents) * 0.55))
        cur.body = " ".join(s.strip() for s in sents[:keep])
        if cur.scenes:
            cur.scenes = cur.scenes[:4]
            cur.scenes[-1].seconds = max(cur.scenes[-1].seconds, 20 - sum(s.seconds for s in cur.scenes[:-1]))
    elif "ấm" in ins:
        opener = "Cả nhà ơi," if inp.channel in ("zalo_oa", "facebook") else "Kể bạn nghe nè,"
        cur.body = f"{opener} {_lower_first(cur.body)}\n\nCảm ơn bạn đã đọc tới đây, cần gì cứ nhắn mình nha."
    elif "giá" in ins:
        price = None
        if inp.product:
            price = f"Giá {vnd(inp.product.price_vnd)}"
            if inp.product.compare_at_price_vnd:
                price += f" (giá thường {vnd(inp.product.compare_at_price_vnd)})"
        elif inp.drop and inp.drop.items:
            price = "Giá trong đợt: " + ", ".join(f"{i.name} {vnd(i.price_vnd)}" for i in inp.drop.items[:3])
        if price and price not in cur.body:
            cur.body = f"{cur.body.rstrip()}\n\n{price}."
    else:
        cur.body = f"{cur.body.rstrip()}\n\n{_instruction_line(inp.instruction)}"
    if inp.channel == "threads":
        cur.body = cur.body[:480]
    return cur


def fake_check(inp: CheckIn) -> CheckOut:
    # Phần luật (checks.py) đã bắt giá/ngày thử/từ cấm; hàm giả chỉ thêm nhận xét chung.
    return CheckOut(note="Đã đọc đối chiếu với hồ sơ sản phẩm.")


STOP = set(
    "và là của có cho thì mà này kia các những một được không với để nên cũng như khi rồi đã đang sẽ vì nhưng "
    "lại ra vào trong ngoài trên dưới hơn nữa rất quá lắm thôi đó đây nào ai gì bao nhiêu nhé nha ạ ơi".split()
)


def fake_learn_voice(inp: VoiceLearnIn) -> VoiceLearnOut:
    text = "\n".join([*inp.samples, *inp.spoken])
    low = text.lower()
    words = re.findall(r"[a-zà-ỹđ]+", low)
    pron = Counter(w for w in words if w in {"mình", "em", "chị", "tớ", "tui", "bạn", "cả", "mọi"})
    self_word = max(("mình", "em", "chị", "tớ", "tui"), key=lambda w: pron.get(w, 0))
    other = "cả nhà" if "cả nhà" in low else ("mọi người" if "mọi người" in low else "bạn")
    sents = [s for s in re.split(r"[.!?…\n]+", text) if s.strip()]
    avg = round(sum(len(s.split()) for s in sents) / max(1, len(sents)))
    style = "câu ngắn, nhịp nhanh" if avg <= 12 else ("câu vừa, kể chuyện" if avg <= 22 else "câu dài, giải thích kỹ")
    bigrams = Counter(f"{a} {b}" for a, b in pairwise(words) if a not in STOP and b not in STOP)
    vocab = [w for w, c in bigrams.most_common(8) if c >= 2][:6] or [
        w for w, _ in Counter(w for w in words if w not in STOP and len(w) > 2).most_common(6)
    ]
    avoid = ["Từ «tốt nhất», «số 1», «thần thánh»", "Hô hào kiểu «mua ngay kẻo hết»"]
    for line in (inp.notes or "").splitlines():
        line = line.strip(" -•")
        if line.lower().startswith(("không", "tránh", "đừng")):
            avoid.append(line[:1].upper() + line[1:])
    rules = ["Kể trải nghiệm dùng thật trước, giá sau", "Mỗi bài nêu một điều chưa ưng"]
    if "?" in text:
        rules.append("Hay kết bằng một câu hỏi cho người đọc")
    examples = [s.strip() for s in sents if 6 <= len(s.split()) <= 30][:3]
    return VoiceLearnOut(
        style_summary=f"Viết như đang kể cho người quen: xưng «{self_word}», gọi «{other}», {style}. Thật thà, nói cả điều chưa ưng.",
        pronouns=f"Xưng «{self_word}» – gọi «{other}»",
        sentence_style=f"Trung bình {avg} chữ mỗi câu — {style}.",
        vocabulary=vocab,
        rules=rules,
        avoid=list(dict.fromkeys(avoid)),
        examples=examples,
    )


IDEA_KINDS = [
    ("Hỏi đáp: 3 câu khách hay hỏi về {name}", "Món đã lâu chưa có bài, khách hỏi nhiều trong hộp thư"),
    ("Vì sao mình chọn {name}: lý do dùng thấy hợp và điều còn chưa ưng", "Bài kể lý do chọn thường giữ người đọc lâu"),
    ("Video ngắn: {name} sau những ngày dùng thật", "Video ngắn có lượt xem cao hơn bài chữ"),
    ("Điều chưa ưng ở {name} — nói thật", "Bài nói thật điều chưa ưng hay được chia sẻ"),
]


def fake_plan_week(inp: PlanWeekIn) -> PlanWeekOut:
    prods = sorted(inp.products, key=lambda p: (-(p.days_since_last_post or 999), -p.orders_from_posts))
    out = []
    for i, slot in enumerate(inp.empty_slots):
        if not prods:
            idea, reason, pid = "Bài kể chuyện một ngày đi săn hàng", "Chưa có sản phẩm nào để gợi ý", None
        else:
            p = prods[i % len(prods)]
            tmpl, reason = IDEA_KINDS[(i + slot.index) % len(IDEA_KINDS)]
            idea, pid = tmpl.format(name=p.name), p.id
            if inp.insights:
                reason = f"{reason}. {inp.insights[0]}"
        out.append(SlotIdea(slot_index=slot.index, product_id=pid, idea=idea, reason=reason))
    return PlanWeekOut(suggestions=out)


def fake_plan_video(inp: VideoPlanIn) -> VideoPlanOut:
    clips = inp.clips or []
    target = max(20, min(30, inp.target_seconds))
    per = target / max(1, len(clips))
    p = inp.product
    captions = [
        "Vì sao mình chọn món này",
        _first_sentence(p.reason_selected, "Dùng thật mỗi ngày") if p else "Dùng thật mỗi ngày",
        f"Sau {_trial_text(p)} vẫn ổn" if p else "Dùng đều mỗi ngày",
        ("Chưa ưng: " + _lower_first(_first_sentence(p.not_satisfied, "có một điểm nhỏ"))) if p else "Có điểm chưa ưng",
        vnd(p.price_vnd) if p else "Link ở trang cá nhân",
    ]
    segs = []
    for i, c in enumerate(clips):
        length = min(per, max(1.0, c.duration_seconds))
        start = max(0.0, min(c.duration_seconds - length, c.duration_seconds * 0.15))
        segs.append(
            VideoSegment(
                clip_index=c.index,
                start=round(start, 1),
                end=round(start + length, 1),
                caption=(c.note or captions[i % len(captions)])[:60],
            )
        )
    return VideoPlanOut(
        summary=f"Dựng {len(segs)} đoạn thành video khoảng {round(sum(s.end - s.start for s in segs))} giây, dọc 9:16, chữ trên hình mỗi cảnh.",
        segments=segs,
        music=MusicHint(
            mood="nhẹ nhàng, ấm",
            suggestion="Nhạc acoustic không lời trong thư viện TikTok/Instagram (tránh nhạc có bản quyền)",
            bpm=90,
        ),
        cover_text=captions[0],
    )


def fake_insights(inp: InsightIn) -> InsightOut:
    posts = inp.posts
    if not posts:
        return InsightOut(
            summary="Chưa có bài nào đủ số liệu trong kỳ này.",
            findings=[
                InsightFinding(
                    pattern="Chưa đủ dữ liệu",
                    evidence="0 bài đã đăng có số liệu",
                    recommendation="Giữ giờ đăng mặc định thêm một tuần",
                )
            ],
        )
    by_ch: dict[str, list] = {}
    for p in posts:
        by_ch.setdefault(p.channel, []).append(p)
    best_ch = max(by_ch, key=lambda c: (sum(x.orders for x in by_ch[c]), sum(x.clicks for x in by_ch[c])))
    ch_orders = sum(x.orders for x in by_ch[best_ch])
    priced = [p for p in posts if p.has_price]
    unpriced = [p for p in posts if not p.has_price]

    def avg(xs, f):
        return round(sum(f(x) for x in xs) / len(xs), 1) if xs else 0

    hours = Counter(p.hour for p in posts if p.orders > 0) or Counter(p.hour for p in posts)
    best_hour = hours.most_common(1)[0][0]
    findings = [
        InsightFinding(
            pattern=f"{best_ch.capitalize()} ra đơn nhiều nhất",
            evidence=f"{ch_orders} đơn từ {len(by_ch[best_ch])} bài {best_ch}",
            recommendation=f"Giữ ít nhất 3 bài {best_ch} mỗi tuần",
        ),
        InsightFinding(
            pattern=f"Bài đăng khoảng {best_hour}:00 hiệu quả hơn",
            evidence=f"{hours[best_hour]} bài ra đơn/tương tác tốt ở khung {best_hour}:00",
            recommendation=f"Xếp bài chính tuần sau quanh {best_hour}:00",
        ),
    ]
    if priced and unpriced:
        a, b = avg(priced, lambda x: x.orders), avg(unpriced, lambda x: x.orders)
        better = "có giá" if a >= b else "không ghi giá"
        findings.append(
            InsightFinding(
                pattern=f"Bài {better} ra đơn tốt hơn",
                evidence=f"Trung bình {a} đơn/bài có giá so với {b} đơn/bài không ghi giá",
                recommendation="Ghi giá ngay trong bài" if a >= b else "Để giá trong hồ sơ, bài tập trung kể chuyện",
            )
        )
    top = sorted(posts, key=lambda p: (p.orders, p.clicks, p.reach), reverse=True)[:3]
    total_orders = sum(p.orders for p in posts)
    return InsightOut(
        summary=f"{len(posts)} bài, {total_orders} đơn gắn được với bài. {findings[0].pattern}.",
        findings=findings[:3],
        top_post_ids=[p.post_id for p in top],
    )


GENERIC_Q = [
    ("Dùng được bao lâu thì phải thay?", "trial"),
    ("Vì sao chọn món này?", "reason"),
    ("Có điểm gì chưa ưng không?", "meh"),
    ("Giá bao nhiêu, có giữ suất không?", "price"),
]


def fake_livestream(inp: LiveIn) -> LiveOut:
    n = max(1, len(inp.products))
    per = max(3, (inp.minutes - 8) // n)
    outline = [
        LiveSegment(
            segment="Chào và giới thiệu buổi live", minutes=3, notes="Nói hôm nay xem mấy món, ai hỏi gì cứ bình luận"
        ),
        *[
            LiveSegment(
                segment=f"Món {i + 1}: {p.name}",
                minutes=per,
                notes="Cầm lên tay, dùng thật trước máy, đọc câu hỏi của khách",
            )
            for i, p in enumerate(inp.products)
        ],
        LiveSegment(
            segment="Trả lời câu hỏi còn lại, chốt cách đặt", minutes=5, notes="Nhắc link đặt, hạn chót đợt nếu có"
        ),
    ]
    items = []
    faq: list[LiveFaq] = []
    for i, p in enumerate(inp.products):
        pts = [
            x
            for x in [
                _first_sentence(p.reason_selected),
                f"Đã dùng thử {_trial_text(p)}" if p.trial_days else None,
                ("Chưa ưng: " + _lower_first(_first_sentence(p.not_satisfied))) if p.not_satisfied else None,
            ]
            if x
        ]
        items.append(
            LiveItem(
                product_id=p.id,
                order=i + 1,
                name=p.name,
                talking_points=pts or ["Dùng thật trước máy"],
                demo=f"Dùng {p.name} như mọi ngày, quay cận bàn tay",
                price_note=f"Giá {vnd(p.price_vnd)}",
            )
        )
    for q in inp.questions[:6]:
        p = next((x for x in inp.products if x.id == q.product_id), None)
        ans = _answer(q.question, p)
        faq.append(LiveFaq(q=q.question, a=ans, product_id=q.product_id, source="khach_hoi"))
    for p in inp.products[:3]:
        for q, kind in GENERIC_Q[:2]:
            faq.append(LiveFaq(q=f"{p.name}: {q}", a=_answer_kind(kind, p), product_id=p.id, source="du_doan"))
    return LiveOut(outline=outline, items=items, faq=faq)


def _answer_kind(kind: str, p: ProductFacts) -> str:
    if kind == "trial":
        return f"Mình mới dùng {_trial_text(p)}, tới giờ vẫn ổn. Lâu hơn thì mình chưa biết, có gì mình báo thêm."
    if kind == "reason":
        return _first_sentence(p.reason_selected, "Mình thấy dùng tiện") + "."
    if kind == "meh":
        return (
            (_first_sentence(p.not_satisfied) + ".")
            if p.not_satisfied
            else "Mình chưa thấy điểm gì lớn, có gì mình nói thật."
        )
    return f"Giá {vnd(p.price_vnd)}. Bạn nhắn mình để giữ suất nhé."


def _answer(question: str, p: ProductFacts | None) -> str:
    if p is None:
        return "Câu này mình kiểm lại rồi trả lời bạn sau buổi live nhé."
    q = question.lower()
    if "giá" in q or "bao nhiêu tiền" in q:
        return _answer_kind("price", p)
    if "bao lâu" in q or "bền" in q:
        return _answer_kind("trial", p)
    if "chưa ưng" in q or "nhược" in q:
        return _answer_kind("meh", p)
    for s in p.specs:
        label = str(s.get("label", "")).lower()
        if label and label in q:
            return f"{s.get('label')}: {s.get('value')}."
    return "Câu này mình chưa có số liệu chắc chắn, mình kiểm lại rồi trả lời bạn nhé."
