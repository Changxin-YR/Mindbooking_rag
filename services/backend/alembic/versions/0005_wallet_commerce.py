"""Add wallet, payment, commerce entitlement, and membership facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_wallet_commerce"
down_revision: str | None = "0003_content_review_reading"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wallet_accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("recharge_coin", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("gift_coin", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", name="uq_wallet_accounts_account_id"),
    )
    op.create_table(
        "wallet_journals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("journal_type", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "idempotency_key", name="uq_wallet_journals_idempotency"),
    )
    op.create_table(
        "wallet_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("journal_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("asset_type", sa.String(24), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["journal_id"], ["wallet_journals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount <> 0", name="ck_wallet_entries_nonzero"),
    )
    op.create_table(
        "wallet_asset_lots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("lot_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("asset_type", sa.String(24), nullable=False),
        sa.Column("origin", sa.String(64), nullable=False),
        sa.Column("available_amount", sa.BigInteger(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lot_id", name="uq_wallet_asset_lots_lot_id"),
    )
    op.create_index(
        "ix_wallet_asset_lots_spend",
        "wallet_asset_lots",
        ["account_id", "asset_type", "available_amount", "expires_at", "issued_at"],
    )
    op.create_table(
        "wallet_lot_allocations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("lot_id", sa.String(64), nullable=False),
        sa.Column("journal_id", sa.BigInteger(), nullable=False),
        sa.Column("allocation_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["journal_id"], ["wallet_journals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount > 0", name="ck_wallet_lot_allocations_positive"),
    )

    op.create_table(
        "payment_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("payment_no", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("paid_cents", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_no", name="uq_payment_orders_payment_no"),
    )
    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("payment_order_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_order_id"], ["payment_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_order_id", "attempt_no", name="uq_payment_attempts_number"),
    )
    op.create_table(
        "payment_channel_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_event_id", sa.String(128), nullable=False),
        sa.Column("payment_no", sa.String(64), nullable=False),
        sa.Column("channel_transaction_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_payment_events_provider_event"
        ),
        sa.UniqueConstraint(
            "provider", "channel_transaction_id", name="uq_payment_events_provider_tx"
        ),
    )
    op.create_table(
        "recharge_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("recharge_no", sa.String(64), nullable=False),
        sa.Column("payment_order_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("paid_cents", sa.BigInteger(), nullable=False),
        sa.Column("recharge_coin", sa.BigInteger(), nullable=False),
        sa.Column("gift_coin", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_order_id"], ["payment_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recharge_no", name="uq_recharge_orders_recharge_no"),
        sa.UniqueConstraint("payment_order_id", name="uq_recharge_orders_payment"),
    )

    op.create_table(
        "chapter_purchase_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("purchase_no", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("total_coin", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("purchase_no", name="uq_chapter_purchase_orders_purchase_no"),
    )
    op.create_table(
        "chapter_purchase_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("purchase_order_id", sa.BigInteger(), nullable=False),
        sa.Column("chapter_id", sa.String(64), nullable=False),
        sa.Column("price_coin", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["chapter_purchase_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("price_coin > 0", name="ck_chapter_purchase_items_positive"),
    )
    op.create_table(
        "chapter_entitlements",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("chapter_id", sa.String(64), nullable=False),
        sa.Column("source_purchase_no", sa.String(64), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id", "chapter_id", name="uq_chapter_entitlements_account_chapter"
        ),
    )

    op.create_table(
        "membership_accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", name="uq_membership_accounts_account_id"),
    )
    op.create_table(
        "membership_library_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("active_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id", name="uq_membership_library_entries_book_id"),
    )


def downgrade() -> None:
    op.drop_table("membership_library_entries")
    op.drop_table("membership_accounts")
    op.drop_table("chapter_entitlements")
    op.drop_table("chapter_purchase_items")
    op.drop_table("chapter_purchase_orders")
    op.drop_table("recharge_orders")
    op.drop_table("payment_channel_events")
    op.drop_table("payment_attempts")
    op.drop_table("payment_orders")
    op.drop_table("wallet_lot_allocations")
    op.drop_index("ix_wallet_asset_lots_spend", table_name="wallet_asset_lots")
    op.drop_table("wallet_asset_lots")
    op.drop_table("wallet_entries")
    op.drop_table("wallet_journals")
    op.drop_table("wallet_accounts")
