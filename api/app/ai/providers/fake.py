"""Provider giả: chạy hàm giả đã đăng ký cho tác vụ (`@ai.fake("...")`), không có thì sinh dữ liệu theo schema."""

from __future__ import annotations

import inspect

from pydantic import BaseModel

from app.ai.errors import AIOutputInvalid, AIRefused
from app.ai.fakegen import fake_output
from app.ai.registry import FAKES
from app.ai.types import AIRequest, ProviderResponse, Usage


class FakeRefusal(Exception):
    def __init__(self, category: str | None = None) -> None:
        self.category = category


class FakeProvider:
    name = "fake"

    async def complete(self, req: AIRequest) -> ProviderResponse:
        fn = FAKES.get(req.task)
        if fn is None:
            output: BaseModel = fake_output(req.output)
        else:
            try:
                result = fn(req.input)
                if inspect.isawaitable(result):
                    result = await result
            except FakeRefusal as e:
                raise AIRefused(category=e.category) from e
            if isinstance(result, BaseModel) and not isinstance(result, req.output):
                result = result.model_dump()  # cùng khuôn nhưng khác lớp (vd lớp khai báo lại ở nơi gọi)
            try:
                output = result if isinstance(result, req.output) else req.output.model_validate(result)
            except Exception as e:
                raise AIOutputInvalid(f"Hàm giả của «{req.task}» trả dữ liệu sai khuôn: {e}") from e
        text = output.model_dump_json()
        usage = Usage(
            input_tokens=max(1, (len(req.system) + len(req.input_json)) // 4),
            output_tokens=max(1, len(text) // 4),
        )
        return ProviderResponse(output=output, model="fake", usage=usage, stop_reason="end_turn")
