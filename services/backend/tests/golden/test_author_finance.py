from datetime import UTC, datetime

import pytest

from novel_platform.modules.author_finance.application import AuthorFinanceService
from novel_platform.modules.author_finance.domain import RevenueStatus, render_virtual_contract
from novel_platform.modules.payment import SandboxPayoutProvider


def test_contract_requires_checker_and_revenue_is_idempotent() -> None:
    service = AuthorFinanceService()
    contract = service.create_contract("author-1", "book-1", 7000)
    with pytest.raises(ValueError, match="MAKER_CHECKER_REQUIRED"):
        service.approve_contract(contract.id, "author-1")
    approved = service.approve_contract(contract.id, "staff-1")
    service.sign_contract(contract.id, "author-1")
    service.activate_contract(approved.id)
    first = service.record_revenue("author-1", "VIP", "payment-1", 10000, 7000)
    assert service.record_revenue("author-1", "VIP", "payment-1", 10000, 7000) is first
    with pytest.raises(ValueError, match="REVENUE_SOURCE_CONFLICT"):
        service.record_revenue("other-author", "VIP", "payment-1", 10000, 7000)


def test_contract_inbox_filters_by_author_and_status() -> None:
    service = AuthorFinanceService()
    draft = service.create_contract("author-a", "book-a")
    approved = service.create_contract("author-a", "book-b")
    service.approve_contract(approved.id, "staff-1")
    service.create_contract("author-b", "book-c")

    assert [item.id for item in service.list_contracts(author_id="author-a")] == [
        approved.id,
        draft.id,
    ]
    assert [item.id for item in service.list_contracts(status="APPROVED")] == [approved.id]
    with pytest.raises(ValueError, match="CONTRACT_STATUS_INVALID"):
        service.list_contracts(status="UNKNOWN")


def test_locked_settlement_requires_real_name_and_chargeback_never_creates_negative_recovery() -> (
    None
):
    service = AuthorFinanceService()
    revenue = service.record_revenue("author-1", "VIP", "payment-1", 10000, 7000)
    service.confirm_revenue(revenue.id)
    settlement = service.settle("author-1", "2026-09")
    with pytest.raises(ValueError, match="PAYOUT_HOLDER_MISMATCH"):
        service.withdraw(settlement.id, "author-1", 1000, "BANK", False)
    service.withdraw(settlement.id, "author-1", 7000, "BANK", True)
    first = service.chargeback("payment-1", 10000)
    second = service.chargeback("payment-1", 10000)
    assert first.recovered_cents == 7000
    assert second.recovered_cents == 0
    assert service.revenue[revenue.id].author_cents == 7000
    assert service.recovery_claims


def test_virtual_contract_policy_applies_tax_above_threshold() -> None:
    service = AuthorFinanceService()
    contract = service.create_contract("author-tax", "book-tax")
    version = service.contract_versions[contract.version_ids[0]]
    assert version.policy_version == "SANDBOX_CN_2026_V1"
    assert version.revenue_share_bps == 7000
    assert version.tax_withholding_bps == 1000
    assert "SANDBOX_CN_2026_V1" in version.document_text
    assert len(version.document_hash) == 64
    assert contract.document_hash == version.document_hash

    approved = service.approve_contract(contract.id, "staff-1")
    service.sign_contract(contract.id, "author-tax")
    service.activate_contract(approved.id)
    revenue = service.record_revenue("author-tax", "VIP", "tax-source", 200_000)

    assert revenue.author_cents == 140_000
    assert revenue.tax_cents == 4_000
    assert revenue.net_author_cents == 136_000
    service.confirm_revenue(revenue.id)
    assert service.settle("author-tax", "2026-09").amount_cents == 136_000


def test_virtual_contract_document_is_deterministic_for_same_inputs() -> None:
    first = render_virtual_contract(
        contract_id="CTR-fixed",
        author_id="author-doc",
        book_id="book-doc",
        version=1,
        revenue_share_bps=7000,
        policy_version="SANDBOX_CN_2026_V1",
        tax_withholding_bps=1000,
        tax_free_threshold_cents=100_000,
    )
    second = render_virtual_contract(
        contract_id="CTR-fixed",
        author_id="author-doc",
        book_id="book-doc",
        version=1,
        revenue_share_bps=7000,
        policy_version="SANDBOX_CN_2026_V1",
        tax_withholding_bps=1000,
        tax_free_threshold_cents=100_000,
    )
    assert first == second
    assert first[0]
    assert len(first[1]) == 64


def test_settlement_only_includes_revenue_created_in_requested_period() -> None:
    service = AuthorFinanceService()
    september = service.record_revenue("author-period", "VIP", "period-september", 10_000, 7000)
    october = service.record_revenue("author-period", "VIP", "period-october", 20_000, 7000)
    september.created_at = datetime(2026, 9, 15, tzinfo=UTC)
    october.created_at = datetime(2026, 10, 15, tzinfo=UTC)
    service.confirm_revenue(september.id)
    service.confirm_revenue(october.id)

    settlement = service.settle("author-period", "2026-09")

    assert settlement.amount_cents == september.net_author_cents
    assert service.revenue[october.id].status is RevenueStatus.CONFIRMED


def test_in_memory_payout_requires_distinct_risk_and_finance_reviewers() -> None:
    service = AuthorFinanceService(SandboxPayoutProvider("payout-secret"), "payout-secret")
    revenue = service.record_revenue("author-payout", "VIP", "payout-source", 10_000, 7000)
    service.confirm_revenue(revenue.id)
    settlement = service.settle("author-payout", "2026-09")
    withdrawal = service.withdraw(settlement.id, "author-payout", 7_000, "BANK", True)

    service.approve_withdrawal_risk(withdrawal.id, "same-staff")
    with pytest.raises(ValueError, match="MAKER_CHECKER_REQUIRED"):
        service.approve_withdrawal_finance(withdrawal.id, "same-staff")
    assert service.approve_withdrawal_finance(withdrawal.id, "finance-staff").amount_cents == 7_000
