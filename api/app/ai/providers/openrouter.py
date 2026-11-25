"""Provider OpenRouter: API Chat Completions tương thích OpenAI, gọi REST bằng httpx (không dùng SDK OpenAI).

Viết theo tài liệu OpenRouter (tra 25/11/2026):
- `POST {base_url}/chat/completions`, `Authorization: Bearer <khoá>` (api_reference/authentication, overview).
- Structured outputs: `response_format = {"type": "json_schema", "json_schema": {"name", "strict": true, "schema"}}`;
  `provider.require_parameters = true` để chỉ định tuyến tới endpoint hỗ trợ (guides/features/structured-outputs).
  Schema lấy từ Pydantic (`model_json_schema`), chỉnh cho chế độ strict; kết quả vẫn được Pydantic kiểm lại.
- Ảnh: phần nội dung `{"type": "image_url", "image_url": {"url": <URL hoặc data URL>}}`, chữ đặt trước ảnh
  (api-reference ChatContentImage, multimodal/image-understanding).
- Effort: `reasoning = {"effort": low|medium|high|max…, "exclude": true}` (best-practices/reasoning-tokens).
- Tra cứu web: plugin `{"id": "web"}` (guides/features/plugins/web-search); nguồn ở `message.annotations[].url_citation`.
- Chi phí: `usage.cost` (credit; giới hạn tính bằng USD) + `usage.prompt_tokens_details.cached_tokens` /
  `cache_write_tokens`, `usage.server_tool_use_details.web_search_requests` (cookbook/usage-accounting).
- Lỗi: `{"error": {"code", "message", "metadata"}}`; 400/401/402/403/408/429/502/503; lỗi trong lúc sinh có thể nằm
  ở thân phản hồi 200 (`error` hoặc `choices[0].error`) (api_reference/errors-and-debugging).
"""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.errors import AIError, AIOutputInvalid, AIRefused, AIUnavailable
from app.ai.providers import BaseProvider, Connection, register
from app.ai.types import AIImage, AIRequest, ProviderResponse, Usage
from app.core.config import settings
from app.core.secrets import redact

log = logging.getLogger("app.ai.openrouter")

# Từ khoá JSON Schema mà chế độ strict của nhiều nhà cung cấp không nhận → chuyển thành lời mô tả (Pydantic vẫn kiểm).
_CONSTRAINTS = (
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
    "format",
)
_SCHEMA_LISTS = ("anyOf", "oneOf", "allOf", "prefixItems")
_SCHEMA_MAPS = ("properties", "$defs", "definitions")
_RETRY_STATUSES = {429, 502, 503}


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema của Pydantic model, chỉnh cho strict: object đóng (`additionalProperties: false`), mọi thuộc tính
    đều required (trường tuỳ chọn vẫn nhận null), ràng buộc số/độ dài chuyển vào description, bỏ `default`/`title`."""
    schema = copy.deepcopy(model.model_json_schema())

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        notes = [f"{k}={node.pop(k)}" for k in _CONSTRAINTS if k in node]
        node.pop("default", None)
        node.pop("title", None)
        if notes:
            node["description"] = f"{node.get('description', '')} ({', '.join(notes)})".strip()
        if "properties" in node:  # object có khuôn; dict[str, X] (additionalProperties = schema) giữ nguyên
            node["additionalProperties"] = False
            node["required"] = list(node.get("properties", {}))
        for key in _SCHEMA_MAPS:
            for child in (node.get(key) or {}).values():
                walk(child)
        for key in _SCHEMA_LISTS:
            for child in node.get(key) or []:
                walk(child)
        if isinstance(node.get("items"), dict):
            walk(node["items"])

    walk(schema)
    return schema


def _schema_name(model: type[BaseModel]) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", model.__name__)[:64] or "output"


def _image_part(img: AIImage) -> dict[str, Any]:
    if img.url:
        url = img.url
    else:
        url = f"data:{img.media_type or 'image/jpeg'};base64,{base64.standard_b64encode(img.data or b'').decode()}"
    return {"type": "image_url", "image_url": {"url": url}}


def _usage(data: dict[str, Any]) -> Usage:
    u = data.get("usage") or {}
    pd = u.get("prompt_tokens_details") or {}
    cached, written = int(pd.get("cached_tokens") or 0), int(pd.get("cache_write_tokens") or 0)
    prompt = int(u.get("prompt_tokens") or 0)
    tools = u.get("server_tool_use_details") or {}
    cost = u.get("cost")
    return Usage(
        input_tokens=max(prompt - cached - written, 0),  # cùng nghĩa với Anthropic: phần input chưa cache
        output_tokens=int(u.get("completion_tokens") or 0),
        cache_read_tokens=cached,
        cache_write_tokens=written,
        web_search_requests=int(tools.get("web_search_requests") or 0),
        reported_cost_usd=float(cost) if isinstance(cost, int | float) else None,
    )


def _sources(message: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for a in message.get("annotations") or []:
        c = a.get("url_citation") if isinstance(a, dict) else None
        if c and c.get("url") and c["url"] not in seen:
            seen.add(c["url"])
            out.append({"url": c["url"], "title": c.get("title") or ""})
    return out


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t


def _error(status: int, err: dict[str, Any], model: str, key: str | None) -> AIError:
    """Lỗi OpenRouter → câu tiếng Việt dễ hiểu (không bao giờ chứa khoá)."""
    detail = redact(str(err.get("message") or "")[:300], key)
    meta = err.get("metadata") if isinstance(err.get("metadata"), dict) else {}
    if status == 401:
        return AIUnavailable("Khoá OpenRouter không hợp lệ, đã bị tắt hoặc hết hạn.", code="ai_auth")
    if status == 402:
        return AIUnavailable(
            "Tài khoản OpenRouter không đủ credit (hoặc khoá đã chạm hạn mức chi). Nạp thêm rồi thử lại.",
            code="ai_quota",
        )
    if status == 403:
        if meta.get("limit_source"):
            return AIUnavailable(f"Khoá OpenRouter đã chạm hạn mức chi tiêu: {detail}", code="ai_quota")
        if meta.get("reasons") or "moderation" in detail.lower() or "flagged" in detail.lower():
            return AIRefused("Nội dung bị bộ lọc của nhà cung cấp chặn.", category="moderation")
        return AIUnavailable(
            f"Khoá không có quyền dùng model «{model}» hoặc bị chặn ({detail or 'không rõ lý do'}).",
            code="ai_permission",
        )
    if status == 404 or (status == 400 and "model" in detail.lower() and "valid" in detail.lower()):
        return AIUnavailable(
            f"Không dùng được model «{model}»: sai tên, khoá không có quyền, hoặc model không hỗ trợ trả JSON theo "
            f"khuôn ({detail or 'không tìm thấy'}).",
            code="ai_model_not_found",
        )
    if status == 408:
        return AIUnavailable("AI trả lời quá lâu (hết thời gian chờ), chị thử lại.", code="ai_timeout")
    if status == 429:
        return AIUnavailable("AI đang quá tải lượt gọi, chị thử lại sau ít phút.", code="ai_rate_limited")
    if status == 400:
        log.error("OpenRouter từ chối yêu cầu: %s", detail)
        return AIError(f"Yêu cầu gửi AI không hợp lệ: {detail}", code="ai_bad_request")
    if status in (502, 503):
        return AIUnavailable(
            "Model đang lỗi hoặc không có nhà cung cấp nào phục vụ được yêu cầu này, chị thử lại sau.",
            code="ai_server_error",
        )
    return AIUnavailable(code="ai_server_error")


@register
class OpenRouterProvider(BaseProvider):
    name = "openrouter"
    label = "OpenRouter"
    key_env = "openrouter_api_key"
    base_url_env = "openrouter_base_url"
    key_placeholder = "sk-or-…"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport  # test gắn httpx.MockTransport vào đây
        self.retry_delay = 1.0

    def _body(self, req: AIRequest) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": req.input_json}]
        content += [_image_part(i) for i in req.images]
        body: dict[str, Any] = {
            "model": req.model,
            "messages": [{"role": "system", "content": req.system}, {"role": "user", "content": content}],
            "max_tokens": req.max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": _schema_name(req.output), "strict": True, "schema": strict_schema(req.output)},
            },
            "provider": {"require_parameters": True},
        }
        if req.effort:
            body["reasoning"] = {"effort": req.effort, "exclude": True}
        if req.web:
            body["plugins"] = [{"id": "web"}]
        return body

    async def _post(self, conn: Connection, body: dict[str, Any]) -> httpx.Response:
        base_url = (conn.base_url or settings.openrouter_base_url).rstrip("/")
        headers = {"Authorization": f"Bearer {conn.api_key}"}
        async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds, transport=self.transport) as client:
            for attempt in range(settings.ai_max_retries + 1):
                last = attempt == settings.ai_max_retries
                try:
                    r = await client.post(f"{base_url}/chat/completions", json=body, headers=headers)
                except httpx.TimeoutException as e:
                    if last:
                        raise AIUnavailable("AI trả lời quá lâu (hết thời gian chờ).", code="ai_timeout") from e
                except httpx.TransportError as e:
                    if last:
                        raise AIUnavailable("Không kết nối được dịch vụ AI.", code="ai_connection") from e
                else:
                    if r.status_code not in _RETRY_STATUSES or last:
                        return r
                    retry_after = r.headers.get("retry-after", "")
                    if retry_after.isdigit():
                        await asyncio.sleep(min(int(retry_after), 20))
                        continue
                await asyncio.sleep(self.retry_delay * 2**attempt)
        raise AssertionError("unreachable")

    async def complete(self, req: AIRequest, conn: Connection) -> ProviderResponse:
        if not conn.api_key:
            raise AIUnavailable(
                "Chưa có khoá OpenRouter: nhập khoá ở Cài đặt → AI và khoá API (hoặc đặt OPENROUTER_API_KEY).",
                code="ai_no_key",
            )
        r = await self._post(conn, self._body(req))
        try:
            data = r.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if r.status_code != 200:
            raise _error(r.status_code, data.get("error") or {}, req.model, conn.api_key)
        choice = (data.get("choices") or [{}])[0]
        err = data.get("error") or choice.get("error")
        if err:
            raise _error(int(err.get("code") or 502), err, req.model, conn.api_key)
        message = choice.get("message") or {}
        finish = choice.get("finish_reason")
        if message.get("refusal") or finish == "content_filter":
            raise AIRefused(category="content_filter" if finish == "content_filter" else None)
        if finish == "length":
            raise AIOutputInvalid("AI trả lời bị cắt ngang vì quá dài.", code="ai_max_tokens")
        text = message.get("content")
        if isinstance(text, list):  # một số model trả mảng phần nội dung
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        if not text:
            raise AIOutputInvalid()
        try:
            output = req.output.model_validate(json.loads(_strip_fences(text)))
        except (ValueError, ValidationError) as e:
            raise AIOutputInvalid() from e
        return ProviderResponse(
            output=output,
            model=str(data.get("model") or req.model),
            usage=_usage(data),
            stop_reason=finish,
            request_id=data.get("id"),
            sources=_sources(message),
        )
