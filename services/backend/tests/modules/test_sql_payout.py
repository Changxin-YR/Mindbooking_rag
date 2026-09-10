from dataclasses import replace
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from novel_platform.modules.author_finance.domain import PayoutStatus
from novel_platform.modules.author_finance.sql_service import SqlAuthorFinanceService
from novel_platform.modules.payment import ProviderStatus, SandboxPayoutProvider
from novel_platform.modules.payment.provider import _event_signature


def _schema() -> sa.MetaData:
    metadata = sa.MetaData()
    contracts = sa.Table(
        "contracts",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signed_by", sa.String(64)),
        sa.Column("signed_at", sa.DateTime(timezone=True)),
        sa.Column("signature_hash", sa.String(64)),
    )
    sa.Table(
        "contract_versions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("contract_id", sa.String(64), sa.ForeignKey(contracts.c.id), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("revenue_share_bps", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "author_revenue_entries",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(128), nullable=False, unique=True),
        sa.Column("gross_cents", sa.BigInteger, nullable=False),
        sa.Column("author_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("settlement_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    settlements = sa.Table(
        "author_settlements",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("period", sa.String(32), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("withdrawn_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "withdrawal_requests",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("settlement_id", sa.String(64), sa.ForeignKey(settlements.c.id), nullable=False),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("payout_method", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("risk_status", sa.String(24), nullable=False),
        sa.Column("finance_status", sa.String(24), nullable=False),
        sa.Column("second_factor_verified", sa.Boolean, nullable=False),
        sa.Column("payout_destination", sa.String(128), nullable=False),
        sa.Column("risk_reviewer_id", sa.String(64)),
        sa.Column("finance_reviewer_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "chargebacks",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_ref", sa.String(128), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("recovered_cents", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "financial_recovery_claims",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("chargeback_id", sa.String(64), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    return metadata


def _service() -> tuple[SqlAuthorFinanceService, SandboxPayoutProvider, sa.Engine]:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = _schema()
    sa.Table(
        "payout_orders",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("withdrawal_id", sa.String(64), nullable=False, unique=True),
        sa.Column("payout_no", sa.String(64), nullable=False, unique=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("destination", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("provider_event_id", sa.String(128)),
        sa.Column("provider_transaction_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    provider = SandboxPayoutProvider("payout-secret")
    return (
        SqlAuthorFinanceService(
            engine,
            payout_provider=provider,
            payout_provider_secret="payout-secret",
        ),
        provider,
        engine,
    )


def test_sql_payout_requires_two_reviews_and_is_idempotent() -> None:
    service, provider, engine = _service()
    contract = service.create_contract("author-1", "book-1", 7000)
    approved = service.approve_contract(contract.id, "finance-maker")
    service.sign_contract(contract.id, "author-1")
    service.activate_contract(approved.id)
    revenue = service.record_revenue("author-1", "VIP", "purchase-1", 10_000, 7000)
    service.confirm_revenue(revenue.id)
    settlement = service.settle("author-1", "2026-09")
    withdrawal = service.withdraw(settlement.id, "author-1", 7_000, "BANK", True)

    with pytest.raises(ValueError, match="PAYOUT_REVIEW_REQUIRED"):
        service.create_payout_order(withdrawal.id, "finance-checker")

    service.approve_withdrawal_risk(withdrawal.id, "risk-1")
    payout = service.approve_withdrawal_finance(withdrawal.id, "finance-1")
    assert payout.status is PayoutStatus.PROCESSING
    assert service.approve_withdrawal_finance(withdrawal.id, "finance-1") == payout

    event = provider.generate_callback_event(payout.payout_no, ProviderStatus.SUCCESS)
    completed = service.handle_payout_provider_event(event)
    assert completed.status is PayoutStatus.SUCCESS
    assert service.handle_payout_provider_event(event) == completed
    with engine.begin() as connection:
        assert (
            connection.execute(sa.text("SELECT status FROM withdrawal_requests")).scalar_one()
            == "PAID"
        )


def test_sql_payout_failure_does_not_mark_withdrawal_paid() -> None:
    service, provider, _ = _service()
    contract = service.create_contract("author-1", "book-1", 7000)
    approved = service.approve_contract(contract.id, "finance-maker")
    service.sign_contract(contract.id, "author-1")
    service.activate_contract(approved.id)
    revenue = service.record_revenue("author-1", "VIP", "purchase-2", 10_000, 7000)
    service.confirm_revenue(revenue.id)
    settlement = service.settle("author-1", "2026-09")
    withdrawal = service.withdraw(settlement.id, "author-1", 7_000, "BANK", True)
    service.approve_withdrawal_risk(withdrawal.id, "risk-1")
    payout = service.approve_withdrawal_finance(withdrawal.id, "finance-1")

    failed = provider.generate_callback_event(payout.payout_no, ProviderStatus.REJECTED)
    assert service.handle_payout_provider_event(failed).status is PayoutStatus.REJECTED


def test_sql_payout_rejects_same_reviewer_for_risk_and_finance() -> None:
    service, _, _ = _service()
    contract = service.create_contract("author-1", "book-1", 7000)
    approved = service.approve_contract(contract.id, "finance-maker")
    service.sign_contract(contract.id, "author-1")
    service.activate_contract(approved.id)
    revenue = service.record_revenue("author-1", "VIP", "purchase-maker-checker", 10_000, 7000)
    service.confirm_revenue(revenue.id)
    settlement = service.settle("author-1", "2026-09")
    withdrawal = service.withdraw(settlement.id, "author-1", 7_000, "BANK", True)

    service.approve_withdrawal_risk(withdrawal.id, "same-staff")
    with pytest.raises(ValueError, match="MAKER_CHECKER_REQUIRED"):
        service.approve_withdrawal_finance(withdrawal.id, "same-staff")


def test_sql_payout_terminal_status_cannot_regress_to_processing() -> None:
    service, provider, _ = _service()
    contract = service.create_contract("author-1", "book-1", 7000)
    approved = service.approve_contract(contract.id, "finance-maker")
    service.sign_contract(contract.id, "author-1")
    service.activate_contract(approved.id)
    revenue = service.record_revenue("author-1", "VIP", "purchase-3", 10_000, 7000)
    service.confirm_revenue(revenue.id)
    settlement = service.settle("author-1", "2026-09")
    withdrawal = service.withdraw(settlement.id, "author-1", 7_000, "BANK", True)
    service.approve_withdrawal_risk(withdrawal.id, "risk-1")
    payout = service.approve_withdrawal_finance(withdrawal.id, "finance-1")

    rejected = provider.generate_callback_event(payout.payout_no, ProviderStatus.REJECTED)
    assert service.handle_payout_provider_event(rejected).status is PayoutStatus.REJECTED
    processing = provider.generate_callback_event(payout.payout_no, ProviderStatus.PROCESSING)
    with pytest.raises(ValueError, match="PAYOUT_STATE_CONFLICT"):
        service.handle_payout_provider_event(processing)


def test_sql_payout_provider_callback_accepts_naive_event_datetime() -> None:
    service, provider, _ = _service()
    provider._clock = lambda: datetime.fromisoformat("2026-09-05T12:00:00")
    contract = service.create_contract("author-1", "book-1", 7000)
    approved = service.approve_contract(contract.id, "finance-maker")
    service.sign_contract(contract.id, "author-1")
    service.activate_contract(approved.id)
    revenue = service.record_revenue("author-1", "VIP", "purchase-naive", 10_000, 7000)
    service.confirm_revenue(revenue.id)
    settlement = service.settle("author-1", "2026-09")
    withdrawal = service.withdraw(settlement.id, "author-1", 7_000, "BANK", True)
    service.approve_withdrawal_risk(withdrawal.id, "risk-1")
    payout = service.approve_withdrawal_finance(withdrawal.id, "finance-1")

    event = provider.generate_callback_event(payout.payout_no, ProviderStatus.SUCCESS)
    assert (
        service.handle_payout_provider_event(event, now=datetime(2026, 9, 5, 12, tzinfo=UTC)).status
        is PayoutStatus.SUCCESS
    )


def test_sql_payout_rejects_provider_transaction_reuse_across_orders() -> None:
    service, provider, _ = _service()
    contract = service.create_contract("author-1", "book-1", 7000)
    approved = service.approve_contract(contract.id, "finance-maker")
    service.sign_contract(contract.id, "author-1")
    service.activate_contract(approved.id)
    revenue = service.record_revenue("author-1", "VIP", "purchase-transaction-reuse", 20_000, 7000)
    service.confirm_revenue(revenue.id)
    settlement = service.settle("author-1", "2026-09")
    first_withdrawal = service.withdraw(settlement.id, "author-1", 7_000, "BANK", True)
    second_withdrawal = service.withdraw(settlement.id, "author-1", 7_000, "BANK", True)
    service.approve_withdrawal_risk(first_withdrawal.id, "risk-1")
    first_payout = service.approve_withdrawal_finance(first_withdrawal.id, "finance-1")
    service.approve_withdrawal_risk(second_withdrawal.id, "risk-2")
    second_payout = service.approve_withdrawal_finance(second_withdrawal.id, "finance-2")

    first_event = provider.generate_callback_event(first_payout.payout_no, ProviderStatus.SUCCESS)
    assert service.handle_payout_provider_event(first_event).status is PayoutStatus.SUCCESS
    reused_event = provider.generate_callback_event(
        second_payout.payout_no,
        ProviderStatus.SUCCESS,
        event_id="provider-reused-event",
    )
    reused_event = replace(
        reused_event, provider_transaction_id=first_event.provider_transaction_id
    )
    reused_event = replace(
        reused_event,
        signature=_event_signature("payout-secret", replace(reused_event, signature="")),
    )
    with pytest.raises(ValueError, match="PAYOUT_PROVIDER_TRANSACTION_CONFLICT"):
        service.handle_payout_provider_event(reused_event)
