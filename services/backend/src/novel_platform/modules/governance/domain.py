from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ParameterStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"


class ReconciliationDifference(StrEnum):
    MISSING_LEDGER = "MISSING_LEDGER"
    DUPLICATE = "DUPLICATE"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    REFUND_MISMATCH = "REFUND_MISMATCH"


class ReconciliationStatus(StrEnum):
    OPEN = "OPEN"
    REPAIRED = "REPAIRED"
    CLOSED = "CLOSED"


class OutboxStatus(StrEnum):
    NEW = "NEW"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    FAILED = "FAILED"
    PUBLISHED = "PUBLISHED"


@dataclass(frozen=True, slots=True)
class PrivacyRequest:
    id: str
    account_id: str
    kind: str
    status: str = "OPEN"


@dataclass(frozen=True, slots=True)
class AgreementAcceptance:
    account_id: str
    agreement_code: str
    version: str


@dataclass(slots=True)
class ParameterVersion:
    id: str
    key: str
    value: str
    maker_id: str
    status: ParameterStatus = ParameterStatus.DRAFT
    checker_id: str | None = None
    effective_at: str | None = None


@dataclass(frozen=True, slots=True)
class PaymentCreditPending:
    id: str
    payment_id: str
    account_id: str
    amount_cents: int
    status: str = "CREDIT_PENDING"


@dataclass(frozen=True, slots=True)
class ReconciliationItem:
    id: str
    batch_id: str
    reference: str
    difference: ReconciliationDifference
    amount_cents: int


@dataclass(slots=True)
class ReconciliationBatch:
    id: str
    business_date: str
    status: ReconciliationStatus = ReconciliationStatus.OPEN
    items: list[ReconciliationItem] = field(default_factory=list)


@dataclass(slots=True)
class Emergency:
    id: str
    reason: str
    features: set[str]
    operator_id: str
    status: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    id: str
    event_type: str
    aggregate_id: str
    payload: dict[str, object]
    attempts: int = 0
    status: OutboxStatus = OutboxStatus.PENDING
    available_at: datetime | None = None
    locked_by: str | None = None
    locked_at: datetime | None = None
    last_error: str | None = None
    processed_at: datetime | None = None


@dataclass(slots=True)
class Invoice:
    id: str
    account_id: str
    amount_cents: int
    title: str
    tax_id: str
    status: str = "APPLIED"
    document_id: str | None = None
    reversal_document_id: str | None = None
