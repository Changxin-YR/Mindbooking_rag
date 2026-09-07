from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.membership.domain import (
    AccessMode,
    ChapterPolicy,
    TicketType,
    UserGrowthProfile,
)
from novel_platform.modules.membership.sql_service import SqlMembershipService
from novel_platform.modules.payment import ProviderStatus, SandboxPaymentProvider
from novel_platform.modules.payment.provider import ProviderEvent, _event_signature


def _engine() -> sa.Engine:
    metadata = sa.MetaData()
    sa.Table(
        "membership_accounts",
        metadata,
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(64), nullable=False, unique=True),
        sa.Column("plan_code", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "membership_library_entries",
        metadata,
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("plan_code", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("active_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active_until", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.UniqueConstraint("plan_code", "book_id"),
    )
    sa.Table(
        "membership_plan_versions",
        metadata,
        sa.Column("plan_code", sa.String(64), primary_key=True),
        sa.Column("version", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("duration_days", sa.Integer, nullable=False),
        sa.Column("price_cents", sa.BigInteger, nullable=False),
        sa.Column("daily_recommend_ticket_count", sa.Integer, nullable=False),
        sa.Column("monthly_chapter_ticket_count", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "ticket_accounts",
        metadata,
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("recommend_balance", sa.BigInteger, nullable=False),
        sa.Column("monthly_balance", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "ticket_lots",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("ticket_type", sa.String(16), nullable=False),
        sa.Column("issued_quantity", sa.BigInteger, nullable=False),
        sa.Column("available_quantity", sa.BigInteger, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("risk_status", sa.String(16), nullable=False),
        sa.Column("source_ref", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "ticket_transactions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("ticket_type", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("quantity", sa.BigInteger, nullable=False),
        sa.Column("lot_id", sa.String(64)),
        sa.Column("source_ref", sa.String(128)),
        sa.Column("idempotency_key", sa.String(128), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "book_ticket_votes",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("ticket_type", sa.String(16), nullable=False),
        sa.Column("quantity", sa.BigInteger, nullable=False),
        sa.Column("risk_status", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "gift_definitions",
        metadata,
        sa.Column("gift_code", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("price_coin", sa.BigInteger, nullable=False),
        sa.Column("fan_value", sa.BigInteger, nullable=False),
        sa.Column("spend_mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "gift_orders",
        metadata,
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
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "book_fan_profiles",
        metadata,
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), primary_key=True),
        sa.Column("value", sa.BigInteger, nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "fan_value_events",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("value", sa.BigInteger, nullable=False),
        sa.Column("source_ref", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "fan_level_rules",
        metadata,
        sa.Column("version", sa.Integer, primary_key=True),
        sa.Column("level", sa.Integer, primary_key=True),
        sa.Column("threshold", sa.BigInteger, nullable=False),
    )
    sa.Table(
        "membership_user_growth_profiles",
        metadata,
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("points", sa.BigInteger, nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("rule_version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "membership_user_growth_events",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("points", sa.BigInteger, nullable=False),
        sa.Column("source_ref", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "membership_user_growth_rules",
        metadata,
        sa.Column("version", sa.Integer, primary_key=True),
        sa.Column("level", sa.Integer, primary_key=True),
        sa.Column("threshold", sa.BigInteger, nullable=False),
    )
    payment_orders = sa.Table(
        "payment_orders",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("payment_no", sa.String(64), nullable=False, unique=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("paid_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "payment_channel_events",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_event_id", sa.String(128), nullable=False),
        sa.Column("payment_no", sa.String(64), nullable=False),
        sa.Column("channel_transaction_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_event_id"),
    )
    sa.Table(
        "membership_orders",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "payment_order_id",
            sa.Integer,
            sa.ForeignKey(payment_orders.c.id),
            nullable=False,
            unique=True,
        ),
        sa.Column("payment_no", sa.String(64), nullable=False, unique=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("plan_code", sa.String(64), nullable=False),
        sa.Column("plan_version", sa.Integer, nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("price_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "wallet_mutations",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
    )
    metadata.create_all(engine := create_engine("sqlite+pysqlite:///:memory:"))
    return engine


def test_sql_membership_activation_and_library_survive_service_rebuild() -> None:
    engine = _engine()
    service = SqlMembershipService(engine)
    service.create_plan(
        "MONTHLY",
        "月度会员",
        30,
        price_cents=999,
        daily_recommend_tickets=2,
        monthly_chapter_tickets=5,
    )

    service.add_library_book("MONTHLY", "book-1")
    expires_at = datetime.now(UTC) + timedelta(days=30)

    service.activate("acct-1", "MONTHLY", expires_at)
    rebuilt = SqlMembershipService(engine)

    assert rebuilt.is_active("acct-1")
    assert not rebuilt.is_active("acct-1", datetime.now(UTC) + timedelta(days=31))
    assert (
        rebuilt.access(
            "acct-1",
            "chapter-1",
            ChapterPolicy(100, AccessMode.VIP_REQUIRED),
            purchased=False,
            book_id="book-1",
        )
        is AccessMode.MEMBER_FREE
    )


def test_sql_membership_tickets_are_separate_and_vote_is_idempotent() -> None:
    engine = _engine()
    service = SqlMembershipService(engine)

    service.grant_tickets(
        "acct-1", TicketType.RECOMMEND, 2, source_ref="daily", idempotency_key="g-1"
    )
    service.grant_tickets(
        "acct-1", TicketType.MONTHLY, 1, source_ref="member", idempotency_key="g-2"
    )
    service.grant_tickets(
        "acct-1", TicketType.RECOMMEND, 2, source_ref="daily", idempotency_key="g-1"
    )
    with pytest.raises(ValueError, match="IDEMPOTENCY_KEY_CONFLICT"):
        service.grant_tickets(
            "acct-2", TicketType.RECOMMEND, 1, source_ref="other", idempotency_key="g-1"
        )
    vote = service.vote("acct-1", "book-1", TicketType.RECOMMEND, idempotency_key="v-1")
    duplicate = service.vote("acct-1", "book-1", TicketType.RECOMMEND, idempotency_key="v-1")

    assert duplicate == vote
    assert service.ticket_balance("acct-1").recommend == 1
    assert service.ticket_balance("acct-1").monthly == 1


def test_sql_membership_gift_debit_and_fan_value_share_transaction() -> None:
    engine = _engine()
    service = SqlMembershipService(engine)
    service.register_gift("LAMP", "明灯", 50, 8)

    def spend(connection: sa.Connection, account_id: str, amount: int, mode: str) -> None:
        assert mode == "GIFT_AND_RECHARGE"
        connection.execute(
            sa.text(
                "INSERT INTO wallet_mutations (account_id, amount, reason) "
                "VALUES (:account_id, :amount, :reason)"
            ),
            {"account_id": account_id, "amount": -amount, "reason": "GIFT"},
        )

    order = service.send_gift(
        "acct-1", "book-1", "author-1", "LAMP", idempotency_key="gift-1", asset_spend=spend
    )
    duplicate = service.send_gift(
        "acct-1", "book-1", "author-1", "LAMP", idempotency_key="gift-1", asset_spend=spend
    )

    assert duplicate == order
    assert order.income_base_coin == 50
    assert service.fan_profile("acct-1", "book-1").value == 8
    with engine.begin() as connection:
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM wallet_mutations")).scalar_one() == 1
        )


def test_sql_membership_growth_is_idempotent_and_rule_driven() -> None:
    engine = _engine()
    service = SqlMembershipService(engine)
    service.set_growth_level(1, 0)
    service.set_growth_level(2, 100)

    service.add_user_growth("acct-1", "READING", 60, source_ref="read-1")
    service.add_user_growth("acct-1", "READING", 60, source_ref="read-1")
    service.add_user_growth("acct-1", "INTERACTION", 40, source_ref="comment-1")

    assert service.user_growth("acct-1") == UserGrowthProfile("acct-1", 100, 2)


def test_sql_membership_gift_failure_rolls_back_asset_and_fan_facts() -> None:
    engine = _engine()
    service = SqlMembershipService(engine)
    service.register_gift("LAMP", "明灯", 50, 8)

    def spend(connection: sa.Connection, account_id: str, amount: int, mode: str) -> None:
        del connection, account_id, amount, mode
        raise RuntimeError("asset unavailable")

    with pytest.raises(RuntimeError, match="asset unavailable"):
        service.send_gift(
            "acct-1", "book-1", "author-1", "LAMP", idempotency_key="gift-fail", asset_spend=spend
        )
    with engine.begin() as connection:
        assert connection.execute(sa.text("SELECT COUNT(*) FROM gift_orders")).scalar_one() == 0
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM fan_value_events")).scalar_one() == 0
        )


def test_sql_membership_checkout_callback_activates_and_grants_configured_tickets() -> None:
    engine = _engine()
    service = SqlMembershipService(engine)
    service.create_plan(
        "MONTHLY",
        "月度会员",
        30,
        price_cents=999,
        daily_recommend_tickets=2,
        monthly_chapter_tickets=5,
    )

    order = service.create_order("acct-1", "MONTHLY", "WECHAT", "membership-key")
    assert order.status == "PENDING_PAYMENT"
    assert service.create_order("acct-1", "MONTHLY", "WECHAT", "membership-key") == order

    paid = service.handle_payment_callback("WECHAT", "event-1", order.payment_no)
    assert paid == order.id
    assert service.is_active("acct-1")
    assert service.ticket_balance("acct-1").recommend == 2
    assert service.ticket_balance("acct-1").monthly == 5
    assert service.handle_payment_callback("WECHAT", "event-1", order.payment_no) == order.id

    with engine.begin() as connection:
        assert (
            connection.execute(sa.text("SELECT status FROM payment_orders")).scalar_one() == "PAID"
        )
        assert (
            connection.execute(sa.text("SELECT status FROM membership_orders")).scalar_one()
            == "PAID"
        )


def test_sql_membership_provider_event_verifies_and_handles_non_success_statuses() -> None:
    engine = _engine()
    provider = SandboxPaymentProvider("membership-secret", provider_name="SANDBOX")
    service = SqlMembershipService(engine)
    service.payment_provider = provider
    service.payment_provider_secret = "membership-secret"
    service.create_plan(
        "MONTHLY",
        "月度会员",
        30,
        price_cents=999,
        daily_recommend_tickets=2,
        monthly_chapter_tickets=5,
    )

    failed_order = service.create_order("acct-failed", "MONTHLY", "SANDBOX", "membership-failed")
    provider.create_checkout(failed_order.payment_no, failed_order.price_cents)
    failed_event = provider.generate_callback_event(
        failed_order.payment_no, ProviderStatus.CANCELLED
    )
    assert service.handle_payment_provider_event(failed_event) == failed_order.id
    assert not service.is_active("acct-failed")
    assert service.handle_payment_provider_event(failed_event) == failed_order.id

    paid_order = service.create_order("acct-paid", "MONTHLY", "SANDBOX", "membership-paid")
    checkout = provider.create_checkout(paid_order.payment_no, paid_order.price_cents)
    assert checkout.provider == "SANDBOX"
    paid_event = provider.generate_callback_event(paid_order.payment_no, ProviderStatus.SUCCESS)
    assert service.handle_payment_provider_event(paid_event) == paid_order.id
    assert service.is_active("acct-paid")


def test_sql_membership_provider_processing_can_finish_with_success() -> None:
    engine = _engine()
    provider = SandboxPaymentProvider("membership-secret", provider_name="SANDBOX")
    service = SqlMembershipService(engine)
    service.payment_provider = provider
    service.payment_provider_secret = "membership-secret"
    service.create_plan(
        "PROCESSING",
        "处理中会员",
        30,
        price_cents=999,
        daily_recommend_tickets=2,
        monthly_chapter_tickets=5,
    )

    order = service.create_order("acct-processing", "PROCESSING", "SANDBOX", "processing-key")
    provider.create_checkout(order.payment_no, order.price_cents)
    processing = provider.generate_callback_event(order.payment_no, ProviderStatus.PROCESSING)
    assert service.handle_payment_provider_event(processing) == order.id
    success = provider.generate_callback_event(order.payment_no, ProviderStatus.SUCCESS)

    assert service.handle_payment_provider_event(success) == order.id
    assert service.is_active("acct-processing")


def test_sql_membership_provider_transaction_conflict_and_duplicate_callback_are_idempotent() -> (
    None
):
    engine = _engine()
    provider = SandboxPaymentProvider("membership-secret", provider_name="SANDBOX")
    service = SqlMembershipService(engine)
    service.payment_provider = provider
    service.payment_provider_secret = "membership-secret"
    service.create_plan(
        "MONTHLY",
        "月度会员",
        30,
        price_cents=999,
        daily_recommend_tickets=2,
        monthly_chapter_tickets=5,
    )

    first = service.create_order("acct-first", "MONTHLY", "SANDBOX", "membership-first")
    second = service.create_order("acct-second", "MONTHLY", "SANDBOX", "membership-second")
    provider.create_checkout(first.payment_no, first.price_cents)
    provider.create_checkout(second.payment_no, second.price_cents)
    first_event = provider.generate_callback_event(first.payment_no, ProviderStatus.SUCCESS)

    assert service.handle_payment_provider_event(first_event) == first.id
    balance = service.ticket_balance("acct-first")
    assert service.handle_payment_provider_event(first_event) == first.id
    assert service.ticket_balance("acct-first") == balance

    second_event = provider.generate_callback_event(second.payment_no, ProviderStatus.SUCCESS)
    unsigned = replace(
        second_event,
        provider_transaction_id=first_event.provider_transaction_id,
        signature="",
    )
    conflicting_event: ProviderEvent = replace(
        unsigned,
        signature=_event_signature("membership-secret", unsigned),
    )
    with pytest.raises(ValueError, match="PAYMENT_TRANSACTION_CONFLICT"):
        service.handle_payment_provider_event(conflicting_event)
