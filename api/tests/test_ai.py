from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Literal

import pytest
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import ai
from app.ai.pricing import estimate_cost
from app.ai.providers import Connection
from app.ai.providers.anthropic import WEB_TOOLS, AnthropicProvider
from app.ai.types import AIImage, AIRequest, Usage
from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.control.models import AIRun, AIRunStatus, ApprovalItem, ApprovalStatus


class Inp(BaseModel):
    text: str


class Item(BaseModel):
    name: str
    score: int = Field(ge=1, le=5)


class Out(BaseModel):
    title: str
    count: int = Field(ge=3)
    price: Decimal
    kind: Literal["a", "b"]
    items: list[Item]
    note: str | None


async def _runs() -> list[AIRun]:
    async with SessionLocal() as s:
        return list((await s.execute(select(AIRun).order_by(AIRun.created_at))).scalars())


async def test_default_fake_generates_valid_output() -> None:
    res = await ai.run("test.default", Inp(text="xin chào"), Out)
    assert isinstance(res.output, Out)
    assert res.output.count >= 3 and 1 <= res.output.items[0].score <= 5 and res.output.kind == "a"
    assert res.provider == "fake" and res.cost_vnd == 0
    runs = await _runs()
    assert len(runs) == 1 and runs[0].status == AIRunStatus.OK and runs[0].task == "test.default"
    assert runs[0].input_tokens > 0 and runs[0].output["title"]


async def test_registered_fake_and_task_spec(fake_ai: dict) -> None:
    ai.task("test.spec", system="Viết ngắn.", tier="smart")
    seen: list[str] = []

    @ai.fake("test.spec")
    async def _f(inp: Inp) -> dict[str, Any]:
        seen.append(inp.text)
        return {"title": inp.text.upper(), "count": 3, "price": "1.5", "kind": "b", "items": [], "note": None}

    res = await ai.run("test.spec", Inp(text="abc"), Out, images=[b"\x89PNG...."])
    assert res.output.title == "ABC" and seen == ["abc"]
    assert (await _runs())[0].tier == "smart"


async def test_fake_wrong_shape_is_output_invalid(fake_ai: dict) -> None:
    fake_ai["test.bad"] = lambda inp: {"title": "x"}
    with pytest.raises(ai.AIOutputInvalid):
        await ai.run("test.bad", Inp(text="x"), Out)
    assert (await _runs())[0].status == AIRunStatus.ERROR


async def test_fake_refusal(fake_ai: dict) -> None:
    def _refuse(inp: Inp) -> None:
        raise ai.FakeRefusal("bio")

    fake_ai["test.refuse"] = _refuse
    with pytest.raises(ai.AIRefused) as e:
        await ai.run("test.refuse", Inp(text="x"), Out)
    assert e.value.category == "bio" and e.value.status_code == 422
    run = (await _runs())[0]
    assert run.status == AIRunStatus.REFUSED and run.refusal_category == "bio"


def test_cost_estimate_uses_pricing_table() -> None:
    usage = Usage(input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=1_000_000, web_search_requests=10)
    usd, vnd = estimate_cost("claude-opus-5-5", usage)
    # 4 + 2 + 0.2 + 0.1 (web search) = 6.3 USD
    assert usd == Decimal("6.300000")
    assert vnd == 6.3 * settings.ai_usd_vnd_rate
    usd_h, _ = estimate_cost("claude-haiku-5-5-20261101", Usage(input_tokens=1_000_000))
    assert usd_h == Decimal("0.100000")
    # fallback: mỗi lượt tính theo model đã chạy lượt đó
    u = Usage(per_model=[("claude-opus-5-5", 1_000_000, 0, 0, 0), ("claude-opus-5", 1_000_000, 0, 0, 0)])
    assert estimate_cost("claude-opus-5", u)[0] == Decimal("9.000000")


async def test_budget_blocks_and_asks_owner() -> None:
    async with SessionLocal() as s:
        s.add(
            AIRun(
                task="x", provider="anthropic", model="claude-opus-5-5", tier="smart", status="ok", cost_vnd=2_000_000
            )
        )
        await s.commit()
    with pytest.raises(ai.AIBudgetExceeded):
        await ai.run("test.blocked", Inp(text="x"), Out)
    with pytest.raises(ai.AIBudgetExceeded):
        await ai.run("test.blocked", Inp(text="y"), Out)
    async with SessionLocal() as s:
        items = list((await s.execute(select(ApprovalItem))).scalars())
        blocked = list((await s.execute(select(AIRun).where(AIRun.status == AIRunStatus.BLOCKED))).scalars())
    # chỉ một việc chờ chị cho mỗi tháng (dedupe), mỗi lần bị chặn vẫn ghi ai_runs
    assert len(items) == 1 and items[0].action == "control.raise_ai_budget"
    assert items[0].status == ApprovalStatus.PENDING and items[0].payload["new_budget_vnd"] > 1_500_000
    assert len(blocked) == 2


# ---- provider anthropic với client giả (không gọi mạng) ---------------------------------------------------------


def _resp(stop_reason: str, parsed: Any = None, content: list | None = None, **usage: Any) -> SimpleNamespace:
    u = SimpleNamespace(
        input_tokens=usage.get("input_tokens", 100),
        output_tokens=usage.get("output_tokens", 50),
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
        server_tool_use=SimpleNamespace(web_search_requests=usage.get("web", 0), web_fetch_requests=0),
        iterations=usage.get("iterations"),
    )
    blocks = list(content or [])
    if parsed is not None:  # câu trả lời cuối: khối chữ JSON (structured outputs)
        blocks.append(SimpleNamespace(type="text", text=parsed.model_dump_json()))
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=blocks,
        usage=u,
        model=usage.get("model", "claude-opus-5-5"),
        stop_details=SimpleNamespace(category=usage.get("category")),
        _request_id="req_test",
    )


class _Messages:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kw: Any) -> SimpleNamespace:
        self.calls.append(kw)
        return self.responses.pop(0)


def _provider(responses: list[SimpleNamespace]) -> tuple[AnthropicProvider, _Messages]:
    p = AnthropicProvider()
    msgs = _Messages(responses)
    p._client = SimpleNamespace(messages=msgs, beta=SimpleNamespace(messages=msgs))  # type: ignore[assignment]
    return p, msgs


def _req(model: str = "claude-opus-5-5", web: bool = False) -> AIRequest:
    return AIRequest(
        task="t", model=model, tier="smart", system="S", input_json="<du_lieu>{}</du_lieu>", input={}, output=Inp,
        images=[AIImage(url="https://x/y.png")], web=web, max_tokens=1000, effort="medium",
    )  # fmt: skip


async def test_anthropic_request_shape_and_fallbacks() -> None:
    p, msgs = _provider([_resp("end_turn", Inp(text="ok"))])
    out = await p.complete(_req(), Connection())
    call = msgs.calls[0]
    assert out.output.text == "ok" and out.request_id == "req_test"
    assert call["output_config"]["effort"] == "medium" and "output_format" not in call
    schema = call["output_config"]["format"]["schema"]
    assert call["output_config"]["format"]["type"] == "json_schema" and schema["required"] == ["text"]
    assert schema["additionalProperties"] is False
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert "temperature" not in call and "thinking" not in call and "tool_choice" not in call
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert call["messages"][0]["content"][0]["source"]["type"] == "url"
    # model nhanh: không gửi fallbacks
    p2, msgs2 = _provider([_resp("end_turn", Inp(text="ok"), model="claude-haiku-5-5")])
    await p2.complete(_req(model="claude-haiku-5-5"), Connection())
    assert "fallbacks" not in msgs2.calls[0]


async def test_anthropic_web_pause_turn_and_sources() -> None:
    search = SimpleNamespace(
        type="web_search_tool_result", content=[SimpleNamespace(url="https://a.vn/x", title="A")],
        model_dump=lambda **_: {"type": "web_search_tool_result"},
    )  # fmt: skip
    p, msgs = _provider([_resp("pause_turn", None, [search], web=2), _resp("end_turn", Inp(text="xong"), web=1)])
    out = await p.complete(_req(web=True), Connection())
    assert len(msgs.calls) == 2 and msgs.calls[0]["tools"] == WEB_TOOLS
    assert "country" not in WEB_TOOLS[0]["user_location"]
    assert msgs.calls[1]["messages"][-1]["role"] == "assistant"
    assert out.usage.web_search_requests == 3 and out.sources == [{"url": "https://a.vn/x", "title": "A"}]


async def test_anthropic_refusal_and_fallback_detection() -> None:
    p, _ = _provider([_resp("refusal", None, category="cyber")])
    with pytest.raises(ai.AIRefused) as e:
        await p.complete(_req(), Connection())
    assert e.value.category == "cyber"

    its = [SimpleNamespace(type="message", model="claude-opus-5-5", input_tokens=10, output_tokens=0,
                           cache_read_input_tokens=0, cache_creation_input_tokens=0),
           SimpleNamespace(type="fallback_message", model="claude-opus-4-8", input_tokens=10, output_tokens=20,
                           cache_read_input_tokens=0, cache_creation_input_tokens=0)]  # fmt: skip
    p, _ = _provider([_resp("end_turn", Inp(text="ok"), model="claude-opus-4-8", iterations=its)])
    out = await p.complete(_req(), Connection())
    assert out.fallback_model == "claude-opus-4-8" and len(out.usage.per_model or []) == 2


async def test_anthropic_errors_map_to_vietnamese() -> None:
    import anthropic
    import httpx2

    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

    class _Boom:
        def __init__(self, exc: Exception) -> None:
            self.exc = exc

        async def create(self, **_: Any) -> None:
            raise self.exc

    cases = [
        (anthropic.RateLimitError("x", response=httpx2.Response(429, request=req), body=None), "ai_rate_limited"),
        (anthropic.AuthenticationError("x", response=httpx2.Response(401, request=req), body=None), "ai_auth"),
        (anthropic.InternalServerError("x", response=httpx2.Response(500, request=req), body=None), "ai_server_error"),
        (anthropic.APIConnectionError(request=req), "ai_connection"),
    ]
    for exc, code in cases:
        p = AnthropicProvider()
        p._client = SimpleNamespace(messages=_Boom(exc), beta=SimpleNamespace(messages=_Boom(exc)))  # type: ignore[assignment]
        with pytest.raises(ai.AIError) as e:
            await p.complete(_req(), Connection())
        assert e.value.code == code
        assert not e.value.message.isascii()  # thông báo tiếng Việt


async def test_anthropic_without_key_is_unavailable() -> None:
    with pytest.raises(ai.AIUnavailable):
        AnthropicProvider().client_for(Connection())


async def test_anthropic_schema_too_complex_fails_fast_without_retry() -> None:
    import anthropic
    import httpx2

    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    calls: list[int] = []

    class _Boom:
        async def create(self, **_: Any) -> None:
            calls.append(1)
            raise anthropic.BadRequestError(
                "Schema is too complex.", response=httpx2.Response(400, request=req), body=None
            )

    p = AnthropicProvider()
    p._client = SimpleNamespace(messages=_Boom(), beta=SimpleNamespace(messages=_Boom()))  # type: ignore[assignment]
    with pytest.raises(ai.AIError) as e:
        await p.complete(_req(), Connection())
    assert e.value.code == "ai_schema_too_complex" and len(calls) == 1


async def test_anthropic_last_text_block_is_parsed_and_bad_json_is_invalid() -> None:
    pre = SimpleNamespace(type="text", text="Mình tra cứu đã…")
    p, _ = _provider([_resp("end_turn", Inp(text="ok"), [pre])])
    assert (await p.complete(_req(), Connection())).output.text == "ok"
    p, _ = _provider([_resp("end_turn", None, [SimpleNamespace(type="text", text='{"khac": 1}')])])
    with pytest.raises(ai.AIOutputInvalid):
        await p.complete(_req(), Connection())


def test_anthropic_schema_marks_every_property_required() -> None:
    from app.ai.schema import anthropic_schema, model_complexity

    schema = anthropic_schema(Out)
    assert schema["required"] == list(schema["properties"])
    item = schema["$defs"]["Item"]
    assert item["required"] == ["name", "score"] and "minimum" not in item["properties"]["score"]
    c = model_complexity(Out)
    assert c.optional == 0 and c.unions == 2  # note: str | None, price: Decimal (number | string)


async def test_run_rejects_too_complex_schema_before_calling_provider() -> None:
    from pydantic import create_model

    Big = create_model("Big", **{f"f{i}": (int | None, None) for i in range(12)})  # 12 kiểu hợp > ngân sách
    with pytest.raises(ai.AIError) as e:
        await ai.run("test.big", Inp(text="x"), Big)
    assert e.value.code == "ai_schema_too_complex"
    runs = await _runs()
    assert runs[-1].error_code == "ai_schema_too_complex"
