"""Persist wallet lot source references and issued amounts for refund tracing."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_wallet_lot_sources"
down_revision: str | None = "0015_auth_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("wallet_asset_lots", sa.Column("source_ref", sa.String(128), nullable=True))
    op.add_column("wallet_asset_lots", sa.Column("issued_amount", sa.BigInteger(), nullable=True))
    op.execute(
        "UPDATE wallet_asset_lots SET issued_amount = available_amount WHERE issued_amount IS NULL"
    )
    op.create_index(
        "ix_wallet_asset_lots_source_ref", "wallet_asset_lots", ["account_id", "source_ref"]
    )


def downgrade() -> None:
    op.drop_index("ix_wallet_asset_lots_source_ref", table_name="wallet_asset_lots")
    op.drop_column("wallet_asset_lots", "issued_amount")
    op.drop_column("wallet_asset_lots", "source_ref")
