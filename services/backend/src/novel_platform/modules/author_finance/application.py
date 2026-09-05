from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from novel_platform.modules.author_finance.domain import (
    Chargeback,
    Contract,
    ContractStatus,
    ContractVersion,
    PayoutOrder,
    PayoutStatus,
    RecoveryClaim,
    RevenueEntry,
    RevenueStatus,
    Settlement,
    SettlementStatus,
    Withdrawal,
    WithdrawalStatus,
)
from novel_platform.modules.payment import PayoutProvider, ProviderEvent


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class AuthorFinanceService:
    def __init__(
        self,
        payout_provider: PayoutProvider | None = None,
        payout_provider_secret: str = "",
    ) -> None:
        self.contracts: dict[str, Contract] = {}
        self.contract_versions: dict[str, ContractVersion] = {}
        self.revenue: dict[str, RevenueEntry] = {}
        self.settlements: dict[str, Settlement] = {}
        self.withdrawals: dict[str, Withdrawal] = {}
        self.chargebacks: dict[str, Chargeback] = {}
        self.recovery_claims: dict[str, RecoveryClaim] = {}
        self.payout_orders: dict[str, PayoutOrder] = {}
        self._risk_approved_withdrawals: set[str] = set()
        self._finance_approved_withdrawals: set[str] = set()
        self.payout_provider = payout_provider
        self.payout_provider_secret = payout_provider_secret

    def create_contract(self, author_id: str, book_id: str, share_bps: int = 7000) -> Contract:
        if not 0 < share_bps <= 10000:
            raise ValueError("INVALID_REVENUE_SHARE_BPS")
        contract = Contract(_id("CTR"), author_id, book_id)
        version = ContractVersion(_id("CTV"), contract.id, 1, share_bps)
        contract.version_ids.append(version.id)
        self.contracts[contract.id] = contract
        self.contract_versions[version.id] = version
        return contract

    def approve_contract(self, contract_id: str, approver_id: str) -> Contract:
        contract = self.contracts[contract_id]
        if contract.author_id == approver_id:
            raise ValueError("MAKER_CHECKER_REQUIRED")
        if contract.status is not ContractStatus.DRAFT:
            raise ValueError("CONTRACT_NOT_DRAFT")
        contract.status = ContractStatus.APPROVED
        return contract

    def activate_contract(self, contract_id: str) -> Contract:
        contract = self.contracts[contract_id]
        if contract.status is not ContractStatus.APPROVED:
            raise ValueError("CONTRACT_NOT_APPROVED")
        contract.status = ContractStatus.ACTIVE
        return contract

    def record_revenue(
        self,
        author_id: str,
        source: str,
        source_ref: str,
        gross_cents: int,
        share_bps: int,
    ) -> RevenueEntry:
        if gross_cents <= 0 or not 0 <= share_bps <= 10000:
            raise ValueError("INVALID_REVENUE_AMOUNT")
        for entry in self.revenue.values():
            if entry.source_ref == source_ref:
                return entry
        entry = RevenueEntry(
            _id("REV"), author_id, source, source_ref, gross_cents, gross_cents * share_bps // 10000
        )
        self.revenue[entry.id] = entry
        return entry

    def confirm_revenue(self, revenue_id: str) -> RevenueEntry:
        entry = self.revenue[revenue_id]
        if entry.status is not RevenueStatus.RISK_PENDING:
            raise ValueError("REVENUE_NOT_PENDING")
        entry.status = RevenueStatus.CONFIRMED
        return entry

    def settle(self, author_id: str, period: str) -> Settlement:
        existing = next(
            (
                item
                for item in self.settlements.values()
                if item.author_id == author_id and item.period == period
            ),
            None,
        )
        if existing is not None:
            return existing
        eligible = [
            item
            for item in self.revenue.values()
            if item.author_id == author_id and item.status is RevenueStatus.CONFIRMED
        ]
        settlement = Settlement(
            _id("SET"), author_id, period, sum(item.author_cents for item in eligible)
        )
        settlement.status = SettlementStatus.LOCKED
        settlement.status = SettlementStatus.WITHDRAWABLE
        self.settlements[settlement.id] = settlement
        for item in eligible:
            item.status = RevenueStatus.SETTLED
            item.settlement_id = settlement.id
        return settlement

    def withdraw(
        self,
        settlement_id: str,
        author_id: str,
        amount_cents: int,
        payout_method: str,
        holder_matches_real_name: bool,
    ) -> Withdrawal:
        settlement = self.settlements[settlement_id]
        if (
            settlement.author_id != author_id
            or settlement.status is not SettlementStatus.WITHDRAWABLE
        ):
            raise ValueError("SETTLEMENT_NOT_WITHDRAWABLE")
        if (
            amount_cents < 1000
            or amount_cents > settlement.amount_cents - settlement.withdrawn_cents
        ):
            raise ValueError("INVALID_WITHDRAWAL_AMOUNT")
        if not holder_matches_real_name:
            raise ValueError("PAYOUT_HOLDER_MISMATCH")
        settlement.withdrawn_cents += amount_cents
        withdrawal = Withdrawal(_id("WD"), settlement_id, author_id, amount_cents, payout_method)
        self.withdrawals[withdrawal.id] = withdrawal
        return withdrawal

    def approve_withdrawal_risk(self, withdrawal_id: str, reviewer_id: str) -> Withdrawal:
        del reviewer_id
        withdrawal = self.withdrawals[withdrawal_id]
        if withdrawal.status is not WithdrawalStatus.PENDING:
            raise ValueError("WITHDRAWAL_NOT_REVIEWABLE")
        self._risk_approved_withdrawals.add(withdrawal_id)
        return withdrawal

    def approve_withdrawal_finance(self, withdrawal_id: str, reviewer_id: str) -> PayoutOrder:
        del reviewer_id
        withdrawal = self.withdrawals[withdrawal_id]
        if withdrawal_id not in self._risk_approved_withdrawals:
            raise ValueError("PAYOUT_REVIEW_REQUIRED")
        existing = next(
            (item for item in self.payout_orders.values() if item.withdrawal_id == withdrawal_id),
            None,
        )
        if existing is not None:
            return existing
        provider = getattr(self, "payout_provider", None)
        secret = getattr(self, "payout_provider_secret", "")
        if provider is None or not secret:
            raise ValueError("PAYOUT_PROVIDER_NOT_CONFIGURED")
        self._finance_approved_withdrawals.add(withdrawal_id)
        payout_no = f"PO-{uuid4().hex}"
        payout = provider.create_payout(
            payout_no, withdrawal.amount_cents, "CNY", withdrawal.payout_method
        )
        result = PayoutOrder(
            id=_id("PAYOUT"),
            withdrawal_id=withdrawal_id,
            payout_no=payout.payout_no,
            provider=payout.provider,
            amount_cents=payout.amount_cents,
            currency=payout.currency,
            destination=payout.destination,
        )
        self.payout_orders[result.id] = result
        return result

    def handle_payout_provider_event(
        self, event: ProviderEvent, *, now: datetime | None = None
    ) -> PayoutOrder:
        provider = getattr(self, "payout_provider", None)
        secret = getattr(self, "payout_provider_secret", "")
        if provider is None or not secret:
            raise ValueError("PAYOUT_PROVIDER_NOT_CONFIGURED")
        if event.event_type != "PAYOUT":
            raise ValueError("PAYOUT_EVENT_TYPE_INVALID")
        provider_name = getattr(provider, "provider_name", event.provider)
        if event.provider != provider_name:
            raise ValueError("PAYOUT_PROVIDER_MISMATCH")
        if not event.verify_signature(secret):
            raise ValueError("PAYOUT_SIGNATURE_INVALID")
        if event.available_at > (now or datetime.now(UTC)):
            raise ValueError("PAYOUT_EVENT_NOT_AVAILABLE")
        payout = next(
            (item for item in self.payout_orders.values() if item.payout_no == event.reference_id),
            None,
        )
        if payout is None:
            raise ValueError("PAYOUT_NOT_FOUND")
        if payout.amount_cents != event.amount_cents or payout.currency != event.currency:
            raise ValueError("PAYOUT_AMOUNT_MISMATCH")
        if payout.provider_event_id == event.event_id:
            return payout
        if payout.status is PayoutStatus.SUCCESS:
            raise ValueError("PAYOUT_STATE_CONFLICT")
        updated = replace(
            payout,
            status=PayoutStatus(event.status.value),
            provider_event_id=event.event_id,
        )
        self.payout_orders[payout.id] = updated
        withdrawal = self.withdrawals[payout.withdrawal_id]
        self.withdrawals[withdrawal.id] = replace(
            withdrawal,
            status=(
                WithdrawalStatus.PAID
                if updated.status is PayoutStatus.SUCCESS
                else WithdrawalStatus.FAILED
                if updated.status
                in (PayoutStatus.FAILED, PayoutStatus.REJECTED, PayoutStatus.TIMEOUT)
                else WithdrawalStatus.PENDING
            ),
        )
        return updated

    def chargeback(self, source_ref: str, amount_cents: int) -> Chargeback:
        if amount_cents <= 0:
            raise ValueError("INVALID_CHARGEBACK_AMOUNT")
        entry = next(
            (item for item in self.revenue.values() if item.source_ref == source_ref), None
        )
        if entry is None:
            raise KeyError(source_ref)
        already_recovered = sum(
            item.recovered_cents
            for item in self.chargebacks.values()
            if item.source_ref == source_ref
        )
        recovered = min(max(0, entry.author_cents - already_recovered), amount_cents)
        chargeback = Chargeback(_id("CB"), source_ref, amount_cents, recovered)
        self.chargebacks[chargeback.id] = chargeback
        if recovered < amount_cents:
            claim = RecoveryClaim(
                _id("CLM"), entry.author_id, chargeback.id, amount_cents - recovered
            )
            self.recovery_claims[claim.id] = claim
        return chargeback
