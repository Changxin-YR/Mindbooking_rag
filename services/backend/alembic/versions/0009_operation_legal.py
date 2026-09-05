"""Add operation, rights, legal hold, export, job, and retention facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_operation_legal"
down_revision: str | None = "0008_author_finance"
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
        "ranking_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("score", sa.BigInteger, nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "kind IN ('ALGORITHM', 'RECOMMENDATION_SCORE', 'EDITORIAL', 'CAMPAIGN')",
            name="ck_ranking_kind",
        ),
    )
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("score", sa.BigInteger, nullable=False),
        sa.Column("personalized", sa.Boolean, nullable=False),
        _created_at(),
    )
    op.create_table(
        "operation_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
    )
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("requester_id", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
    )
    op.create_table(
        "retention_policies",
        sa.Column("resource_type", sa.String(64), primary_key=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("days", sa.Integer, nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "action IN ('DELETE', 'ANONYMIZE', 'ARCHIVE', 'KEEP', 'DOMAIN_CONTROLLED')",
            name="ck_retention_action",
        ),
        sa.CheckConstraint("days >= 0", name="ck_retention_days"),
    )
    op.create_table(
        "copyright_dossiers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), nullable=False),
        _created_at(),
    )
    op.create_table(
        "copyright_right_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("dossier_id", sa.String(64), nullable=False),
        sa.Column("region", sa.String(64), nullable=False),
        sa.Column("language", sa.String(32), nullable=False),
        sa.Column("media", sa.String(32), nullable=False),
        sa.Column("exclusive", sa.Boolean, nullable=False),
        sa.Column("start_year", sa.Integer, nullable=False),
        sa.Column("end_year", sa.Integer, nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["dossier_id"], ["copyright_dossiers.id"]),
        sa.CheckConstraint("end_year > start_year", name="ck_right_year_range"),
    )
    op.create_table(
        "copyright_complaints",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("claimant_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("counter_notice", sa.Text, nullable=True),
        _created_at(),
    )
    op.create_table(
        "legal_cases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
    )
    op.create_table(
        "legal_holds",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["case_id"], ["legal_cases.id"]),
        sa.CheckConstraint("status IN ('ACTIVE', 'RELEASED')", name="ck_legal_hold_status"),
    )


def downgrade() -> None:
    for table in (
        "legal_holds",
        "legal_cases",
        "copyright_complaints",
        "copyright_right_items",
        "copyright_dossiers",
        "retention_policies",
        "export_jobs",
        "operation_jobs",
        "recommendations",
        "ranking_items",
    ):
        op.drop_table(table)
