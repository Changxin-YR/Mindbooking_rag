"""Add configurable membership commercial entitlement facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_membership_commercial"
down_revision: str | None = "0023_agent_audit_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("membership_accounts", sa.Column("plan_code", sa.String(64), nullable=True))
    op.add_column(
        "membership_library_entries", sa.Column("plan_code", sa.String(64), nullable=True)
    )
    op.drop_constraint(
        "uq_membership_library_entries_book_id", "membership_library_entries", type_="unique"
    )
    op.create_unique_constraint(
        "uq_membership_library_entries_plan_book",
        "membership_library_entries",
        ["plan_code", "book_id"],
    )
    op.create_index("ix_membership_accounts_plan", "membership_accounts", ["plan_code"])

    op.create_table(
        "membership_plan_versions",
        sa.Column("plan_code", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("duration_days", sa.Integer, nullable=False),
        sa.Column("daily_recommend_ticket_count", sa.Integer, nullable=False),
        sa.Column("monthly_chapter_ticket_count", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("plan_code", "version"),
        sa.CheckConstraint("duration_days > 0", name="ck_membership_plan_duration_positive"),
        sa.CheckConstraint(
            "daily_recommend_ticket_count >= 0", name="ck_membership_plan_daily_nonnegative"
        ),
        sa.CheckConstraint(
            "monthly_chapter_ticket_count >= 0", name="ck_membership_plan_monthly_nonnegative"
        ),
    )
    op.create_table(
        "ticket_accounts",
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("recommend_balance", sa.BigInteger, nullable=False, server_default=sa.text("0")),
        sa.Column("monthly_balance", sa.BigInteger, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("recommend_balance >= 0", name="ck_ticket_recommend_nonnegative"),
        sa.CheckConstraint("monthly_balance >= 0", name="ck_ticket_monthly_nonnegative"),
    )
    op.create_table(
        "ticket_lots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("ticket_type", sa.String(16), nullable=False),
        sa.Column("issued_quantity", sa.BigInteger, nullable=False),
        sa.Column("available_quantity", sa.BigInteger, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_status", sa.String(16), nullable=False),
        sa.Column("source_ref", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("issued_quantity > 0", name="ck_ticket_lot_issued_positive"),
        sa.CheckConstraint("available_quantity >= 0", name="ck_ticket_lot_available_nonnegative"),
    )
    op.create_index(
        "ix_ticket_lots_account_spend",
        "ticket_lots",
        ["account_id", "ticket_type", "expires_at", "created_at"],
    )
    op.create_table(
        "ticket_transactions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("ticket_type", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("quantity", sa.BigInteger, nullable=False),
        sa.Column("lot_id", sa.String(64), nullable=True),
        sa.Column("source_ref", sa.String(128), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_ticket_transactions_idempotency"),
        sa.CheckConstraint("quantity > 0", name="ck_ticket_transaction_quantity_positive"),
    )
    op.create_table(
        "book_ticket_votes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("ticket_type", sa.String(16), nullable=False),
        sa.Column("quantity", sa.BigInteger, nullable=False),
        sa.Column("risk_status", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_book_ticket_votes_idempotency"),
    )
    op.create_table(
        "gift_definitions",
        sa.Column("gift_code", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("price_coin", sa.BigInteger, nullable=False),
        sa.Column("fan_value", sa.BigInteger, nullable=False),
        sa.Column("spend_mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("price_coin > 0", name="ck_gift_price_positive"),
        sa.CheckConstraint("fan_value > 0", name="ck_gift_fan_value_positive"),
    )
    op.create_table(
        "gift_orders",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("gift_code", sa.String(64), nullable=False),
        sa.Column("quantity", sa.BigInteger, nullable=False),
        sa.Column("total_coin", sa.BigInteger, nullable=False),
        sa.Column("income_base_coin", sa.BigInteger, nullable=False),
        sa.Column("fan_value", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_gift_orders_idempotency"),
    )
    op.create_table(
        "book_fan_profiles",
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("value", sa.BigInteger, nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("account_id", "book_id"),
    )
    op.create_table(
        "fan_value_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("value", sa.BigInteger, nullable=False),
        sa.Column("source_ref", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "account_id", "book_id", "source", "source_ref", name="uq_fan_value_event_source"
        ),
    )
    op.create_table(
        "fan_level_rules",
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("threshold", sa.BigInteger, nullable=False),
        sa.PrimaryKeyConstraint("version", "level"),
    )
    op.create_table(
        "membership_user_growth_profiles",
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("points", sa.BigInteger, nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("rule_version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "membership_user_growth_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("points", sa.BigInteger, nullable=False),
        sa.Column("source_ref", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "source_ref", name="uq_membership_growth_event_source"),
    )
    op.create_table(
        "membership_user_growth_rules",
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("threshold", sa.BigInteger, nullable=False),
        sa.PrimaryKeyConstraint("version", "level"),
    )


def downgrade() -> None:
    for table in (
        "membership_user_growth_rules",
        "membership_user_growth_events",
        "membership_user_growth_profiles",
        "fan_level_rules",
        "fan_value_events",
        "book_fan_profiles",
        "gift_orders",
        "gift_definitions",
        "book_ticket_votes",
        "ticket_transactions",
        "ticket_lots",
        "ticket_accounts",
        "membership_plan_versions",
    ):
        op.drop_table(table)
    op.drop_index("ix_membership_accounts_plan", table_name="membership_accounts")
    op.drop_constraint(
        "uq_membership_library_entries_plan_book", "membership_library_entries", type_="unique"
    )
    op.create_unique_constraint(
        "uq_membership_library_entries_book_id", "membership_library_entries", ["book_id"]
    )
    op.drop_column("membership_library_entries", "plan_code")
    op.drop_column("membership_accounts", "plan_code")
