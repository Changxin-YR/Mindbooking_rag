"""Persist copyright complaint evidence links."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_copyright_evidence"
down_revision: str | None = "0019_operation_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "copyright_complaint_evidence",
        sa.Column("complaint_id", sa.String(64), nullable=False),
        sa.Column("evidence_id", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("complaint_id", "evidence_id"),
        sa.ForeignKeyConstraint(["complaint_id"], ["copyright_complaints.id"]),
    )


def downgrade() -> None:
    op.drop_table("copyright_complaint_evidence")
