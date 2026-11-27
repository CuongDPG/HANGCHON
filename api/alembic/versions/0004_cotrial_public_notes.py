"""co-trial program («Mời thử cùng»: tester registry, per-item offers, paid trials + refunds) and public trial notes

Revision ID: 0004_cotrial_public_notes
Revises: 0003_review_choice_reason
Create Date: 2026-11-27 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_cotrial_public_notes"
down_revision: str | None = "0003_review_choice_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tester_profiles",
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column(
            "interests",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
            comment="Nhóm hàng quan tâm (slug danh mục)",
        ),
        sa.Column(
            "agreed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Lúc đồng ý điều kiện: mua giá thường, gửi cảm nhận đúng hạn",
        ),
        sa.Column(
            "excluded",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Lỡ hạn cảm nhận → không chọn ở lời mời sau (chị bỏ qua được)",
        ),
        sa.Column("excluded_reason", sa.String(length=300), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_tester_profiles_customer_id_customers"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tester_profiles")),
        sa.UniqueConstraint("customer_id", name=op.f("uq_tester_profiles_customer_id")),
    )
    op.create_table(
        "cotrial_offers",
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False, comment="Link riêng chị tự gửi (Zalo...)"),
        sa.Column(
            "status", sa.Enum("open", "closed", name="cotrialofferstatus", native_enum=False, length=40), nullable=False
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "photos",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
            comment='Bản sao công khai chị chọn (đã bỏ EXIF) [{"files": {...}}]',
        ),
        sa.Column("price_vnd", sa.BigInteger(), server_default="0", nullable=False, comment="Giá thường người thử trả"),
        sa.Column("refund_vnd", sa.BigInteger(), nullable=True, comment="Hoàn lại khi gửi cảm nhận đủ (số tiền)"),
        sa.Column("refund_pct", sa.SmallInteger(), nullable=True, comment="…hoặc theo % giá"),
        sa.Column(
            "ask_price_vnd",
            sa.BigInteger(),
            nullable=True,
            comment="Câu hỏi «Giá X bạn có mua không?» (trống = giá thường)",
        ),
        sa.Column("slots", sa.SmallInteger(), server_default="3", nullable=False),
        sa.Column("feedback_days", sa.SmallInteger(), server_default="10", nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_cotrial_offers_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_cotrial_offers_created_by_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cotrial_offers")),
        sa.UniqueConstraint("token", name=op.f("uq_cotrial_offers_token")),
    )
    op.create_index(op.f("ix_cotrial_offers_candidate_id"), "cotrial_offers", ["candidate_id"], unique=False)
    op.add_column("tester_invites", sa.Column("offer_id", sa.UUID(), nullable=True, comment="Null = lời mời h8 cũ"))
    op.add_column("tester_invites", sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tester_invites", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tester_invites",
        sa.Column("paid_vnd", sa.BigInteger(), nullable=True, comment="Chị xác nhận đã nhận (giá thường của lời mời)"),
    )
    op.add_column(
        "tester_invites",
        sa.Column(
            "feedback_due_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Hạn gửi cảm nhận = lúc gửi hàng + số ngày",
        ),
    )
    op.add_column("tester_invites", sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tester_invites",
        sa.Column(
            "feedback_answers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment='{"liked","disliked","would_buy","refund_account"} — chỉ ở desk, không ra website',
        ),
    )
    op.add_column("tester_invites", sa.Column("refund_vnd", sa.BigInteger(), nullable=True))
    op.add_column("tester_invites", sa.Column("refund_approval_id", sa.UUID(), nullable=True))
    op.add_column("tester_invites", sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_tester_invites_offer_id"), "tester_invites", ["offer_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_tester_invites_refund_approval_id_approval_items"),
        "tester_invites",
        "approval_items",
        ["refund_approval_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_tester_invites_offer_id_cotrial_offers"),
        "tester_invites",
        "cotrial_offers",
        ["offer_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column(
        "trial_notes",
        sa.Column(
            "is_public",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Chị tích «Đưa lên website»",
        ),
    )
    op.add_column(
        "trial_notes",
        sa.Column(
            "public_text", sa.Text(), nullable=True, comment="Lời hiện trên website (chị sửa được, khác lời gốc)"
        ),
    )
    op.add_column(
        "trial_notes",
        sa.Column(
            "public_photos",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
            comment='Ảnh chị tích kèm: bản sao công khai đã bỏ EXIF [{"files": {"800": {"webp","jpg"}}}]',
        ),
    )


def downgrade() -> None:
    op.drop_column("trial_notes", "public_photos")
    op.drop_column("trial_notes", "public_text")
    op.drop_column("trial_notes", "is_public")
    op.drop_constraint(op.f("fk_tester_invites_offer_id_cotrial_offers"), "tester_invites", type_="foreignkey")
    op.drop_constraint(
        op.f("fk_tester_invites_refund_approval_id_approval_items"), "tester_invites", type_="foreignkey"
    )
    op.drop_index(op.f("ix_tester_invites_offer_id"), table_name="tester_invites")
    op.drop_column("tester_invites", "refunded_at")
    op.drop_column("tester_invites", "refund_approval_id")
    op.drop_column("tester_invites", "refund_vnd")
    op.drop_column("tester_invites", "feedback_answers")
    op.drop_column("tester_invites", "reminded_at")
    op.drop_column("tester_invites", "feedback_due_at")
    op.drop_column("tester_invites", "paid_vnd")
    op.drop_column("tester_invites", "paid_at")
    op.drop_column("tester_invites", "selected_at")
    op.drop_column("tester_invites", "offer_id")
    op.drop_index(op.f("ix_cotrial_offers_candidate_id"), table_name="cotrial_offers")
    op.drop_table("cotrial_offers")
    op.drop_table("tester_profiles")
