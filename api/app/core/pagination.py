"""Phân trang: `Paginated[T]` cho mọi endpoint danh sách."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Annotated, Any

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class Paginated[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int


class PageParams(BaseModel):
    page: int = 1
    size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def _page_params(
    page: Annotated[int, Query(ge=1, description="Trang, bắt đầu từ 1")] = 1,
    size: Annotated[int, Query(ge=1, le=200, description="Số dòng mỗi trang")] = 20,
) -> PageParams:
    return PageParams(page=page, size=size)


Page = Annotated[PageParams, Depends(_page_params)]


async def paginate[T](
    db: AsyncSession,
    stmt: Select[Any],
    params: PageParams,
    item: Callable[[Any], T] | type[T] | None = None,
    *,
    scalars: bool = True,
) -> Paginated[T]:
    """Chạy `stmt` có phân trang. `item` là schema Pydantic (dùng model_validate) hoặc hàm chuyển đổi."""
    total = (await db.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    result = await db.execute(stmt.limit(params.size).offset(params.offset))
    rows: Sequence[Any] = result.scalars().all() if scalars else result.all()
    if item is None:
        items = list(rows)
    elif isinstance(item, type) and issubclass(item, BaseModel):
        items = [item.model_validate(r) for r in rows]
    else:
        items = [item(r) for r in rows]  # type: ignore[operator]
    return Paginated[Any](
        items=items, total=total, page=params.page, size=params.size, pages=(total + params.size - 1) // params.size
    )
