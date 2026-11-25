"""Provider OpenRouter với máy chủ giả (httpx.MockTransport) — không gọi mạng."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, Field

from app import ai
from app.ai.providers import Connection
from app.ai.providers.openrouter import OpenRouterProvider, strict_schema
from app.ai.types import AIImage, AIRequest
from app.core.config import settings

KEY = "sk-or-v1-unit-test-key-0000000000000000-ABCD"


class Item(BaseModel):
    name: str = Field(min_length=2)
    score: int = Field(ge=1, le=5)


class Out(BaseModel):
    title: str
    items: list[Item]
    note: str | None = None
    tags: dict[str, int] = Field(default_factory=dict)


def _req(**kw: Any) -> AIRequest:
    base: dict[str, Any] = dict(
        task="t", model="anthropic/claude-opus-5.5", tier="smart", system="S", input_json="<du_lieu>{}</du_lieu>",
        input={}, output=Out, images=[], web=False, max_tokens=1000, effort="high",
    )  # fmt: skip
    return AIRequest(**{**base, **kw})


def _provider(*responses: httpx.Response) -> tuple[OpenRouterProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return queue.pop(0)

    p = OpenRouterProvider(transport=httpx.MockTransport(handler))
    p.retry_delay = 0
    return p, seen


def _ok(content: Any, *, finish: str = "stop", **message: Any) -> httpx.Response:
    text = content if isinstance(content, str) else json.dumps(content)
    return httpx.Response(
        200,
        json={
            "id": "gen-1",
            "model": "anthropic/claude-opus-5.5",
            "choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": text, **message}}],
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 50,
                "prompt_tokens_details": {"cached_tokens": 300, "cache_write_tokens": 100},
                "server_tool_use_details": {"web_search_requests": 2},
                "cost": 0.0123,
            },
        },
    )


GOOD = {"title": "Bình", "items": [{"name": "ab", "score": 3}], "note": None, "tags": {}}


async def test_request_shape_structured_output_and_usage() -> None:
    p, seen = _provider(_ok(GOOD))
    img = AIImage(data=b"\x89PNG....", media_type="image/png")
    out = await p.complete(_req(images=[img, AIImage(url="https://x/y.jpg")]), Connection(api_key=KEY))
    assert isinstance(out.output, Out) and out.output.items[0].score == 3
    req = seen[0]
    assert str(req.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(req.content)
    rf = body["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True and rf["json_schema"]["name"] == "Out"
    assert body["provider"] == {"require_parameters": True}
    assert body["reasoning"] == {"effort": "high", "exclude": True} and body["max_tokens"] == 1000
    assert "plugins" not in body and "temperature" not in body
    assert body["messages"][0] == {"role": "system", "content": "S"}
    parts = body["messages"][1]["content"]
    assert parts[0]["type"] == "text"  # chữ trước ảnh (theo tài liệu)
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert parts[2]["image_url"]["url"] == "https://x/y.jpg"
    u = out.usage
    assert (u.input_tokens, u.cache_read_tokens, u.cache_write_tokens, u.output_tokens) == (600, 300, 100, 50)
    assert u.web_search_requests == 2 and u.reported_cost_usd == pytest.approx(0.0123)
    assert out.model == "anthropic/claude-opus-5.5" and out.request_id == "gen-1"


def test_strict_schema_from_pydantic() -> None:
    s = strict_schema(Out)
    assert s["additionalProperties"] is False and s["required"] == ["title", "items", "note", "tags"]
    item = s["$defs"]["Item"]
    assert item["additionalProperties"] is False and set(item["required"]) == {"name", "score"}
    assert "minimum" not in item["properties"]["score"] and "minimum=1" in item["properties"]["score"]["description"]
    assert s["properties"]["tags"]["additionalProperties"] == {"type": "integer"}  # dict giữ nguyên
    assert "default" not in json.dumps(s)


async def test_web_plugin_and_sources() -> None:
    ann = [{"type": "url_citation", "url_citation": {"url": "https://a.vn/x", "title": "A"}},
           {"type": "url_citation", "url_citation": {"url": "https://a.vn/x", "title": "A"}}]  # fmt: skip
    p, seen = _provider(_ok(GOOD, annotations=ann))
    out = await p.complete(_req(web=True), Connection(api_key=KEY, base_url="https://proxy.local/v1/"))
    body = json.loads(seen[0].content)
    assert body["plugins"] == [{"id": "web"}]
    assert str(seen[0].url) == "https://proxy.local/v1/chat/completions"
    assert out.sources == [{"url": "https://a.vn/x", "title": "A"}]


async def test_output_validation_fences_refusal_length() -> None:
    p, _ = _provider(_ok("```json\n" + json.dumps(GOOD) + "\n```"))
    assert (await p.complete(_req(), Connection(api_key=KEY))).output.title == "Bình"

    bad = {**GOOD, "items": [{"name": "a", "score": 9}]}  # vi phạm ràng buộc → Pydantic bắt
    for resp, exc, code in (
        (_ok(bad), ai.AIOutputInvalid, "ai_output_invalid"),
        (_ok("không phải JSON"), ai.AIOutputInvalid, "ai_output_invalid"),
        (_ok("", finish="length"), ai.AIOutputInvalid, "ai_max_tokens"),
        (_ok("", finish="content_filter"), ai.AIRefused, "ai_refused"),
        (_ok(None, refusal="Tôi không làm việc này"), ai.AIRefused, "ai_refused"),
    ):
        p, _ = _provider(resp)
        with pytest.raises(exc) as e:
            await p.complete(_req(), Connection(api_key=KEY))
        assert e.value.code == code


def _err(status: int, message: str = "x", **meta: Any) -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": status, "message": message, "metadata": meta or None}})


async def test_errors_map_to_vietnamese_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ai_max_retries", 0)
    cases = [
        (_err(401, "Invalid API key"), "ai_auth"),
        (_err(402, "Insufficient credits"), "ai_quota"),
        (_err(403, "Budget limit exceeded", limit_source="openrouter_key_limit"), "ai_quota"),
        (_err(403, "Forbidden"), "ai_permission"),
        (_err(404, "No endpoints found"), "ai_model_not_found"),
        (_err(408, "timeout"), "ai_timeout"),
        (_err(429, "rate limited"), "ai_rate_limited"),
        (_err(502, "provider down"), "ai_server_error"),
        (_err(400, f"bad param, key {KEY}"), "ai_bad_request"),
        # lỗi trong lúc sinh: HTTP 200 nhưng có `error` ở thân / ở choice
        (httpx.Response(200, json={"error": {"code": 502, "message": "upstream"}}), "ai_server_error"),
        (httpx.Response(200, json={"choices": [{"error": {"code": 429, "message": "slow"}}]}), "ai_rate_limited"),
        (httpx.Response(500, text="<html>oops</html>"), "ai_server_error"),
    ]
    for resp, code in cases:
        p, _ = _provider(resp)
        with pytest.raises(ai.AIError) as e:
            await p.complete(_req(), Connection(api_key=KEY))
        assert e.value.code == code, (resp.status_code, e.value.code)
        assert KEY not in e.value.message and not e.value.message.isascii()

    p, _ = _provider(_err(403, "flagged", reasons=["violence"]))
    with pytest.raises(ai.AIRefused):
        await p.complete(_req(), Connection(api_key=KEY))


async def test_retries_transient_errors_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ai_max_retries", 2)
    p, seen = _provider(_err(503, "no provider"), _err(429, "slow"), _ok(GOOD))
    assert (await p.complete(_req(), Connection(api_key=KEY))).output.title == "Bình"
    assert len(seen) == 3

    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=req)

    p = OpenRouterProvider(transport=httpx.MockTransport(boom))
    p.retry_delay = 0
    with pytest.raises(ai.AIUnavailable) as e:
        await p.complete(_req(), Connection(api_key=KEY))
    assert e.value.code == "ai_connection"


async def test_missing_key_is_unavailable() -> None:
    p, seen = _provider()
    with pytest.raises(ai.AIUnavailable) as e:
        await p.complete(_req(), Connection())
    assert e.value.code == "ai_no_key" and seen == []
