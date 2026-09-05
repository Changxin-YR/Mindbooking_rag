import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.author_finance.domain import (
    ContractStatus,
    RevenueStatus,
    SettlementStatus,
)
from novel_platform.modules.author_finance.sql_service import SqlAuthorFinanceService


def _engine() -> sa.Engine:
    metadata = sa.MetaData()
    contracts = sa.Table(
        "contracts",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "contract_versions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("contract_id", sa.String(64), sa.ForeignKey(contracts.c.id), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("revenue_share_bps", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("contract_id", "version"),
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
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "author_settlements",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("period", sa.String(32), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("withdrawn_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("author_id", "period"),
    )
    settlements = metadata.tables["author_settlements"]
    sa.Table(
        "withdrawal_requests",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("settlement_id", sa.String(64), sa.ForeignKey(settlements.c.id), nullable=False),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("payout_method", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "chargebacks",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_ref", sa.String(128), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("recovered_cents", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    chargebacks = metadata.tables["chargebacks"]
    sa.Table(
        "financial_recovery_claims",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("chargeback_id", sa.String(64), sa.ForeignKey(chargebacks.c.id), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    return engine


def test_sql_author_finance_survives_rebuild_and_preserves_idempotency() -> None:
    engine = _engine()
    service = SqlAuthorFinanceService(engine)
    contract = service.create_contract("author-1", "book-1", 7000)
    assert SqlAuthorFinanceService(engine).get_contract(contract.id).status is ContractStatus.DRAFT
    with pytest.raises(ValueError, match="MAKER_CHECKER_REQUIRED"):
        service.approve_contract(contract.id, "author-1")
    service.activate_contract(service.approve_contract(contract.id, "staff-1").id)

    first = service.record_revenue("author-1", "VIP", "payment-1", 10000, 7000)
    rebuilt = SqlAuthorFinanceService(engine)
    assert rebuilt.record_revenue("author-1", "VIP", "payment-1", 10000, 7000).id == first.id
    assert rebuilt.confirm_revenue(first.id).status is RevenueStatus.CONFIRMED
    settlement = rebuilt.settle("author-1", "2026-09")
    assert settlement.amount_cents == 7000
    assert settlement.status is SettlementStatus.WITHDRAWABLE
    assert rebuilt.withdraw(settlement.id, "author-1", 7000, "BANK", True).amount_cents == 7000

    first_chargeback = rebuilt.chargeback("payment-1", 10000)
    second_chargeback = rebuilt.chargeback("payment-1", 10000)
    assert first_chargeback.recovered_cents == 7000
    assert second_chargeback.recovered_cents == 0
