"""Add request context and risk metadata to Agent audit events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_agent_audit_context"
down_revision: str | None = "0022_outbox_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_audit_events", sa.Column("session_id", sa.String(64)))
    op.add_column("agent_audit_events", sa.Column("arguments_json", sa.Text))
    op.add_column("agent_audit_events", sa.Column("result_summary", sa.String(255)))
    op.add_column("agent_audit_events", sa.Column("ip", sa.String(64)))
    op.add_column("agent_audit_events", sa.Column("device_id", sa.String(128)))
    op.add_column(
        "agent_audit_events",
        sa.Column("confirmed", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "agent_audit_events",
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="LOW"),
    )
    op.create_index(
        "ix_agent_audit_events_actor_time",
        "agent_audit_events",
        ["actor_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_audit_events_actor_time", table_name="agent_audit_events")
    for column in (
        "risk_level",
        "confirmed",
        "device_id",
        "ip",
        "result_summary",
        "arguments_json",
        "session_id",
    ):
        op.drop_column("agent_audit_events", column)
