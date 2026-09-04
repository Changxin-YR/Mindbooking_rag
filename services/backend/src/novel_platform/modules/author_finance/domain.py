from dataclasses import dataclass, field
from enum import StrEnum


class ContractStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    TERMINATED = "TERMINATED"


class RevenueStatus(StrEnum):
    ESTIMATED = "ESTIMATED"
    RISK_PENDING = "RISK_PENDING"
    CONFIRMED = "CONFIRMED"
    SETTLED = "SETTLED"
    FROZEN = "FROZEN"
    REVERSED = "REVERSED"


class SettlementStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    LOCKED = "LOCKED"
    WITHDRAWABLE = "WITHDRAWABLE"


class WithdrawalStatus(StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"


@dataclass(slots=True)
class Contract:
    id: str
    author_id: str
    book_id: str
    status: ContractStatus = ContractStatus.DRAFT
    version_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ContractVersion:
    id: str
    contract_id: str
    version: int
    revenue_share_bps: int


@dataclass(slots=True)
class RevenueEntry:
    id: str
    author_id: str
    source: str
    source_ref: str
    gross_cents: int
    author_cents: int
    status: RevenueStatus = RevenueStatus.RISK_PENDING
    settlement_id: str | None = None


@dataclass(slots=True)
class Settlement:
    id: str
    author_id: str
    period: str
    amount_cents: int
    status: SettlementStatus = SettlementStatus.CONFIRMED
    withdrawn_cents: int = 0


@dataclass(slots=True)
class Withdrawal:
    id: str
    settlement_id: str
    author_id: str
    amount_cents: int
    payout_method: str
    status: WithdrawalStatus = WithdrawalStatus.PENDING


@dataclass(slots=True)
class Chargeback:
    id: str
    source_ref: str
    amount_cents: int
    recovered_cents: int


@dataclass(slots=True)
class RecoveryClaim:
    id: str
    author_id: str
    chargeback_id: str
    amount_cents: int
    status: str = "OPEN"
