"""supplier images: cached candidate images + supplier origin on product images

Revision ID: 0002_supplier_images
Revises: 0001_initial
Create Date: 2026-11-26 10:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_supplier_images"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column(
            "image_cache",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
            comment='Bản sao ảnh nguồn trong kho riêng (chỉ desk): [{"url","key","type","bytes","at"} | {"url","error","at"}]',
        ),
    )
    op.add_column(
        "product_images",
        sa.Column(
            "source_url",
            sa.Text(),
            nullable=True,
            comment="kind=supplier: link ảnh gốc của nhà cung cấp (chỉ desk, không ra website)",
        ),
    )


def downgrade() -> None:
    op.drop_column("product_images", "source_url")
    op.drop_column("candidates", "image_cache")
