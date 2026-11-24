"""Worker arq: `uv run arq app.worker.WorkerSettings`. Job và cron do module đăng ký (app.core.jobs)."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.core.discovery import discover_modules
from app.core.jobs import build_cron_jobs, build_functions, job_context, redis_settings
from app.core.timeutil import VN_TZ

discover_modules()
logging.basicConfig(level=settings.log_level)


async def startup(ctx: dict[str, Any]) -> None:
    ctx.update(job_context())


class WorkerSettings:
    functions = build_functions()
    cron_jobs = build_cron_jobs()
    redis_settings = redis_settings()
    on_startup = startup
    timezone = VN_TZ  # giờ trong @cron(...) là giờ Việt Nam
    max_jobs = 10
    job_timeout = 600
    keep_result = 3600
