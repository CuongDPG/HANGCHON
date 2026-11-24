"""Việc nền (arq). Module khai báo trong `app/modules/<ten>/jobs.py`:

    from app.core.jobs import job, cron

    @job("sourcing.scan_brief")
    async def scan_brief(ctx, brief_id: str) -> None: ...

    @cron("sourcing.weekly_rescan", weekday="mon", hour={6}, minute={0})   # giờ Việt Nam
    async def weekly_rescan(ctx) -> None: ...

Gọi: `await enqueue("sourcing.scan_brief", brief_id=str(b.id))`. `ctx["db"]` là hàm mở phiên CSDL mới.
Khi `JOBS_EAGER=true` (test), `enqueue` chạy hàm ngay trong tiến trình.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.cron import CronJob
from arq.cron import cron as arq_cron
from arq.worker import func as arq_func

from app.core.config import settings

log = logging.getLogger("app.jobs")

JobFn = Callable[..., Awaitable[Any]]


@dataclass
class CronSpec:
    name: str
    fn: JobFn
    kwargs: dict[str, Any] = field(default_factory=dict)


JOBS: dict[str, JobFn] = {}
CRONS: dict[str, CronSpec] = {}


def job(name: str) -> Callable[[JobFn], JobFn]:
    def deco(fn: JobFn) -> JobFn:
        if name in JOBS and JOBS[name] is not fn:
            raise ValueError(f"Job trùng tên: {name}")
        JOBS[name] = fn
        return fn

    return deco


def cron(name: str, **schedule: Any) -> Callable[[JobFn], JobFn]:
    """`schedule` là tham số của `arq.cron.cron` (month, day, weekday, hour, minute, second, run_at_startup...)."""

    def deco(fn: JobFn) -> JobFn:
        job(name)(fn)
        CRONS[name] = CronSpec(name=name, fn=fn, kwargs=schedule)
        return fn

    return deco


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


def build_functions() -> list[Any]:
    return [arq_func(fn, name=name) for name, fn in JOBS.items() if name not in CRONS]


def build_cron_jobs() -> list[CronJob]:
    return [arq_cron(spec.fn, name=spec.name, **spec.kwargs) for spec in CRONS.values()]


_pool: ArqRedis | None = None


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


def job_context() -> dict[str, Any]:
    from app.core.db import SessionLocal

    return {"db": SessionLocal}


async def enqueue(name: str, *, _defer_by: float | None = None, _job_id: str | None = None, **kwargs: Any) -> Any:
    if name not in JOBS:
        raise KeyError(f"Chưa đăng ký job: {name}")
    if settings.jobs_eager:
        return await JOBS[name](job_context(), **kwargs)
    pool = await get_pool()
    return await pool.enqueue_job(name, _defer_by=_defer_by, _job_id=_job_id, **kwargs)
