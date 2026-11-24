"""Fixture riêng của catalog: xoá bộ đếm giới hạn tần suất giữa các test."""

import pytest

from app.modules.assistant.service import reset_limits
from app.modules.catalog.ratelimit import reset


@pytest.fixture(autouse=True)
def _reset_limits():
    reset()
    reset_limits()
    yield
    reset()
    reset_limits()
