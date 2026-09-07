"""Persist reader display preferences per account."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_reader_preferences"
down_revision: str | None = "0038_account_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reading_preferences",
        sa.Column("account_id", sa.String(36), primary_key=True),
        sa.Column("preferences_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["platform_accounts.id"]),
    )


def downgrade() -> None:
    op.drop_table("reading_preferences")
