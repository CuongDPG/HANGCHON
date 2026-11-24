"""Alembic (async). Nạp mọi models qua app.core.discovery nên module mới tự có mặt khi autogenerate."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic.operations import ops
from sqlalchemy import ForeignKeyConstraint, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import settings
from app.core.db import Base
from app.core.discovery import load_all_models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

load_all_models()
target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", os.environ.get("ALEMBIC_DATABASE_URL") or settings.database_url)


def _split_use_alter_fks(_ctx: object, _rev: object, directives: list) -> None:
    """Alembic bỏ qua khoá ngoại `use_alter=True` nằm trong create_table → tách thành create_foreign_key chạy sau
    khi đủ bảng (và drop trước khi xoá bảng ở downgrade). Cần cho các khoá «trỏ ngược» tạo vòng giữa bảng."""
    script = directives[0]
    if script.upgrade_ops is None:
        return
    created, dropped = [], []
    for op_ in script.upgrade_ops.ops:
        if isinstance(op_, ops.CreateTableOp):
            keep = []
            for item in op_.columns:
                if isinstance(item, ForeignKeyConstraint) and item.use_alter:
                    referent = item.elements[0].target_fullname.rsplit(".", 1)[0]
                    remote_cols = [e.target_fullname.rsplit(".", 1)[1] for e in item.elements]
                    created.append(
                        ops.CreateForeignKeyOp(
                            item.name,
                            op_.table_name,
                            referent,
                            list(item.column_keys),
                            remote_cols,
                            ondelete=item.ondelete,
                        )
                    )
                    dropped.append(ops.DropConstraintOp(item.name, op_.table_name, type_="foreignkey"))
                else:
                    keep.append(item)
            op_.columns = keep
    script.upgrade_ops.ops.extend(created)
    if script.downgrade_ops is not None:
        script.downgrade_ops.ops[:0] = dropped


def _configure(**kw: object) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=False,
        process_revision_directives=_split_use_alter_fks,
        **kw,
    )


def run_migrations_offline() -> None:
    _configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
