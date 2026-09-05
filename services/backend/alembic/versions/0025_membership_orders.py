"""Add paid membership checkout facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_membership_orders"
down_revision: str | None = "0024_membership_commercial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "membership_plan_versions",
        sa.Column("price_cents", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
    )
    op.alter_column("membership_plan_versions", "price_cents", server_default=None)
    op.create_check_constraint(
        "ck_membership_plan_price_nonnegative",
        "membership_plan_versions",
        "price_cents >= 0",
    )
    op.create_table(
        "membership_orders",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("payment_order_id", sa.BigInteger(), nullable=False),
        sa.Column("payment_no", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("plan_code", sa.String(64), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_order_id"], ["payment_orders.id"]),
        sa.UniqueConstraint("payment_order_id", name="uq_membership_orders_payment"),
        sa.UniqueConstraint("payment_no", name="uq_membership_orders_payment_no"),
        sa.UniqueConstraint("idempotency_key", name="uq_membership_orders_idempotency"),
        sa.CheckConstraint("price_cents > 0", name="ck_membership_order_price_positive"),
    )
    op.create_index(
        "ix_membership_orders_account_created",
        "membership_orders",
        ["account_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_membership_orders_account_created", table_name="membership_orders")
    op.drop_table("membership_orders")
    op.drop_constraint(
        "ck_membership_plan_price_nonnegative", "membership_plan_versions", type_="check"
    )
    op.drop_column("membership_plan_versions", "price_cents")
