"""Add durable Outbox claim, retry, and publish state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_outbox_lifecycle"
down_revision: str | None = "0021_agent_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "outbox_events",
        sa.Column("status", sa.String(24), nullable=False, server_default=sa.text("'PENDING'")),
    )
    op.add_column("outbox_events", sa.Column("available_at", sa.DateTime(timezone=True)))
    op.add_column("outbox_events", sa.Column("locked_by", sa.String(128)))
    op.add_column("outbox_events", sa.Column("locked_at", sa.DateTime(timezone=True)))
    op.add_column("outbox_events", sa.Column("last_error", sa.Text))
    op.add_column("outbox_events", sa.Column("processed_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_outbox_events_delivery",
        "outbox_events",
        ["status", "available_at", "locked_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_delivery", table_name="outbox_events")
    for column in (
        "processed_at",
        "last_error",
        "locked_at",
        "locked_by",
        "available_at",
        "status",
    ):
        op.drop_column("outbox_events", column)
