"""Add withdrawal review facts and durable sandbox payout orders."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_payout_orders"
down_revision: str | None = "0025_membership_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "withdrawal_requests",
        sa.Column("risk_status", sa.String(24), nullable=False, server_default="PENDING"),
    )
    op.add_column(
        "withdrawal_requests",
        sa.Column("finance_status", sa.String(24), nullable=False, server_default="PENDING"),
    )
    op.add_column(
        "withdrawal_requests",
        sa.Column(
            "second_factor_verified",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "withdrawal_requests",
        sa.Column("payout_destination", sa.String(128), nullable=False, server_default=""),
    )
    op.create_table(
        "payout_orders",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("withdrawal_id", sa.String(64), nullable=False),
        sa.Column("payout_no", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("destination", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("provider_event_id", sa.String(128)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["withdrawal_id"], ["withdrawal_requests.id"]),
        sa.UniqueConstraint("withdrawal_id", name="uq_payout_orders_withdrawal"),
        sa.UniqueConstraint("payout_no", name="uq_payout_orders_payout_no"),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_payout_provider_event"),
        sa.CheckConstraint(
            "status IN ('PROCESSING', 'SUCCESS', 'FAILED', 'REJECTED', 'TIMEOUT')",
            name="ck_payout_order_status",
        ),
        sa.CheckConstraint("amount_cents > 0", name="ck_payout_order_amount"),
    )


def downgrade() -> None:
    op.drop_table("payout_orders")
    op.drop_column("withdrawal_requests", "payout_destination")
    op.drop_column("withdrawal_requests", "second_factor_verified")
    op.drop_column("withdrawal_requests", "finance_status")
    op.drop_column("withdrawal_requests", "risk_status")
