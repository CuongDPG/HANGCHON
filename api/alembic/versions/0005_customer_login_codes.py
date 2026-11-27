"""customer one-time login codes for the website («Của tôi» → my orders)

Revision ID: 0005_customer_login_codes
Revises: 0004_cotrial_public_notes
Create Date: 2026-11-27 18:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_customer_login_codes"
down_revision: str | None = "0004_cotrial_public_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_login_codes",
        sa.Column("contact_kind", sa.String(length=10), nullable=False, comment="phone | email"),
        sa.Column(
            "contact",
            sa.String(length=254),
            nullable=False,
            comment="SĐT chuẩn hoá 0xxxxxxxxx hoặc email chữ thường",
        ),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Đã dùng / bị thay bằng mã mới / sai quá số lần",
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_login_codes")),
    )
    op.create_index("ix_customer_login_codes_contact", "customer_login_codes", ["contact", "created_at"], unique=False)
    op.create_index(op.f("ix_customer_login_codes_created_at"), "customer_login_codes", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_customer_login_codes_created_at"), table_name="customer_login_codes")
    op.drop_index("ix_customer_login_codes_contact", table_name="customer_login_codes")
    op.drop_table("customer_login_codes")
