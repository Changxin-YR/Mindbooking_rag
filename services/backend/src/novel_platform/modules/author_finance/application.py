from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from novel_platform.modules.author_finance.domain import (
    DEFAULT_AUTHOR_SHARE_BPS,
    DEFAULT_POLICY_VERSION,
    DEFAULT_TAX_FREE_THRESHOLD_CENTS,
    DEFAULT_TAX_WITHHOLDING_BPS,
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
    period_bounds,
    render_virtual_contract,
)
from novel_platform.modules.payment import PayoutProvider, ProviderEvent


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


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
        self._risk_approved_withdrawals: dict[str, str] = {}
        self._finance_approved_withdrawals: dict[str, str] = {}
        self.payout_provider = payout_provider
        self.payout_provider_secret = payout_provider_secret

    def create_contract(
        self, author_id: str, book_id: str, share_bps: int | None = None
    ) -> Contract:
        effective_share = DEFAULT_AUTHOR_SHARE_BPS if share_bps is None else share_bps
        if not 0 < effective_share <= 10000:
            raise ValueError("INVALID_REVENUE_SHARE_BPS")
        contract = Contract(_id("CTR"), author_id, book_id, policy_version=DEFAULT_POLICY_VERSION)
        version = ContractVersion(
            _id("CTV"),
            contract.id,
            1,
            effective_share,
            DEFAULT_POLICY_VERSION,
            DEFAULT_TAX_WITHHOLDING_BPS,
            DEFAULT_TAX_FREE_THRESHOLD_CENTS,
        )
        document_text, document_hash = render_virtual_contract(
            contract_id=contract.id,
            author_id=author_id,
            book_id=book_id,
            version=version.version,
            revenue_share_bps=version.revenue_share_bps,
            policy_version=version.policy_version,
            tax_withholding_bps=version.tax_withholding_bps,
            tax_free_threshold_cents=version.tax_free_threshold_cents,
        )
        version = replace(version, document_text=document_text, document_hash=document_hash)
        contract.document_text = document_text
        contract.document_hash = document_hash
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

    def get_contract(self, contract_id: str) -> Contract:
        return self.contracts[contract_id]

    def list_contracts(
        self,
        *,
        author_id: str | None = None,
        status: str | None = None,
    ) -> list[Contract]:
        """Return the contract inbox without exposing mutable domain state."""
        normalized_author = author_id.strip() if author_id is not None else None
        normalized_status = status.strip().upper() if status is not None else None
        allowed_statuses = {item.value for item in ContractStatus}
        if normalized_author == "":
            raise ValueError("AUTHOR_ID_REQUIRED")
        if normalized_status not in {None, *allowed_statuses}:
            raise ValueError("CONTRACT_STATUS_INVALID")
        # Dict insertion order is the in-memory equivalent of SQL's
        # created_at DESC ordering; UUID lexical order is intentionally not
        # used because it is unrelated to creation order.
        return [
            item
            for item in reversed(tuple(self.contracts.values()))
            if (normalized_author is None or item.author_id == normalized_author)
            and (normalized_status is None or item.status.value == normalized_status)
        ]

    def activate_contract(self, contract_id: str) -> Contract:
        contract = self.contracts[contract_id]
        if contract.status is not ContractStatus.APPROVED:
            raise ValueError("CONTRACT_NOT_APPROVED")
        if contract.signature_hash is None:
            raise ValueError("CONTRACT_SIGNATURE_REQUIRED")
        contract.status = ContractStatus.ACTIVE
        return contract

    def sign_contract(self, contract_id: str, signer_id: str) -> Contract:
        signer_id = signer_id.strip()
        if not signer_id:
            raise ValueError("SIGNER_ID_REQUIRED")
        contract = self.contracts[contract_id]
        if contract.status is not ContractStatus.APPROVED:
            raise ValueError("CONTRACT_NOT_APPROVED")
        if contract.signed_by is not None:
            if contract.signed_by != signer_id:
                raise ValueError("CONTRACT_SIGNATURE_CONFLICT")
            return contract
        signed_at = datetime.now(UTC)
        signature_hash = sha256(
            f"{contract.id}:{contract.document_hash}:{signer_id}:{signed_at.isoformat()}".encode()
        ).hexdigest()
        contract.signed_by = signer_id
        contract.signed_at = signed_at
        contract.signature_hash = signature_hash
        return contract

    def record_revenue(
        self,
        author_id: str,
        source: str,
        source_ref: str,
        gross_cents: int,
        share_bps: int | None = None,
        book_id: str | None = None,
    ) -> RevenueEntry:
        if gross_cents <= 0 or (share_bps is not None and not 0 <= share_bps <= 10000):
            raise ValueError("INVALID_REVENUE_AMOUNT")
        for entry in self.revenue.values():
            if entry.source_ref == source_ref:
                if (
                    entry.author_id != author_id
                    or entry.gross_cents != gross_cents
                    or (
                        share_bps is not None
                        and entry.author_cents != gross_cents * share_bps // 10000
                    )
                ):
                    raise ValueError("REVENUE_SOURCE_CONFLICT")
                return entry
        policy_version: str | None = None
        tax_withholding_bps = 0
        tax_free_threshold_cents = 0
        effective_share = share_bps
        if effective_share is None:
            active_contracts = [
                item
                for item in self.contracts.values()
                if item.author_id == author_id
                and item.status is ContractStatus.ACTIVE
                and (book_id is None or item.book_id == book_id)
            ]
            if book_id is None and len(active_contracts) > 1:
                raise ValueError("BOOK_ID_REQUIRED_FOR_CONTRACT_POLICY")
            active = active_contracts[0] if active_contracts else None
            if active is not None:
                version = self.contract_versions[active.version_ids[-1]]
                effective_share = version.revenue_share_bps
                policy_version = version.policy_version
                tax_withholding_bps = version.tax_withholding_bps
                tax_free_threshold_cents = version.tax_free_threshold_cents
            else:
                effective_share = DEFAULT_AUTHOR_SHARE_BPS
        author_cents = gross_cents * effective_share // 10000
        tax_base = max(0, author_cents - tax_free_threshold_cents)
        tax_cents = tax_base * tax_withholding_bps // 10000
        entry = RevenueEntry(
            _id("REV"),
            author_id,
            source,
            source_ref,
            gross_cents,
            author_cents,
            tax_cents=tax_cents,
            net_author_cents=author_cents - tax_cents,
            policy_version=policy_version,
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
        start, end = period_bounds(period)
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
            if item.author_id == author_id
            and item.status is RevenueStatus.CONFIRMED
            and start <= _utc(item.created_at) < end
        ]
        settlement = Settlement(
            _id("SET"),
            author_id,
            period,
            sum(
                item.net_author_cents if item.net_author_cents is not None else item.author_cents
                for item in eligible
            ),
            gross_cents=sum(item.gross_cents for item in eligible),
            tax_cents=sum(item.tax_cents for item in eligible),
        )
        settlement.status = SettlementStatus.LOCKED
        settlement.status = SettlementStatus.WITHDRAWABLE
        self.settlements[settlement.id] = settlement
        for item in eligible:
            item.status = RevenueStatus.SETTLED
            item.settlement_id = settlement.id
        return settlement

    def list_settlements(self, author_id: str) -> list[Settlement]:
        if not author_id.strip():
            raise ValueError("AUTHOR_ID_REQUIRED")
        return sorted(
            (item for item in self.settlements.values() if item.author_id == author_id),
            key=lambda item: (item.period, item.id),
            reverse=True,
        )

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
        reviewer_id = reviewer_id.strip()
        if not reviewer_id:
            raise ValueError("REVIEWER_ID_REQUIRED")
        withdrawal = self.withdrawals[withdrawal_id]
        if withdrawal.status is not WithdrawalStatus.PENDING:
            raise ValueError("WITHDRAWAL_NOT_REVIEWABLE")
        if withdrawal_id in self._risk_approved_withdrawals:
            return withdrawal
        if self._finance_approved_withdrawals.get(withdrawal_id) == reviewer_id:
            raise ValueError("MAKER_CHECKER_REQUIRED")
        self._risk_approved_withdrawals[withdrawal_id] = reviewer_id
        return withdrawal

    def approve_withdrawal_finance(self, withdrawal_id: str, reviewer_id: str) -> PayoutOrder:
        reviewer_id = reviewer_id.strip()
        if not reviewer_id:
            raise ValueError("REVIEWER_ID_REQUIRED")
        withdrawal = self.withdrawals[withdrawal_id]
        if withdrawal_id not in self._risk_approved_withdrawals:
            raise ValueError("PAYOUT_REVIEW_REQUIRED")
        existing = next(
            (item for item in self.payout_orders.values() if item.withdrawal_id == withdrawal_id),
            None,
        )
        if existing is not None:
            return existing
        if self._risk_approved_withdrawals.get(withdrawal_id) == reviewer_id:
            raise ValueError("MAKER_CHECKER_REQUIRED")
        provider = getattr(self, "payout_provider", None)
        secret = getattr(self, "payout_provider_secret", "")
        if provider is None or not secret:
            raise ValueError("PAYOUT_PROVIDER_NOT_CONFIGURED")
        self._finance_approved_withdrawals[withdrawal_id] = reviewer_id
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
        if (
            not isinstance(event.provider_transaction_id, str)
            or not event.provider_transaction_id.strip()
        ):
            raise ValueError("PAYOUT_PROVIDER_TRANSACTION_ID_REQUIRED")
        provider_name = getattr(provider, "provider_name", event.provider)
        if event.provider != provider_name:
            raise ValueError("PAYOUT_PROVIDER_MISMATCH")
        if not event.verify_signature(secret):
            raise ValueError("PAYOUT_SIGNATURE_INVALID")
        if _utc(event.available_at) > _utc(now or datetime.now(UTC)):
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
        if payout.status in (
            PayoutStatus.SUCCESS,
            PayoutStatus.FAILED,
            PayoutStatus.REJECTED,
            PayoutStatus.TIMEOUT,
        ):
            raise ValueError("PAYOUT_STATE_CONFLICT")
        if (
            payout.provider_transaction_id is not None
            and payout.provider_transaction_id != event.provider_transaction_id
        ):
            raise ValueError("PAYOUT_PROVIDER_TRANSACTION_CONFLICT")
        if any(
            item.id != payout.id
            and item.provider == event.provider
            and item.provider_transaction_id == event.provider_transaction_id
            for item in self.payout_orders.values()
        ):
            raise ValueError("PAYOUT_PROVIDER_TRANSACTION_CONFLICT")
        if any(
            item.id != payout.id
            and item.provider == event.provider
            and item.provider_event_id == event.event_id
            for item in self.payout_orders.values()
        ):
            raise ValueError("PAYOUT_PROVIDER_EVENT_CONFLICT")
        updated = replace(
            payout,
            status=PayoutStatus(event.status.value),
            provider_event_id=event.event_id,
            provider_transaction_id=event.provider_transaction_id,
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

    def payout_details(self, payout_no: str) -> tuple[int, str, str]:
        payout = next(
            (item for item in self.payout_orders.values() if item.payout_no == payout_no),
            None,
        )
        if payout is None:
            raise ValueError("PAYOUT_NOT_FOUND")
        return payout.amount_cents, payout.currency, payout.destination

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
