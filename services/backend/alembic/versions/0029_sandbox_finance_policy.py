"""Persist virtual contract policy and tax snapshots for sandbox settlement."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_sandbox_finance_policy"
down_revision: str | None = "0028_author_center_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contract_versions",
        sa.Column(
            "policy_version",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'SANDBOX_CN_2026_V1'"),
        ),
    )
    op.add_column(
        "contract_versions",
        sa.Column(
            "tax_withholding_bps", sa.Integer, nullable=False, server_default=sa.text("1000")
        ),
    )
    op.add_column(
        "contract_versions",
        sa.Column(
            "tax_free_threshold_cents",
            sa.BigInteger,
            nullable=False,
            server_default=sa.text("100000"),
        ),
    )
    op.create_check_constraint(
        "ck_contract_tax_withholding_bps",
        "contract_versions",
        "tax_withholding_bps BETWEEN 0 AND 10000",
    )
    op.create_check_constraint(
        "ck_contract_tax_free_threshold",
        "contract_versions",
        "tax_free_threshold_cents >= 0",
    )
    op.add_column("author_revenue_entries", sa.Column("tax_cents", sa.BigInteger, nullable=True))
    op.add_column(
        "author_revenue_entries", sa.Column("net_author_cents", sa.BigInteger, nullable=True)
    )
    op.add_column(
        "author_revenue_entries", sa.Column("policy_version", sa.String(64), nullable=True)
    )
    op.execute("UPDATE author_revenue_entries SET tax_cents = 0 WHERE tax_cents IS NULL")
    op.execute(
        "UPDATE author_revenue_entries SET net_author_cents = author_cents WHERE net_author_cents IS NULL"
    )
    op.add_column("author_settlements", sa.Column("gross_cents", sa.BigInteger, nullable=True))
    op.add_column("author_settlements", sa.Column("tax_cents", sa.BigInteger, nullable=True))
    op.execute("UPDATE author_settlements SET gross_cents = amount_cents WHERE gross_cents IS NULL")
    op.execute("UPDATE author_settlements SET tax_cents = 0 WHERE tax_cents IS NULL")


def downgrade() -> None:
    op.drop_column("author_settlements", "tax_cents")
    op.drop_column("author_settlements", "gross_cents")
    op.drop_column("author_revenue_entries", "policy_version")
    op.drop_column("author_revenue_entries", "net_author_cents")
    op.drop_column("author_revenue_entries", "tax_cents")
    op.drop_constraint("ck_contract_tax_free_threshold", "contract_versions", type_="check")
    op.drop_constraint("ck_contract_tax_withholding_bps", "contract_versions", type_="check")
    op.drop_column("contract_versions", "tax_free_threshold_cents")
    op.drop_column("contract_versions", "tax_withholding_bps")
    op.drop_column("contract_versions", "policy_version")
