"""review choice reason: «Vì sao bạn chọn món này?» on reviews + per-reason visibility

Revision ID: 0003_review_choice_reason
Revises: 0002_supplier_images
Create Date: 2026-11-27 10:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_review_choice_reason"
down_revision: str | None = "0002_supplier_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reviews",
        sa.Column(
            "choice_reason",
            sa.Text(),
            nullable=True,
            comment="«Vì sao bạn chọn món này?» (≤ 300 chữ, không bắt buộc)",
        ),
    )
    op.add_column(
        "reviews",
        sa.Column(
            "reason_public",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="Chị tắt để ẩn riêng lý do chọn mà vẫn hiện đánh giá",
        ),
    )


def downgrade() -> None:
    op.drop_column("reviews", "reason_public")
    op.drop_column("reviews", "choice_reason")
