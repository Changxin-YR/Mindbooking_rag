"""Add one-time MFA recovery codes, MFA audit facts, and review assignment scope."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_mfa_review_scope"
down_revision: str | None = "0026_payout_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "staff_mfa_factors",
        sa.Column("recovery_codes_hash", sa.Text(), nullable=True),
    )
    op.create_table(
        "staff_mfa_audits",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("staff_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor_staff_id", sa.String(36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_accounts.id"]),
        sa.ForeignKeyConstraint(["actor_staff_id"], ["staff_accounts.id"]),
        sa.CheckConstraint("action IN ('ENABLED', 'DISABLED')", name="ck_staff_mfa_audit_action"),
    )
    op.create_index(
        "ix_staff_mfa_audits_staff_created",
        "staff_mfa_audits",
        ["staff_id", "created_at"],
    )
    op.add_column(
        "review_tasks",
        sa.Column("assigned_staff_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_review_tasks_assigned_staff",
        "review_tasks",
        "staff_accounts",
        ["assigned_staff_id"],
        ["id"],
    )
    op.create_index(
        "ix_review_tasks_assigned_staff_status",
        "review_tasks",
        ["assigned_staff_id", "status"],
    )
    op.create_table(
        "outbox_event_deliveries",
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("consumer", sa.String(128), nullable=False),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("event_id", "consumer"),
        sa.ForeignKeyConstraint(["event_id"], ["outbox_events.id"]),
    )


def downgrade() -> None:
    op.drop_table("outbox_event_deliveries")
    op.drop_index("ix_review_tasks_assigned_staff_status", table_name="review_tasks")
    op.drop_constraint("fk_review_tasks_assigned_staff", "review_tasks", type_="foreignkey")
    op.drop_column("review_tasks", "assigned_staff_id")
    op.drop_index("ix_staff_mfa_audits_staff_created", table_name="staff_mfa_audits")
    op.drop_table("staff_mfa_audits")
    op.drop_column("staff_mfa_factors", "recovery_codes_hash")
