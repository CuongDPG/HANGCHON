"""stop selling a product on every channel: per-post removal record on scheduled_posts

Revision ID: 0006_product_stop_selling
Revises: 0005_customer_login_codes
Create Date: 2026-11-27 20:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_product_stop_selling"
down_revision: str | None = "0005_customer_login_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scheduled_posts",
        sa.Column(
            "removal",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment='Ngừng bán: {"stop_id","outcome":"cancelled|hidden|deleted|manual|needs_manual|failed","error","at",'
            '"prev_status","restored_at","restore_error"}',
        ),
    )


def downgrade() -> None:
    op.drop_column("scheduled_posts", "removal")
