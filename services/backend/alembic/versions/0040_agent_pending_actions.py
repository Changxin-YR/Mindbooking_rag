"""Persist server-created Agent confirmation actions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_agent_pending_actions"
down_revision: str | None = "0039_reader_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_pending_actions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("arguments_snapshot", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("impact_summary", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Index("ix_agent_pending_actions_actor_status", "actor_id", "status"),
        sa.Index("ix_agent_pending_actions_expires", "expires_at"),
    )


def downgrade() -> None:
    op.drop_table("agent_pending_actions")
