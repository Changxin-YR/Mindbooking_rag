"""Add moderation rules, quality, alerts, user views, and support CSAT facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_admin_center"
down_revision: str | None = "0012_author_center"
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
        "review_rules",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("recommended_action", sa.String(64), nullable=False),
        sa.Column("auto_block_policy", sa.Boolean, nullable=False),
        sa.Column("subject_types_json", sa.Text, nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("code", "version"),
    )
    op.create_table(
        "reviewer_quality_metrics",
        sa.Column("reviewer_id", sa.String(64), primary_key=True),
        sa.Column("accuracy_bps", sa.Integer, nullable=False),
        sa.Column("false_positive_bps", sa.Integer, nullable=False),
        sa.Column("miss_bps", sa.Integer, nullable=False),
        sa.Column("overturn_bps", sa.Integer, nullable=False),
        sa.Column("avg_handle_seconds", sa.Integer, nullable=False),
        sa.Column("complaint_bps", sa.Integer, nullable=False),
        _created_at(),
    )
    op.create_table(
        "author_alerts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("risk_level", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
    )
    op.create_table(
        "support_csat_records",
        sa.Column("ticket_id", sa.String(64), primary_key=True),
        sa.Column("score", sa.SmallInteger, nullable=False),
        _created_at(),
    )


def downgrade() -> None:
    for table in (
        "support_csat_records",
        "author_alerts",
        "reviewer_quality_metrics",
        "review_rules",
    ):
        op.drop_table(table)
