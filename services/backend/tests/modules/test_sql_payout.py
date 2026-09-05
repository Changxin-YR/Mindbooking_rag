import pytest
import sqlalchemy as sa

from novel_platform.modules.author_finance.domain import PayoutStatus
from novel_platform.modules.author_finance.sql_service import SqlAuthorFinanceService
from novel_platform.modules.payment import ProviderStatus, SandboxPayoutProvider


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
    service.activate_contract(service.approve_contract(contract.id, "finance-maker").id)
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
    service.activate_contract(service.approve_contract(contract.id, "finance-maker").id)
    revenue = service.record_revenue("author-1", "VIP", "purchase-2", 10_000, 7000)
    service.confirm_revenue(revenue.id)
    settlement = service.settle("author-1", "2026-09")
    withdrawal = service.withdraw(settlement.id, "author-1", 7_000, "BANK", True)
    service.approve_withdrawal_risk(withdrawal.id, "risk-1")
    payout = service.approve_withdrawal_finance(withdrawal.id, "finance-1")

    failed = provider.generate_callback_event(payout.payout_no, ProviderStatus.REJECTED)
    assert service.handle_payout_provider_event(failed).status is PayoutStatus.REJECTED
