"""Provider Anthropic (SDK chính thức `anthropic` 2.x).

- Structured outputs qua `output_config.format` với khuôn `app.ai.schema.anthropic_schema()` (mọi thuộc tính required để
  khỏi vượt giới hạn độ phức tạp ngữ pháp), Pydantic kiểm lại theo model gốc; không temperature, không prefill, không ép
  tool_choice. Khuôn vượt ngân sách bị chặn trước khi gọi (`check_limits`), lỗi 400 không gửi lại.
- Thinking: Opus 5.5 / Haiku 5.5 luôn adaptive → không gửi `thinking`; độ sâu điều khiển bằng `output_config.effort`.
- web=True: bật server tools `web_search_20260209` + `web_fetch_20260209`; xử lý `pause_turn` bằng cách gửi lại lượt dở.
  Lưu ý: `user_location.country="VN"` bị API từ chối, chỉ gửi timezone.
- Từ chối (`stop_reason == "refusal"`): với model trong AI_FALLBACK_MODELS và AI_FALLBACKS="default", bật server-side
  fallbacks (beta `server-side-fallback-2026-07-01`); nếu cả chuỗi vẫn từ chối → AIRefused.
- Khoá lấy từ cấu hình chị lưu ở Cài đặt (CSDL, đã giải mã) hoặc ANTHROPIC_API_KEY — truyền vào qua `Connection`.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any

import anthropic
from pydantic import ValidationError

from app.ai.errors import AIError, AIOutputInvalid, AIRefused, AIUnavailable
from app.ai.providers import BaseProvider, Connection, register
from app.ai.schema import AISchemaTooComplex, anthropic_schema
from app.ai.types import AIRequest, ProviderResponse, Usage
from app.core.config import settings
from app.core.secrets import redact

log = logging.getLogger("app.ai.anthropic")

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_PAUSE_TURNS = 5

WEB_TOOLS: list[dict[str, Any]] = [
    {
        "type": "web_search_20260209",
        "name": "web_search",
        "user_location": {"type": "approximate", "timezone": "Asia/Ho_Chi_Minh"},
    },
    {"type": "web_fetch_20260209", "name": "web_fetch"},
]


def _image_block(img: Any) -> dict[str, Any]:
    if img.url:
        return {"type": "image", "source": {"type": "url", "url": img.url}}
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": img.media_type or "image/jpeg",
            "data": base64.standard_b64encode(img.data).decode(),
        },
    }


def _block_param(block: Any) -> dict[str, Any]:
    d = block.model_dump(mode="json", exclude_none=True)
    d.pop("parsed_output", None)
    return d


def _usage(resp: Any) -> Usage:
    u = resp.usage
    stu = getattr(u, "server_tool_use", None)
    usage = Usage(
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        web_search_requests=getattr(stu, "web_search_requests", 0) or 0 if stu else 0,
        web_fetch_requests=getattr(stu, "web_fetch_requests", 0) or 0 if stu else 0,
    )
    iterations = getattr(u, "iterations", None)
    if iterations:
        # mỗi lượt (kể cả lượt bị từ chối rồi chuyển model) tính theo giá của model đã chạy lượt đó
        usage.per_model = [
            (
                getattr(it, "model", None) or resp.model,
                getattr(it, "input_tokens", 0) or 0,
                getattr(it, "output_tokens", 0) or 0,
                getattr(it, "cache_read_input_tokens", 0) or 0,
                getattr(it, "cache_creation_input_tokens", 0) or 0,
            )
            for it in iterations
        ]
    return usage


def _sources(content: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for block in content:
        if getattr(block, "type", "") == "web_search_tool_result" and isinstance(block.content, list):
            out += [{"url": r.url, "title": getattr(r, "title", "") or ""} for r in block.content if hasattr(r, "url")]
        elif getattr(block, "type", "") == "web_fetch_tool_result":
            url = getattr(getattr(block, "content", None), "url", None)
            if url:
                out.append({"url": url, "title": ""})
    seen: set[str] = set()
    return [s for s in out if not (s["url"] in seen or seen.add(s["url"]))]


@register
class AnthropicProvider(BaseProvider):
    name = "anthropic"
    label = "Anthropic (Claude)"
    key_env = "anthropic_api_key"
    model_suggestions = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")
    key_placeholder = "sk-ant-…"

    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = None  # test gắn client giả vào đây
        self._clients: dict[str, anthropic.AsyncAnthropic] = {}

    def client_for(self, conn: Connection) -> anthropic.AsyncAnthropic:
        if self._client is not None:
            return self._client
        if not conn.api_key:
            raise AIUnavailable(
                "Chưa có khoá Anthropic: nhập khoá ở Cài đặt → AI và khoá API (hoặc đặt ANTHROPIC_API_KEY).",
                code="ai_no_key",
            )
        # một client cho mỗi khoá (đổi khoá ở Cài đặt → client mới); khoá băm để không giữ chuỗi rõ làm khoá dict
        ident = hashlib.sha256(f"{conn.api_key}|{conn.base_url or ''}".encode()).hexdigest()
        if ident not in self._clients:
            self._clients[ident] = anthropic.AsyncAnthropic(
                api_key=conn.api_key,
                base_url=conn.base_url or None,
                timeout=settings.ai_timeout_seconds,
                max_retries=settings.ai_max_retries,
            )
        return self._clients[ident]

    def _uses_fallbacks(self, model: str) -> bool:
        return settings.ai_fallbacks == "default" and model in settings.ai_fallback_models

    async def complete(self, req: AIRequest, conn: Connection) -> ProviderResponse:
        client = self.client_for(conn)
        content: list[dict[str, Any]] = [_image_block(i) for i in req.images]
        content.append({"type": "text", "text": req.input_json})
        messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
        kwargs: dict[str, Any] = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "system": [{"type": "text", "text": req.system, "cache_control": {"type": "ephemeral"}}],
        }
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": anthropic_schema(req.output)}}
        if req.effort:
            output_config["effort"] = req.effort
        kwargs["output_config"] = output_config
        if req.web:
            kwargs["tools"] = WEB_TOOLS
        fallbacks = self._uses_fallbacks(req.model)

        usage = Usage()
        all_content: list[Any] = []
        resp: Any = None
        try:
            for _ in range(MAX_PAUSE_TURNS + 1):
                if fallbacks:
                    resp = await client.beta.messages.create(
                        messages=messages, betas=[FALLBACK_BETA], fallbacks="default", **kwargs
                    )
                else:
                    resp = await client.messages.create(messages=messages, **kwargs)
                usage.add(_usage(resp))
                all_content += list(resp.content)
                if resp.stop_reason != "pause_turn":
                    break
                messages = [*messages, {"role": "assistant", "content": [_block_param(b) for b in resp.content]}]
        except anthropic.AuthenticationError as e:
            raise AIUnavailable("Khoá AI không hợp lệ hoặc đã hết hạn.", code="ai_auth") from e
        except anthropic.PermissionDeniedError as e:
            raise AIUnavailable("Khoá AI không có quyền dùng model hoặc tính năng này.", code="ai_permission") from e
        except anthropic.RateLimitError as e:
            raise AIUnavailable("AI đang quá tải lượt gọi, chị thử lại sau ít phút.", code="ai_rate_limited") from e
        except anthropic.NotFoundError as e:
            raise AIUnavailable(
                f"Không tìm thấy model «{req.model}» (sai tên, hoặc khoá không có quyền dùng model này).",
                code="ai_model_not_found",
            ) from e
        except anthropic.BadRequestError as e:
            detail = redact(str(e.message), conn.api_key)
            if "credit balance" in detail.lower():
                raise AIUnavailable(
                    "Tài khoản Anthropic hết hạn mức (credit), nạp thêm rồi thử lại.", code="ai_quota"
                ) from e
            log.error("Anthropic từ chối yêu cầu (%s): %s", req.task, detail)
            low = detail.lower()
            if "too complex" in low or "grammar compilation" in low:
                raise AISchemaTooComplex(
                    f"Khuôn kết quả {req.output.__name__} quá phức tạp, AI từ chối biên dịch (lỗi hệ thống)."
                ) from e
            raise AIError("Yêu cầu gửi AI không hợp lệ (lỗi hệ thống).", code="ai_bad_request") from e
        except anthropic.APIStatusError as e:
            raise AIUnavailable(code="ai_server_error") from e
        except anthropic.APIConnectionError as e:  # gồm cả APITimeoutError
            raise AIUnavailable("Không kết nối được dịch vụ AI.", code="ai_connection") from e

        fallback_model = None
        iterations = getattr(resp.usage, "iterations", None) or []
        if any(getattr(it, "type", "") == "fallback_message" for it in iterations):
            fallback_model = resp.model
        if resp.stop_reason == "refusal":
            details = getattr(resp, "stop_details", None)
            raise AIRefused(category=getattr(details, "category", None))
        if resp.stop_reason == "pause_turn":
            raise AIError("AI tra cứu web quá lâu chưa xong, chị thử lại.", code="ai_pause_limit")
        if resp.stop_reason == "max_tokens":
            raise AIOutputInvalid("AI trả lời bị cắt ngang vì quá dài.", code="ai_max_tokens")
        texts = [b.text for b in resp.content if getattr(b, "type", "") == "text" and getattr(b, "text", "")]
        if not texts:
            raise AIOutputInvalid()
        try:
            parsed = req.output.model_validate_json(texts[-1])
        except ValidationError as e:
            raise AIOutputInvalid() from e
        return ProviderResponse(
            output=parsed,
            model=resp.model,
            usage=usage,
            stop_reason=resp.stop_reason,
            request_id=getattr(resp, "_request_id", None),
            sources=_sources(all_content),
            fallback_model=fallback_model,
        )
