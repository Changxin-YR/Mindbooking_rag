"""Add integrity checks for virtual finance snapshot amounts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0030_finance_constraints"
down_revision: str | None = "0029_sandbox_finance_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_check(name: str, table: str, condition: str) -> None:
    if context.is_offline_mode():
        op.create_check_constraint(name, table, condition)
        return
    existing = {item.get("name") for item in sa.inspect(op.get_bind()).get_check_constraints(table)}
    if name not in existing:
        op.create_check_constraint(name, table, condition)


def upgrade() -> None:
    _add_check("ck_author_revenue_tax_cents", "author_revenue_entries", "tax_cents >= 0")
    _add_check(
        "ck_author_revenue_net_cents",
        "author_revenue_entries",
        "net_author_cents >= 0 AND net_author_cents <= author_cents",
    )
    _add_check("ck_author_settlement_gross_cents", "author_settlements", "gross_cents >= 0")
    _add_check(
        "ck_author_settlement_tax_cents",
        "author_settlements",
        "tax_cents >= 0 AND tax_cents <= gross_cents",
    )


def downgrade() -> None:
    for name, table in (
        ("ck_author_settlement_tax_cents", "author_settlements"),
        ("ck_author_settlement_gross_cents", "author_settlements"),
        ("ck_author_revenue_net_cents", "author_revenue_entries"),
        ("ck_author_revenue_tax_cents", "author_revenue_entries"),
    ):
        existing = {
            item.get("name") for item in sa.inspect(op.get_bind()).get_check_constraints(table)
        }
        if name in existing:
            op.drop_constraint(name, table, type_="check")
