"""Add request correlation to append-only Agent audit events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_agent_request_id"
down_revision: str | None = "0036_contract_author_signature"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_audit_events", sa.Column("request_id", sa.String(128)))


def downgrade() -> None:
    op.drop_column("agent_audit_events", "request_id")
