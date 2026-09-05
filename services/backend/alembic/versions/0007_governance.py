"""Add community, notification, support, risk and approval facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_governance"
down_revision: str | None = "0006_refund"
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
        "community_report_cases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
        sa.UniqueConstraint("content_type", "content_id", name="uq_report_case_content"),
        sa.CheckConstraint(
            "status IN ('OPEN', 'PROCESSING', 'RESOLVED')", name="ck_report_case_status"
        ),
    )
    op.create_table(
        "community_report_submissions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("reporter_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["case_id"], ["community_report_cases.id"]),
        sa.UniqueConstraint("case_id", "reporter_id", name="uq_report_submission_reporter"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(8), nullable=False),
        sa.Column("channels", sa.String(64), nullable=False),
        _created_at(),
        sa.CheckConstraint("priority IN ('NORMAL', 'P0')", name="ck_notification_priority"),
        sa.CheckConstraint(
            "category IN ('SYSTEM', 'SECURITY', 'MARKETING')", name="ck_notification_category"
        ),
        sa.CheckConstraint(
            "NOT (category = 'SECURITY' AND priority = 'P0') OR channels = 'IN_APP,SMS'",
            name="ck_notification_p0_channels",
        ),
    )
    op.create_table(
        "notification_preferences",
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("marketing_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        _created_at(),
        sa.CheckConstraint("marketing_enabled = 1", name="ck_marketing_cannot_be_disabled"),
    )
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(8), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "status IN ('NEW', 'IN_PROGRESS', 'WAITING_USER', 'WAITING_INTERNAL', 'RESOLVED', 'CLOSED', 'CANCELLED')",
            name="ck_support_ticket_status",
        ),
        sa.CheckConstraint(
            "priority IN ('P0', 'P1', 'P2', 'P3')", name="ck_support_ticket_priority"
        ),
    )
    op.create_table(
        "support_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("ticket_id", sa.String(64), nullable=False),
        sa.Column("author_type", sa.String(16), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"]),
        sa.CheckConstraint("author_type IN ('USER', 'STAFF')", name="ck_support_message_author"),
    )
    op.create_table(
        "risk_order_facts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("amount_coin", sa.BigInteger, nullable=False),
        _created_at(),
        sa.CheckConstraint("amount_coin >= 0", name="ck_risk_order_amount_nonnegative"),
    )
    op.create_table(
        "risk_signals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("signal_type", sa.String(64), nullable=False),
        sa.Column("order_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["order_id"], ["risk_order_facts.id"]),
        sa.CheckConstraint("status IN ('OBSERVE', 'FROZEN')", name="ck_risk_signal_status"),
    )
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("requester_id", sa.String(64), nullable=False),
        sa.Column("critical", sa.Boolean, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')", name="ck_approval_request_status"
        ),
    )
    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("approver_id", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["request_id"], ["approval_requests.id"]),
        sa.UniqueConstraint("request_id", "approver_id", name="uq_approval_decision_approver"),
        sa.CheckConstraint("decision IN ('APPROVE', 'REJECT')", name="ck_approval_decision"),
    )


def downgrade() -> None:
    op.drop_table("approval_decisions")
    op.drop_table("approval_requests")
    op.drop_table("risk_signals")
    op.drop_table("risk_order_facts")
    op.drop_table("support_messages")
    op.drop_table("support_tickets")
    op.drop_table("notification_preferences")
    op.drop_table("notifications")
    op.drop_table("community_report_submissions")
    op.drop_table("community_report_cases")
