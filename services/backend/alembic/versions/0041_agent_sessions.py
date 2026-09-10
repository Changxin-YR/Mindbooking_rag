"""Persist Agent sessions and immutable conversation messages."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_agent_sessions"
down_revision: str | None = "0040_agent_pending_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255)),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("model_provider", sa.String(128), nullable=False, server_default="unknown"),
        sa.Column("context_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("context_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_agent_sessions_actor_updated", "actor_id", "updated_at"),
    )
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.Index("ix_agent_messages_session_created", "session_id", "created_at"),
    )


def downgrade() -> None:
    op.drop_table("agent_messages")
    op.drop_table("agent_sessions")
