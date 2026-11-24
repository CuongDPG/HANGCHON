from __future__ import annotations

from typing import Protocol

from app.ai.types import AIRequest, ProviderResponse


class Provider(Protocol):
    name: str

    async def complete(self, req: AIRequest) -> ProviderResponse: ...


_providers: dict[str, Provider] = {}


def get_provider(name: str) -> Provider:
    if name not in _providers:
        if name == "fake":
            from app.ai.providers.fake import FakeProvider

            _providers[name] = FakeProvider()
        elif name == "anthropic":
            from app.ai.providers.anthropic import AnthropicProvider

            _providers[name] = AnthropicProvider()
        else:
            raise ValueError(f"AI_PROVIDER không hợp lệ: {name}")
    return _providers[name]


def reset_providers() -> None:
    _providers.clear()
