"""Migration: `alembic upgrade head` chạy được trên CSDL trống, kết quả khớp models, downgrade về trống được."""

from __future__ import annotations

import os
import subprocess
import sys

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import Base
from tests.conftest import API_DIR, PG_BASE, TEST_DB, drop_database, ensure_database

MIG_DB = f"{TEST_DB}_mig"


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "ALEMBIC_DATABASE_URL": f"{PG_BASE}/{MIG_DB}"}
    env.pop("VIRTUAL_ENV", None)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=API_DIR, env=env, capture_output=True, text=True, check=False
    )


def test_single_head_and_short_revision_ids() -> None:
    script = ScriptDirectory.from_config(Config(str(API_DIR / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, f"Nhiều head: {heads}"
    for rev in script.walk_revisions():
        assert len(rev.revision) <= 32, rev.revision


async def test_upgrade_matches_models_and_downgrades() -> None:
    await drop_database(MIG_DB)
    await ensure_database(MIG_DB)
    try:
        up = _alembic("upgrade", "head")
        assert up.returncode == 0, up.stderr
        engine = create_async_engine(f"{PG_BASE}/{MIG_DB}")
        try:
            async with engine.connect() as conn:
                diff = await conn.run_sync(lambda c: compare_metadata(MigrationContext.configure(c), Base.metadata))
                n_tables = (
                    await conn.execute(text("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"))
                ).scalar_one()
        finally:
            await engine.dispose()
        assert diff == [], f"Migration lệch models: {diff}"
        assert n_tables == len(Base.metadata.tables) + 1  # + alembic_version
        down = _alembic("downgrade", "base")
        assert down.returncode == 0, down.stderr
    finally:
        await drop_database(MIG_DB)
