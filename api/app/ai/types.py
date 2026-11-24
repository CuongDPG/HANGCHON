from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

Tier = Literal["smart", "fast"]


@dataclass
class AIImage:
    """Ảnh đính kèm: bytes (kèm media_type) hoặc URL công khai."""

    data: bytes | None = None
    media_type: str | None = None
    url: str | None = None

    @classmethod
    def coerce(cls, value: AIImage | bytes | str) -> AIImage:
        if isinstance(value, AIImage):
            return value
        if isinstance(value, bytes):
            return cls(data=value, media_type=sniff_media_type(value))
        return cls(url=value)


def sniff_media_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


@dataclass
class TaskSpec:
    """Khai báo một tác vụ AI: prompt hệ thống ổn định + mặc định tier/web."""

    name: str
    system: str = ""
    tier: Tier = "fast"
    web: bool = False
    max_tokens: int | None = None
    effort: str | None = None
    description: str = ""


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    web_search_requests: int = 0
    web_fetch_requests: int = 0
    # chi phí đã tính theo từng lượt (khi fallback chạy model khác); None = tính theo `model`
    per_model: list[tuple[str, int, int, int, int]] | None = None

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.web_search_requests += other.web_search_requests
        self.web_fetch_requests += other.web_fetch_requests
        if other.per_model:
            self.per_model = (self.per_model or []) + other.per_model


@dataclass
class AIRequest:
    task: str
    model: str
    tier: Tier
    system: str
    input_json: str
    input: BaseModel | dict[str, Any] | str
    output: type[BaseModel]
    images: list[AIImage] = field(default_factory=list)
    web: bool = False
    max_tokens: int = 16000
    effort: str | None = None


@dataclass
class ProviderResponse:
    output: BaseModel
    model: str
    usage: Usage
    stop_reason: str | None = None
    request_id: str | None = None
    sources: list[dict[str, str]] = field(default_factory=list)
    fallback_model: str | None = None


@dataclass
class AIResult[T: BaseModel]:
    output: T
    run_id: uuid.UUID
    model: str
    provider: str
    cost_vnd: int
    input_tokens: int
    output_tokens: int
    sources: list[dict[str, str]] = field(default_factory=list)
    fallback_model: str | None = None
