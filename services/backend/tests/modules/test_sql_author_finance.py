from datetime import UTC, datetime

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
        sa.Column("signed_by", sa.String(64)),
        sa.Column("signed_at", sa.DateTime),
        sa.Column("signature_hash", sa.String(64)),
    )
    sa.Table(
        "contract_versions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("contract_id", sa.String(64), sa.ForeignKey(contracts.c.id), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("revenue_share_bps", sa.Integer, nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("tax_withholding_bps", sa.Integer, nullable=False),
        sa.Column("tax_free_threshold_cents", sa.BigInteger, nullable=False),
        sa.Column("document_text", sa.Text, nullable=False),
        sa.Column("document_hash", sa.String(64), nullable=False),
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
        sa.Column("tax_cents", sa.BigInteger),
        sa.Column("net_author_cents", sa.BigInteger),
        sa.Column("policy_version", sa.String(64)),
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
        sa.Column("gross_cents", sa.BigInteger),
        sa.Column("tax_cents", sa.BigInteger),
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
    approved = service.approve_contract(contract.id, "staff-1")
    service.sign_contract(contract.id, "author-1")
    service.activate_contract(approved.id)

    first = service.record_revenue("author-1", "VIP", "payment-1", 10000, 7000)
    rebuilt = SqlAuthorFinanceService(engine)
    assert rebuilt.record_revenue("author-1", "VIP", "payment-1", 10000, 7000).id == first.id
    with pytest.raises(ValueError, match="REVENUE_SOURCE_CONFLICT"):
        rebuilt.record_revenue("other-author", "VIP", "payment-1", 10000, 7000)
    assert rebuilt.confirm_revenue(first.id).status is RevenueStatus.CONFIRMED
    settlement = rebuilt.settle("author-1", "2026-09")
    assert settlement.amount_cents == 7000
    assert settlement.status is SettlementStatus.WITHDRAWABLE
    assert rebuilt.withdraw(settlement.id, "author-1", 7000, "BANK", True).amount_cents == 7000

    first_chargeback = rebuilt.chargeback("payment-1", 10000)
    second_chargeback = rebuilt.chargeback("payment-1", 10000)
    assert first_chargeback.recovered_cents == 7000
    assert second_chargeback.recovered_cents == 0


def test_sql_virtual_policy_snapshot_calculates_tax_and_net_settlement() -> None:
    engine = _engine()
    service = SqlAuthorFinanceService(engine)
    contract = service.create_contract("author-tax", "book-tax")
    approved = service.approve_contract(contract.id, "staff-1")
    service.sign_contract(contract.id, "author-tax")
    service.activate_contract(approved.id)

    revenue = service.record_revenue("author-tax", "VIP", "tax-source", 200_000)

    assert revenue.policy_version == "SANDBOX_CN_2026_V1"
    assert revenue.tax_cents == 4_000
    service.confirm_revenue(revenue.id)
    settlement = service.settle("author-tax", "2026-09")
    assert settlement.amount_cents == 136_000
    assert settlement.gross_cents == 200_000
    assert settlement.tax_cents == 4_000


def test_sql_contract_document_is_persisted_and_rebuilt() -> None:
    engine = _engine()
    service = SqlAuthorFinanceService(engine)
    contract = service.create_contract("author-doc", "book-doc")
    rebuilt = SqlAuthorFinanceService(engine).get_contract(contract.id)

    assert rebuilt.document_text == contract.document_text
    assert rebuilt.document_hash == contract.document_hash
    assert "SANDBOX_CN_2026_V1" in rebuilt.document_text
    assert len(rebuilt.document_hash) == 64


def test_sql_contract_signature_is_required_and_idempotent() -> None:
    engine = _engine()
    service = SqlAuthorFinanceService(engine)
    contract = service.create_contract("author-sign", "book-sign")
    service.approve_contract(contract.id, "staff-maker")

    with pytest.raises(ValueError, match="CONTRACT_SIGNATURE_REQUIRED"):
        service.activate_contract(contract.id)

    signed = service.sign_contract(contract.id, "author-sign")
    repeated = service.sign_contract(contract.id, "author-sign")
    assert repeated.signature_hash == signed.signature_hash
    assert repeated.signed_by == "author-sign"
    assert repeated.signed_at is not None

    with pytest.raises(ValueError, match="CONTRACT_SIGNATURE_CONFLICT"):
        service.sign_contract(contract.id, "other-author")

    activated = service.activate_contract(contract.id)
    assert activated.status is ContractStatus.ACTIVE


def test_sql_contract_inbox_filters_and_rebuilds_documents() -> None:
    engine = _engine()
    service = SqlAuthorFinanceService(engine)
    draft = service.create_contract("author-inbox", "book-draft")
    approved = service.create_contract("author-inbox", "book-approved")
    service.approve_contract(approved.id, "staff-1")
    service.create_contract("other-author", "book-other")

    rebuilt = SqlAuthorFinanceService(engine)
    assert [item.id for item in rebuilt.list_contracts(author_id="author-inbox")] == [
        approved.id,
        draft.id,
    ]
    filtered = rebuilt.list_contracts(status="APPROVED")
    assert [item.id for item in filtered] == [approved.id]
    assert filtered[0].document_hash == approved.document_hash
    with pytest.raises(ValueError, match="CONTRACT_STATUS_INVALID"):
        rebuilt.list_contracts(status="UNKNOWN")


def test_sql_settlement_only_includes_revenue_created_in_requested_period() -> None:
    engine = _engine()
    service = SqlAuthorFinanceService(engine)
    september = service.record_revenue("author-period", "VIP", "period-september", 10_000, 7000)
    october = service.record_revenue("author-period", "VIP", "period-october", 20_000, 7000)
    with engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE author_revenue_entries SET created_at = :created_at WHERE id = :id"),
            {"created_at": datetime(2026, 9, 15, tzinfo=UTC), "id": september.id},
        )
        connection.execute(
            sa.text("UPDATE author_revenue_entries SET created_at = :created_at WHERE id = :id"),
            {"created_at": datetime(2026, 10, 15, tzinfo=UTC), "id": october.id},
        )
    service.confirm_revenue(september.id)
    service.confirm_revenue(october.id)

    settlement = service.settle("author-period", "2026-09")

    assert settlement.amount_cents == september.net_author_cents
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.select(service._revenue.c.status).where(service._revenue.c.id == october.id)
            ).scalar_one()
            == "CONFIRMED"
        )


def test_sql_manual_revenue_uses_book_contract_and_rejects_ambiguous_author_policy() -> None:
    engine = _engine()
    service = SqlAuthorFinanceService(engine)
    first = service.create_contract("author-books", "book-a", 5_000)
    second = service.create_contract("author-books", "book-b", 8_000)
    first_approved = service.approve_contract(first.id, "staff-maker")
    service.sign_contract(first.id, "author-books")
    service.activate_contract(first_approved.id)
    second_approved = service.approve_contract(second.id, "staff-maker")
    service.sign_contract(second.id, "author-books")
    service.activate_contract(second_approved.id)

    first_revenue = service.record_revenue(
        "author-books", "MANUAL", "manual-book-a", 10_000, book_id="book-a"
    )
    second_revenue = service.record_revenue(
        "author-books", "MANUAL", "manual-book-b", 10_000, book_id="book-b"
    )

    assert first_revenue.author_cents == 5_000
    assert second_revenue.author_cents == 8_000
    with pytest.raises(ValueError, match="BOOK_ID_REQUIRED_FOR_CONTRACT_POLICY"):
        service.record_revenue("author-books", "MANUAL", "manual-ambiguous", 10_000)
