"""Persist the author's electronic signature for sandbox contracts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_contract_author_signature"
down_revision: str | None = "0035_virtual_contract_document"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("contracts", sa.Column("signed_by", sa.String(64), nullable=True))
    op.add_column("contracts", sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contracts", sa.Column("signature_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("contracts", "signature_hash")
    op.drop_column("contracts", "signed_at")
    op.drop_column("contracts", "signed_by")
