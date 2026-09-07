"""Persist the staff identities that approve risk and finance payout steps."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_finance_maker_checker"
down_revision: str | None = "0030_finance_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("withdrawal_requests", sa.Column("risk_reviewer_id", sa.String(64)))
    op.add_column("withdrawal_requests", sa.Column("finance_reviewer_id", sa.String(64)))
    op.create_index(
        "ix_withdrawal_requests_risk_reviewer",
        "withdrawal_requests",
        ["risk_reviewer_id"],
    )
    op.create_index(
        "ix_withdrawal_requests_finance_reviewer",
        "withdrawal_requests",
        ["finance_reviewer_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_withdrawal_requests_finance_reviewer", table_name="withdrawal_requests")
    op.drop_index("ix_withdrawal_requests_risk_reviewer", table_name="withdrawal_requests")
    op.drop_column("withdrawal_requests", "finance_reviewer_id")
    op.drop_column("withdrawal_requests", "risk_reviewer_id")
