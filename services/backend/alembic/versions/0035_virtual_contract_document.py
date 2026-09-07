"""Persist generated virtual contract documents for sandbox acceptance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_virtual_contract_document"
down_revision: str | None = "0034_notification_read_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contract_versions",
        sa.Column("document_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "contract_versions",
        sa.Column("document_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contract_versions", "document_hash")
    op.drop_column("contract_versions", "document_text")
