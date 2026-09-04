"""Add privacy, parameter, reconciliation, emergency, and outbox facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_governance"
down_revision: str | None = "0010_reader_experience"
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
        "privacy_requests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
        sa.UniqueConstraint("account_id", "kind", name="uq_privacy_request_kind"),
    )
    op.create_table(
        "agreement_acceptances",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("agreement_code", sa.String(64), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        _created_at(),
        sa.UniqueConstraint("account_id", "agreement_code", "version", name="uq_agreement_acceptance"),
    )
    op.create_table(
        "parameter_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("parameter_key", sa.String(128), nullable=False),
        sa.Column("value_text", sa.Text, nullable=False),
        sa.Column("maker_id", sa.String(64), nullable=False),
        sa.Column("checker_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
    )
    op.create_table(
        "payment_credit_pending",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("payment_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
        sa.UniqueConstraint("payment_id", name="uq_payment_credit_pending"),
    )
    op.create_table(
        "reconciliation_batches",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("business_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
        sa.UniqueConstraint("business_date", name="uq_reconciliation_business_date"),
    )
    op.create_table(
        "reconciliation_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("batch_id", sa.String(64), nullable=False),
        sa.Column("reference", sa.String(128), nullable=False),
        sa.Column("difference", sa.String(32), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["batch_id"], ["reconciliation_batches.id"]),
    )
    op.create_table(
        "platform_emergencies",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("features_json", sa.Text, nullable=False),
        sa.Column("operator_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
    )
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        _created_at(),
    )


def downgrade() -> None:
    for table in (
        "outbox_events",
        "platform_emergencies",
        "reconciliation_items",
        "reconciliation_batches",
        "payment_credit_pending",
        "parameter_versions",
        "agreement_acceptances",
        "privacy_requests",
    ):
        op.drop_table(table)
