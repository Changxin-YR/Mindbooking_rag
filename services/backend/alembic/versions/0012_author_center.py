"""Add author calendar, tasks, learning, funnel, and appeal facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_author_center"
down_revision: str | None = "0011_governance"
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
        "author_daily_writing_stats",
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("business_date", sa.Date, nullable=False),
        sa.Column("words", sa.BigInteger, nullable=False),
        sa.Column("goal", sa.BigInteger, nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("author_id", "business_date"),
    )
    op.create_table(
        "author_task_definitions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("target", sa.BigInteger, nullable=False),
        _created_at(),
        sa.UniqueConstraint("code", name="uq_author_task_code"),
    )
    op.create_table(
        "author_task_progress",
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("progress", sa.BigInteger, nullable=False),
        sa.Column("claimed", sa.Boolean, nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("author_id", "task_id"),
    )
    op.create_table(
        "writer_learning_contents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        _created_at(),
    )
    op.create_table(
        "writer_learning_progress",
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=False),
        sa.Column("percent", sa.SmallInteger, nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("author_id", "content_id"),
    )
    op.create_table(
        "chapter_funnel_metrics",
        sa.Column("chapter_id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("entrants", sa.BigInteger, nullable=False),
        sa.Column("completion_bps", sa.Integer, nullable=False),
        sa.Column("next_chapter_bps", sa.Integer, nullable=False),
        sa.Column("subscription_bps", sa.Integer, nullable=False),
        _created_at(),
    )
    op.create_table(
        "author_appeals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
    )
    op.create_table(
        "invoice_requests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("tax_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("document_id", sa.String(128), nullable=True),
        sa.Column("reversal_document_id", sa.String(128), nullable=True),
        _created_at(),
    )


def downgrade() -> None:
    for table in (
        "invoice_requests",
        "author_appeals",
        "chapter_funnel_metrics",
        "writer_learning_progress",
        "writer_learning_contents",
        "author_task_progress",
        "author_task_definitions",
        "author_daily_writing_stats",
    ):
        op.drop_table(table)
