"""Track payment credit repair attempts and terminal outcomes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_credit_pending_lifecycle"
down_revision: str | None = "0031_finance_maker_checker"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payment_credit_pending",
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column("payment_credit_pending", sa.Column("last_error", sa.Text))
    op.add_column(
        "payment_credit_pending", sa.Column("last_attempted_at", sa.DateTime(timezone=True))
    )
    op.add_column("payment_credit_pending", sa.Column("resolved_at", sa.DateTime(timezone=True)))
    op.add_column("payment_credit_pending", sa.Column("repair_actor_id", sa.String(64)))
    op.create_index(
        "ix_payment_credit_pending_status",
        "payment_credit_pending",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_payment_credit_pending_status", table_name="payment_credit_pending")
    op.drop_column("payment_credit_pending", "repair_actor_id")
    op.drop_column("payment_credit_pending", "resolved_at")
    op.drop_column("payment_credit_pending", "last_attempted_at")
    op.drop_column("payment_credit_pending", "last_error")
    op.drop_column("payment_credit_pending", "attempts")
