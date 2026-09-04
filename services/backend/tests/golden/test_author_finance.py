import pytest

from novel_platform.modules.author_finance.application import AuthorFinanceService


def test_contract_requires_checker_and_revenue_is_idempotent() -> None:
    service = AuthorFinanceService()
    contract = service.create_contract("author-1", "book-1", 7000)
    with pytest.raises(ValueError, match="MAKER_CHECKER_REQUIRED"):
        service.approve_contract(contract.id, "author-1")
    service.activate_contract(service.approve_contract(contract.id, "staff-1").id)
    first = service.record_revenue("author-1", "VIP", "payment-1", 10000, 7000)
    assert service.record_revenue("author-1", "VIP", "payment-1", 10000, 7000) is first


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
