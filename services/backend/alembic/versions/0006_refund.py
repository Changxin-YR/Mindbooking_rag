"""Add reference-bound refund requests and immutable calculation snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_refund"
down_revision: str | None = "0005_wallet_commerce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refund_calculation_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("refund_reference", sa.String(128), nullable=False),
        sa.Column("payment_no", sa.String(64), nullable=False),
        sa.Column("recharge_no", sa.String(64), nullable=False),
        sa.Column("original_paid_cents", sa.BigInteger(), nullable=False),
        sa.Column("consumed_recharge_coin", sa.BigInteger(), nullable=False),
        sa.Column("consumed_promo_gift_coin", sa.BigInteger(), nullable=False),
        sa.Column("naturally_expired_promo_gift_coin", sa.BigInteger(), nullable=False),
        sa.Column("prior_refunded_cents", sa.BigInteger(), nullable=False),
        sa.Column("refundable_cents", sa.BigInteger(), nullable=False),
        sa.Column("recoverable_recharge_coin", sa.BigInteger(), nullable=False),
        sa.Column("recoverable_promo_gift_coin", sa.BigInteger(), nullable=False),
        sa.Column("executed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refund_reference", name="uq_refund_snapshot_reference"),
        sa.CheckConstraint("refundable_cents >= 0", name="ck_refund_snapshot_nonnegative"),
    )
    op.create_table(
        "refund_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("refund_no", sa.String(64), nullable=False),
        sa.Column("refund_reference", sa.String(128), nullable=False),
        sa.Column("payment_no", sa.String(64), nullable=False),
        sa.Column("recharge_no", sa.String(64), nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refund_no", name="uq_refund_request_no"),
        sa.UniqueConstraint("refund_reference", name="uq_refund_request_reference"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["refund_calculation_snapshots.id"]),
    )
    op.create_table(
        "refund_source_locks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("payment_no", sa.String(64), nullable=False),
        sa.Column("recharge_no", sa.String(64), nullable=False),
        sa.Column("refund_reference", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_no", "recharge_no", name="uq_refund_source_lock"),
    )


def downgrade() -> None:
    op.drop_table("refund_source_locks")
    op.drop_table("refund_requests")
    op.drop_table("refund_calculation_snapshots")
