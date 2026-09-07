import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.approval.domain import ApprovalStatus
from novel_platform.modules.approval.sql_service import SqlApprovalService
from novel_platform.modules.community.sql_service import SqlCommunityService
from novel_platform.modules.notification.domain import NotificationCategory, NotificationPriority
from novel_platform.modules.notification.sql_service import SqlNotificationService
from novel_platform.modules.support.domain import SupportPriority, SupportStatus
from novel_platform.modules.support.sql_service import SqlSupportService


def _engine() -> sa.Engine:
    metadata = sa.MetaData()
    cases = sa.Table(
        "community_report_cases",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("content_type", "content_id"),
    )
    sa.Table(
        "community_report_submissions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("case_id", sa.String(64), sa.ForeignKey(cases.c.id), nullable=False),
        sa.Column("reporter_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("case_id", "reporter_id"),
    )
    sa.Table(
        "notifications",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(8), nullable=False),
        sa.Column("channels", sa.String(64), nullable=False),
        sa.Column("read_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "notification_preferences",
        metadata,
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("marketing_enabled", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    tickets = sa.Table(
        "support_tickets",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(8), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "support_messages",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("ticket_id", sa.String(64), sa.ForeignKey(tickets.c.id), nullable=False),
        sa.Column("author_type", sa.String(16), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    approvals = sa.Table(
        "approval_requests",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("requester_id", sa.String(64), nullable=False),
        sa.Column("critical", sa.Boolean, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "approval_decisions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(64), sa.ForeignKey(approvals.c.id), nullable=False),
        sa.Column("approver_id", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("request_id", "approver_id"),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    return engine


def test_sql_community_persists_case_and_rejects_duplicate_reporter() -> None:
    engine = _engine()
    service = SqlCommunityService(engine)
    created = service.submit_report("BOOK", "book-1", "account-1", "spam")

    rebuilt = SqlCommunityService(engine)
    assert rebuilt.get_case(created.id) == created
    with pytest.raises(ValueError, match="already submitted"):
        rebuilt.submit_report("BOOK", "book-1", "account-1", "again")


def test_sql_notification_persists_channels_and_marketing_preference() -> None:
    engine = _engine()
    service = SqlNotificationService(engine)
    notification = service.send(
        "account-1", NotificationCategory.SECURITY, NotificationPriority.P0, {"IN_APP"}
    )
    service.set_marketing_enabled("account-1", True)

    with engine.begin() as connection:
        row = connection.execute(
            sa.text("SELECT channels FROM notifications WHERE id = :id"), {"id": notification.id}
        ).scalar_one()
        enabled = connection.execute(
            sa.text(
                "SELECT marketing_enabled FROM notification_preferences WHERE account_id = :id"
            ),
            {"id": "account-1"},
        ).scalar_one()
    assert row == "IN_APP,SMS"
    assert enabled in (True, 1)
    with pytest.raises(ValueError, match="cannot be disabled"):
        service.set_marketing_enabled("account-1", False)


def test_sql_notification_list_reloads_account_history_and_filters_category() -> None:
    service = SqlNotificationService(_engine())
    service.send("account-1", NotificationCategory.SYSTEM, NotificationPriority.NORMAL, {"IN_APP"})
    security = service.send(
        "account-1", NotificationCategory.SECURITY, NotificationPriority.P0, {"IN_APP"}
    )
    service.send("account-2", NotificationCategory.SYSTEM, NotificationPriority.NORMAL, {"IN_APP"})

    rebuilt = SqlNotificationService(service.engine)
    listed = rebuilt.list("account-1")
    assert listed[0] == security
    assert len(listed) == 2
    assert [
        item.category for item in rebuilt.list("account-1", category=NotificationCategory.SECURITY)
    ] == [NotificationCategory.SECURITY]


def test_sql_notification_read_state_is_account_scoped_and_idempotent() -> None:
    service = SqlNotificationService(_engine())
    notification = service.send(
        "account-1", NotificationCategory.SYSTEM, NotificationPriority.NORMAL, {"IN_APP"}
    )
    assert notification.is_read is False
    assert service.unread_count("account-1") == 1

    marked = service.mark_read("account-1", notification.id)
    assert marked.is_read is True
    assert service.unread_count("account-1") == 0
    assert service.mark_read("account-1", notification.id).is_read is True
    with pytest.raises(KeyError):
        service.mark_read("account-2", notification.id)


def test_sql_support_rebuild_preserves_messages_and_status_transition() -> None:
    engine = _engine()
    service = SqlSupportService(engine)
    ticket = service.open_ticket("account-1", "PAYMENT", SupportPriority.P1, "payment failed")

    rebuilt = SqlSupportService(engine)
    assert rebuilt.get_ticket(ticket.id) == ticket
    rebuilt.resolve(ticket.id)
    rebuilt.reply(ticket.id, "please retry", "USER")
    current = rebuilt.get_ticket(ticket.id)
    assert current.status is SupportStatus.IN_PROGRESS
    assert [message.body for message in current.messages] == ["payment failed", "please retry"]


def test_sql_approval_persists_and_enforces_maker_checker() -> None:
    engine = _engine()
    service = SqlApprovalService(engine)
    request = service.request("PAYOUT", "maker-1", critical=True)

    assert SqlApprovalService(engine).get(request.id) == request
    with pytest.raises(ValueError, match="requester cannot approve"):
        service.approve(request.id, "maker-1")
    approved = SqlApprovalService(engine).approve(request.id, "checker-1")
    assert approved.status is ApprovalStatus.APPROVED
