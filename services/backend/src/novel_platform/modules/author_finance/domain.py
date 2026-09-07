import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256

DEFAULT_POLICY_VERSION = "SANDBOX_CN_2026_V1"
DEFAULT_AUTHOR_SHARE_BPS = 7000
DEFAULT_TAX_WITHHOLDING_BPS = 1000
DEFAULT_TAX_FREE_THRESHOLD_CENTS = 100_000


def render_virtual_contract(
    *,
    contract_id: str,
    author_id: str,
    book_id: str,
    version: int,
    revenue_share_bps: int,
    policy_version: str,
    tax_withholding_bps: int,
    tax_free_threshold_cents: int,
) -> tuple[str, str]:
    """Render the deterministic sandbox agreement and its content hash."""
    text = "\n".join(
        (
            "墨页平台虚拟数字内容合作合同",
            f"合同编号：{contract_id}",
            f"作者账号：{author_id}",
            f"作品编号：{book_id}",
            f"合同版本：{version}",
            f"作者分成：{revenue_share_bps} BPS",
            f"税务政策：{policy_version}",
            f"预扣税率：{tax_withholding_bps} BPS",
            f"免征阈值：{tax_free_threshold_cents} 分",
            "本合同为本地/Staging 沙盒演示文本，不构成正式法律、税务或生产结算依据。",
        )
    )
    return text, sha256(text.encode("utf-8")).hexdigest()


def period_bounds(period: str) -> tuple[datetime, datetime]:
    """Return the inclusive start/exclusive end for a YYYY-MM settlement period."""
    if not isinstance(period, str) or re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period) is None:
        raise ValueError("INVALID_SETTLEMENT_PERIOD")
    year, month = (int(part) for part in period.split("-"))
    start = datetime(year, month, 1, tzinfo=UTC)
    end = (
        datetime(year + 1, 1, 1, tzinfo=UTC)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=UTC)
    )
    return start, end


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


class PayoutStatus(StrEnum):
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"


@dataclass(slots=True)
class Contract:
    id: str
    author_id: str
    book_id: str
    status: ContractStatus = ContractStatus.DRAFT
    version_ids: list[str] = field(default_factory=list)
    policy_version: str = DEFAULT_POLICY_VERSION
    document_text: str = ""
    document_hash: str = ""
    signed_by: str | None = None
    signed_at: datetime | None = None
    signature_hash: str | None = None


@dataclass(frozen=True, slots=True)
class ContractVersion:
    id: str
    contract_id: str
    version: int
    revenue_share_bps: int
    policy_version: str = DEFAULT_POLICY_VERSION
    tax_withholding_bps: int = DEFAULT_TAX_WITHHOLDING_BPS
    tax_free_threshold_cents: int = DEFAULT_TAX_FREE_THRESHOLD_CENTS
    document_text: str = ""
    document_hash: str = ""


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
    tax_cents: int = 0
    net_author_cents: int | None = None
    policy_version: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class Settlement:
    id: str
    author_id: str
    period: str
    amount_cents: int
    status: SettlementStatus = SettlementStatus.CONFIRMED
    withdrawn_cents: int = 0
    gross_cents: int = 0
    tax_cents: int = 0


@dataclass(slots=True)
class Withdrawal:
    id: str
    settlement_id: str
    author_id: str
    amount_cents: int
    payout_method: str
    status: WithdrawalStatus = WithdrawalStatus.PENDING


@dataclass(frozen=True, slots=True)
class PayoutOrder:
    id: str
    withdrawal_id: str
    payout_no: str
    provider: str
    amount_cents: int
    currency: str
    destination: str
    status: PayoutStatus = PayoutStatus.PROCESSING
    provider_event_id: str | None = None
    provider_transaction_id: str | None = None


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
