"""Persist provider payout transaction ids and reject cross-order reuse."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_payout_provider_transaction"
down_revision: str | None = "0032_credit_pending_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payout_orders",
        sa.Column("provider_transaction_id", sa.String(128), nullable=True),
    )
    op.create_unique_constraint(
        "uq_payout_provider_transaction",
        "payout_orders",
        ["provider", "provider_transaction_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_payout_provider_transaction", "payout_orders", type_="unique")
    op.drop_column("payout_orders", "provider_transaction_id")
