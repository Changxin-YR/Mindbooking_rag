"""Persist Agent tool audit events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_agent_audit"
down_revision: str | None = "0020_copyright_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_audit_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("permission", sa.String(128), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agent_audit_events")
