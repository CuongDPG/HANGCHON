"""Phiên CSDL, lớp `Base` cho mọi model và các mixin/kiểu cột dùng chung."""

from __future__ import annotations

import enum
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, MetaData, String, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import settings
from app.core.enums import StrEnum
from app.core.timeutil import now_utc

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(AsyncAttrs, DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
        uuid.UUID: UUID(as_uuid=True),
        datetime: DateTime(timezone=True),
    }


# ---- mixin -------------------------------------------------------------------------------------------------------


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=func.now(), nullable=False
    )
    # onupdate chạy phía Python để giá trị có sẵn sau commit (không phải nạp lại trong async)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc, server_default=func.now(), nullable=False
    )


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=func.now(), nullable=False, index=True
    )


# ---- kiểu cột ----------------------------------------------------------------------------------------------------


def enum_col(enum_cls: type[enum.Enum], *, length: int = 40) -> SAEnum:
    """Cột Enum lưu **giá trị chữ thường** (values_callable) dưới dạng VARCHAR, không tạo kiểu enum của Postgres.

    VARCHAR giúp thêm giá trị mới không cần migration (chỉ cần đủ `length`)."""
    return SAEnum(
        enum_cls,
        values_callable=lambda e: [m.value for m in e],
        native_enum=False,
        create_constraint=False,
        length=length,
        validate_strings=True,
    )


Money = Annotated[int, mapped_column(BigInteger, nullable=False, default=0, server_default="0")]
MoneyOpt = Annotated[int | None, mapped_column(BigInteger, nullable=True)]
Str200 = Annotated[str, mapped_column(String(200))]


def money(**kw: Any) -> Any:
    """Tiền VND (số nguyên), mặc định 0."""
    return mapped_column(BigInteger, nullable=False, default=0, server_default="0", **kw)


def money_opt(**kw: Any) -> Any:
    return mapped_column(BigInteger, nullable=True, **kw)


def json_list(**kw: Any) -> Any:
    return mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"), **kw)


def json_obj(**kw: Any) -> Any:
    return mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"), **kw)


def flag(default: bool = False, **kw: Any) -> Any:
    return mapped_column(Boolean, nullable=False, default=default, server_default=text(str(default).lower()), **kw)


def count(**kw: Any) -> Any:
    """Số nguyên không âm, mặc định 0 (bộ đếm, số lượng)."""
    return mapped_column(Integer, nullable=False, default=0, server_default="0", **kw)


def fk(target: str, *, ondelete: str = "SET NULL", index: bool = True, use_alter: bool = False, **kw: Any) -> Any:
    """Khoá ngoại tới `<bảng>.id`. `ondelete="CASCADE"` cho bảng con, "SET NULL" cho liên kết tuỳ chọn.
    `use_alter=True` cho khoá «trỏ ngược» tạo vòng giữa các bảng (tạo bằng ALTER sau khi đủ bảng)."""
    return mapped_column(ForeignKey(f"{target}.id", ondelete=ondelete, use_alter=use_alter), index=index, **kw)


__all__ = [
    "Base",
    "CreatedAt",
    "DbSession",
    "Money",
    "MoneyOpt",
    "SessionLocal",
    "StrEnum",
    "Timestamps",
    "UUIDPk",
    "count",
    "enum_col",
    "fk",
    "flag",
    "get_db",
    "json_list",
    "json_obj",
    "money",
    "money_opt",
]


# ---- phiên -------------------------------------------------------------------------------------------------------

engine = create_async_engine(settings.database_url, echo=settings.database_echo, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


def configure_engine(url: str) -> None:
    """Đổi CSDL (dùng trong test)."""
    global engine
    engine = create_async_engine(url, pool_pre_ping=True)
    SessionLocal.configure(bind=engine)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Một phiên cho mỗi request: commit khi hàm xử lý xong không lỗi, rollback khi lỗi."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


# scope="function": commit chạy TRƯỚC khi gửi phản hồi, lỗi commit trả 500 thay vì mất dữ liệu âm thầm.
DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]
