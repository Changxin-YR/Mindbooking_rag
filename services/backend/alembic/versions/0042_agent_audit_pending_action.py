"""Persist the PendingAction reference on Agent audit events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_agent_audit_pending_action"
down_revision: str | None = "0041_agent_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_audit_events",
        sa.Column("pending_action_id", sa.String(128), nullable=True),
    )
    op.create_index(
        "ix_agent_audit_events_pending_action",
        "agent_audit_events",
        ["pending_action_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_audit_events_pending_action", table_name="agent_audit_events")
    op.drop_column("agent_audit_events", "pending_action_id")
