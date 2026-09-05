"""Persist operation campaigns, rewards, and legal retention holds."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_operation_facts"
down_revision: str | None = "0018_chapter_commerce_policies"
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
        "operation_legal_holds",
        sa.Column("resource_id", sa.String(64), primary_key=True),
        _created_at(),
    )
    op.create_table(
        "operation_campaigns",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("start_date", sa.String(32), nullable=False),
        sa.Column("end_date", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
    )
    op.create_table(
        "operation_campaign_enrollments",
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("campaign_id", sa.String(64), primary_key=True),
        _created_at(),
    )
    op.create_table(
        "operation_reward_grants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("reward_type", sa.String(64), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        _created_at(),
        sa.UniqueConstraint("idempotency_key", name="uq_operation_reward_idempotency"),
        sa.CheckConstraint("amount > 0", name="ck_operation_reward_amount"),
    )


def downgrade() -> None:
    for table in (
        "operation_reward_grants",
        "operation_campaign_enrollments",
        "operation_campaigns",
        "operation_legal_holds",
    ):
        op.drop_table(table)
