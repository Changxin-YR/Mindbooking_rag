"""Add author contracts, revenue, settlements, withdrawals, and chargebacks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_author_finance"
down_revision: str | None = "0007_governance"
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
        "contracts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'APPROVED', 'ACTIVE', 'TERMINATED')", name="ck_contract_status"
        ),
    )
    op.create_table(
        "contract_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("contract_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("revenue_share_bps", sa.Integer, nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
        sa.UniqueConstraint("contract_id", "version", name="uq_contract_version"),
        sa.CheckConstraint("revenue_share_bps BETWEEN 1 AND 10000", name="ck_contract_share_bps"),
    )
    op.create_table(
        "author_revenue_entries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(128), nullable=False),
        sa.Column("gross_cents", sa.BigInteger, nullable=False),
        sa.Column("author_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("settlement_id", sa.String(64), nullable=True),
        _created_at(),
        sa.UniqueConstraint("source_ref", name="uq_author_revenue_source_ref"),
        sa.CheckConstraint(
            "gross_cents > 0 AND author_cents >= 0", name="ck_author_revenue_amount"
        ),
    )
    op.create_table(
        "author_settlements",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("period", sa.String(32), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("withdrawn_cents", sa.BigInteger, nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
        sa.UniqueConstraint("author_id", "period", name="uq_author_settlement_period"),
        sa.CheckConstraint(
            "amount_cents >= 0 AND withdrawn_cents >= 0", name="ck_settlement_amount"
        ),
    )
    op.create_table(
        "withdrawal_requests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("settlement_id", sa.String(64), nullable=False),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("payout_method", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["settlement_id"], ["author_settlements.id"]),
        sa.CheckConstraint("amount_cents >= 1000", name="ck_withdrawal_minimum"),
    )
    op.create_table(
        "chargebacks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_ref", sa.String(128), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("recovered_cents", sa.BigInteger, nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "amount_cents > 0 AND recovered_cents >= 0", name="ck_chargeback_amount"
        ),
    )
    op.create_table(
        "financial_recovery_claims",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("chargeback_id", sa.String(64), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["chargeback_id"], ["chargebacks.id"]),
        sa.CheckConstraint("amount_cents > 0", name="ck_recovery_claim_amount"),
    )


def downgrade() -> None:
    op.drop_table("financial_recovery_claims")
    op.drop_table("chargebacks")
    op.drop_table("withdrawal_requests")
    op.drop_table("author_settlements")
    op.drop_table("author_revenue_entries")
    op.drop_table("contract_versions")
    op.drop_table("contracts")
