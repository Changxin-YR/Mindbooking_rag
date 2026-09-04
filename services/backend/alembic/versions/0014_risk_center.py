"""Add login risk signals and durable watchlist history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_risk_center"
down_revision: str | None = "0013_admin_center"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


def upgrade() -> None:
    op.create_table(
        "login_risk_signals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("browser", sa.String(64), nullable=False),
        sa.Column("operating_system", sa.String(64), nullable=False),
        sa.Column("ip", sa.String(64), nullable=False),
        sa.Column("region", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.Text, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
    )
    op.create_table(
        "risk_watchlist_entries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_value", sa.String(256), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("release_reason", sa.Text, nullable=True),
        sa.Column("evidence_id", sa.String(64), nullable=True),
        _created_at(),
    )


def downgrade() -> None:
    op.drop_table("risk_watchlist_entries")
    op.drop_table("login_risk_signals")
