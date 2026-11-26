"""Soát lời theo các lỗi thấy ở lần chạy AI thật đầu tiên (26/11, «hộp 100 chun buộc tóc trẻ em sợi dày»).

- Bài Instagram/Threads/TikTok/Zalo thiếu «Vì sao mình chọn món này» mà vẫn qua (luật của chị: mọi bài, mọi kênh).
- Bài tự thêm lời hứa «đóng thêm túi zip riêng cho bạn» trong khi hồ sơ chỉ ghi chị tự đóng túi zip lúc thử.
- Bài Facebook/Zalo bỏ mất cảnh báo hóc nuốt mà trang web có.
- `claims` của AI soát: giải thích ghi «khớp hồ sơ, không phải lỗi» mà vẫn đánh trượt (câu trả lời ghi lại bên dưới).
"""

from __future__ import annotations

from typing import Any

from app.core.enums import Channel
from app.modules.content.ai_io import CheckIssue, CheckOut, ProductFacts
from app.modules.content.checks import build_findings, can_approve, status_of
from app.modules.content.facts import customer_warnings

CHOKING = "Chun nhỏ, có thể gây nguy cơ hóc nuốt với trẻ nhỏ; nên để xa tầm tay trẻ nhỏ."


def _product(**kw: Any) -> ProductFacts:
    base = dict(
        id="p1",
        name="Hộp 100 chun buộc tóc trẻ em sợi dày",
        price_vnd=59000,
        reason_selected="Chun sợi dày nhưng mềm, buộc thử cho bé 5 tuổi tóc mỏng không thấy giật tóc.",
        not_satisfied="Hộp nhựa mỏng, nắp dễ bung nên mình đóng thêm túi zip riêng.",
        trial_notes=["Ngày 5: cho bé 6 tuổi tự buộc, bé tự xỏ được, không kêu đau."],
        safety_warnings=[CHOKING],
    )
    return ProductFacts(**{**base, **kw})


def _chips(channel: Channel, body: str, script: list[dict] | None = None, ai: CheckOut | None = None,
           product: ProductFacts | None = None) -> dict[str, dict]:  # fmt: skip
    items = build_findings(channel=channel, title="t", body=body, hashtags=[], script=script or [],
                           product=product or _product(), drop=None, ai_generated=True, ai=ai)  # fmt: skip
    return {f["key"]: f for f in items}


THREADS_REAL = (
    "Hộp 100 chun sợi dày này mềm đến mức bé 6 tuổi tự buộc mà không kêu đau. Có điều kéo căng gấp 4 lần thì 2 cái "
    "đứt, màu cũng hơi tối hơn ảnh. Nhà bạn bé có hay kêu đau khi buộc tóc không?"
)


def test_reason_section_required_on_every_product_post() -> None:
    chips = _chips(Channel.THREADS, THREADS_REAL + " Chun nhỏ, bạn để xa tầm tay bé nhỏ nhé.")
    assert not chips["reason"]["ok"] and "Vì sao mình chọn món này" in chips["reason"]["detail"]
    assert not can_approve(status_of(list(chips.values())))
    fixed = "Vì sao mình chọn món này: chun sợi dày mà mềm, buộc cho bé không thấy giật tóc. " + THREADS_REAL
    chips = _chips(Channel.THREADS, fixed + " Chun nhỏ, bạn để xa tầm tay bé nhỏ nhé.")
    assert chips["reason"]["ok"] and chips["process"]["ok"]
    assert can_approve(status_of(list(chips.values())))


def test_tiktok_reason_must_be_spoken() -> None:
    def scene(n: int, voice: str, screen: str = "") -> dict:
        return {"scene": n, "seconds": 6, "visual": "Bàn tay cầm chun", "voiceover": voice, "on_screen_text": screen}

    caption = "Hộp 100 chun sợi dày, mềm. Vì sao mình chọn món này? Xem video nhé. 59.000đ/hộp."
    only_text = [scene(1, "Chun buộc tóc cho bé đây.", "Vì sao mình chọn món này"), scene(2, "Giá 59.000 đồng."),
                 scene(3, "Chun nhỏ, bạn để xa tầm tay bé nhỏ."), scene(4, "Nhắn mình nhé.")]  # fmt: skip
    chips = _chips(Channel.TIKTOK, caption, only_text)
    assert not chips["reason"]["ok"] and "Lời thoại" in chips["reason"]["detail"]
    spoken = [scene(1, "Vì sao mình chọn món này? Chun sợi dày mà mềm, bé không kêu đau."), *only_text[1:]]
    assert _chips(Channel.TIKTOK, caption, spoken)["reason"]["ok"]


def test_drop_posts_and_posts_without_product_skip_reason_rule() -> None:
    items = build_findings(channel=Channel.ZALO_OA, title=None, body="Cả nhà ơi, mình mở đợt mới nhé, nhắn mình.",
                           hashtags=[], script=[], product=None, drop=None, ai_generated=True, ai=None)  # fmt: skip
    assert next(f for f in items if f["key"] == "reason")["ok"]


def test_promise_not_in_dossier_is_flagged() -> None:
    body = (
        "Vì sao mình chọn món này: chun mềm, không giật tóc. Hộp nhựa mỏng, nắp dễ bung nên mình đóng thêm túi zip "
        "riêng cho bạn. Chun nhỏ, bạn để xa tầm tay bé nhỏ nhé. Giá 59.000đ."
    )
    claims = _chips(Channel.FACEBOOK, body * 2)["claims"]
    assert not claims["ok"] and "đóng thêm túi zip riêng cho bạn" in claims["detail"]
    honest = body.replace("nên mình đóng thêm túi zip riêng cho bạn", "nên mình đã đóng riêng vào túi zip lúc thử")
    assert _chips(Channel.FACEBOOK, honest * 2)["claims"]["ok"]
    freeship = _chips(Channel.FACEBOOK, (honest + " Freeship toàn quốc!") * 2)["claims"]
    assert not freeship["ok"] and "freeship" in freeship["detail"]


def test_safety_warning_must_be_carried() -> None:
    body = "Vì sao mình chọn món này: chun mềm, bé 6 tuổi tự buộc không kêu đau. Giá 59.000đ, bạn nhắn mình nhé."
    chips = _chips(Channel.ZALO_OA, body)
    assert not chips["safety"]["ok"] and "hóc/nuốt" in chips["safety"]["detail"]
    ok = _chips(Channel.ZALO_OA, body + " Chun nhỏ, bạn để xa tầm tay bé nhỏ kẻo bé nuốt phải.")
    assert ok["safety"]["ok"]
    # hồ sơ không có cảnh báo → không đòi
    assert _chips(Channel.ZALO_OA, body, product=_product(safety_warnings=[]))["safety"]["ok"]


# Câu trả lời thật của content.check cho bài Zalo (26/11): verdict trượt nhưng chính lời giải thích nói không phải lỗi.
ZALO_RECORDED = CheckOut(
    claim_issues=[
        CheckIssue(
            quote="bé 6 tuổi tự buộc mà không kêu đau",
            detail="Hồ sơ ghi bé 6 tuổi tự xỏ, tự buộc được mà không kêu đau. Nội dung này khớp hồ sơ, không phải lỗi.",
        ),
        CheckIssue(
            quote="chun mềm",
            detail="Nhận xét mềm là cảm nhận khi dùng thử, nên nói rõ là cảm nhận.",
            severity="note",
            suggestion="Viết «mình thấy chun mềm».",
        ),
    ]
)
ZALO_BODY = (
    "Bạn ơi, mình mới có hộp 100 chun buộc tóc sợi dày cho bé, giá 59.000đ. Vì sao mình chọn món này: chun mềm, bé 6 "
    "tuổi tự buộc mà không kêu đau. Chun nhỏ, bạn để xa tầm tay bé nhỏ nhé. Cần thì nhắn mình."
)


def test_ai_claims_verdict_follows_its_own_reasoning() -> None:
    chips = _chips(Channel.ZALO_OA, ZALO_BODY, ai=ZALO_RECORDED)
    assert chips["claims"]["ok"], chips["claims"]
    assert "Góp ý" in chips["claims"]["detail"] and "chun mềm" in chips["claims"]["detail"]
    assert can_approve(status_of(list(chips.values())))
    real = CheckOut(
        claim_issues=[CheckIssue(quote="bé nào cũng thích", detail="Khái quát cho mọi bé, hồ sơ không có.")]
    )
    chips = _chips(Channel.ZALO_OA, ZALO_BODY, ai=real)
    assert not chips["claims"]["ok"] and "bé nào cũng thích" in chips["claims"]["detail"]


async def test_run_check_with_recorded_ai_response(fake_ai: dict) -> None:
    from app.modules.content.service import run_check

    seen: list[Any] = []

    def recorded(inp: Any) -> CheckOut:
        seen.append(inp)
        return ZALO_RECORDED

    fake_ai["content.check"] = recorded
    findings, status = await run_check(channel=Channel.ZALO_OA, title="t", body=ZALO_BODY, hashtags=[], script=[],
                                       pf=_product(), df=None, ai_generated=True)  # fmt: skip
    assert can_approve(status), findings
    # AI soát nhận cả ghi chú thử và cảnh báo an toàn (để không coi trải nghiệm thật là bịa)
    assert seen[0].product.trial_notes and seen[0].product.safety_warnings == [CHOKING]


def test_customer_warnings_from_safety_findings() -> None:
    safety = {
        "findings": [
            {"level": "warning", "text": "Chun nhỏ, có thể gây nguy cơ hóc nuốt với trẻ nhỏ."},
            {"level": "warning", "text": "Chưa rõ có thuộc diện chứng nhận hợp quy không, nên kiểm lại."},
            {"level": "info", "text": "Không có pin."},
        ]
    }
    assert customer_warnings(safety) == ["Chun nhỏ, có thể gây nguy cơ hóc nuốt với trẻ nhỏ."]
    assert customer_warnings({"customer_warnings": ["Để xa tầm tay trẻ."], **safety}) == ["Để xa tầm tay trẻ."]
    assert customer_warnings(None) == []


def test_livestream_faq_medical_answers_flagged_for_review() -> None:
    from app.modules.content.livestream import SKIP_INTENTS, needs_review
    from app.modules.inbox.models import Intent

    assert needs_review("Bé dùng xong da đầu đỏ, shop giải thích sao?", "Bạn hỏi bác sĩ giúp mình nhé.")
    assert not needs_review("Màu có giống ảnh không?", "Màu hơi tối hơn ảnh một chút.")
    assert Intent.COMPLAINT in SKIP_INTENTS and Intent.ASK_PRODUCT not in SKIP_INTENTS
