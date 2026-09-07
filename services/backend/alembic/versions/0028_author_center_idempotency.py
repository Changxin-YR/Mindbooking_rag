"""Persist Writer task progress idempotency keys."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_author_center_idempotency"
down_revision: str | None = "0027_mfa_review_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "author_task_progress",
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    op.create_index(
        "uq_author_task_progress_idempotency",
        "author_task_progress",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_author_task_progress_idempotency", table_name="author_task_progress")
    op.drop_column("author_task_progress", "idempotency_key")
