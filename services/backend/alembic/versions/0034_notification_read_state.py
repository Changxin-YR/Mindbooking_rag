"""Persist notification read timestamps."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_notification_read_state"
down_revision: str | None = "0033_payout_provider_transaction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("read_at", sa.DateTime(), nullable=True))
    op.create_index("ix_notifications_account_read", "notifications", ["account_id", "read_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_account_read", table_name="notifications")
    op.drop_column("notifications", "read_at")
