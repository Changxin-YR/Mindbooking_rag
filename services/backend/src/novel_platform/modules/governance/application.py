from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from novel_platform.modules.governance.domain import (
    AgreementAcceptance,
    Emergency,
    Invoice,
    OutboxEvent,
    OutboxStatus,
    ParameterStatus,
    ParameterVersion,
    PaymentCreditPending,
    PrivacyRequest,
    ReconciliationBatch,
    ReconciliationDifference,
    ReconciliationItem,
    ReconciliationStatus,
)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class GovernanceService:
    def __init__(self) -> None:
        self._privacy: dict[tuple[str, str], PrivacyRequest] = {}
        self._agreements: dict[tuple[str, str, str], AgreementAcceptance] = {}
        self._parameters: dict[str, ParameterVersion] = {}
        self._pending: dict[str, PaymentCreditPending] = {}
        self._batches: dict[str, ReconciliationBatch] = {}
        self._emergencies: dict[str, Emergency] = {}
        self._outbox: dict[str, OutboxEvent] = {}
        self._invoices: dict[str, Invoice] = {}
        self.repair_payment_credit: Callable[[str], object] | None = None

    def open_privacy_request(self, account_id: str, kind: str) -> PrivacyRequest:
        if not account_id.strip() or not kind.strip():
            raise ValueError("PRIVACY_REQUEST_INVALID")
        key = (account_id, kind.upper())
        request = self._privacy.get(key)
        if request is None:
            request = PrivacyRequest(_id("PRV"), account_id, key[1])
            self._privacy[key] = request
        return request

    def accept_agreement(
        self, account_id: str, agreement_code: str, version: str
    ) -> AgreementAcceptance:
        if not account_id.strip() or not agreement_code.strip() or not version.strip():
            raise ValueError("AGREEMENT_VERSION_REQUIRED")
        acceptance = AgreementAcceptance(account_id, agreement_code, version)
        self._agreements[(account_id, agreement_code, version)] = acceptance
        return acceptance

    def draft_parameter(self, key: str, value: str, maker_id: str) -> ParameterVersion:
        if not key.strip() or not value.strip() or not maker_id.strip():
            raise ValueError("PARAMETER_DRAFT_INVALID")
        parameter = ParameterVersion(_id("PARAM"), key, value, maker_id)
        self._parameters[parameter.id] = parameter
        return parameter

    def approve_parameter(self, parameter_id: str, checker_id: str) -> ParameterVersion:
        parameter = self._parameters[parameter_id]
        if parameter.maker_id == checker_id:
            raise ValueError("PARAMETER_MAKER_CHECKER_SEPARATION")
        parameter.status = ParameterStatus.APPROVED
        parameter.checker_id = checker_id
        return parameter

    def activate_parameter(self, parameter_id: str, effective_at: str) -> ParameterVersion:
        parameter = self._parameters[parameter_id]
        if parameter.status is not ParameterStatus.APPROVED or not parameter.checker_id:
            raise ValueError("PARAMETER_CHECKER_REQUIRED")
        if not effective_at.strip():
            raise ValueError("PARAMETER_EFFECTIVE_AT_REQUIRED")
        parameter.status = ParameterStatus.ACTIVE
        parameter.effective_at = effective_at
        return parameter

    def record_payment_credit_failure(
        self, payment_id: str, account_id: str, amount_cents: int
    ) -> PaymentCreditPending:
        if not payment_id.strip() or not account_id.strip() or amount_cents <= 0:
            raise ValueError("PAYMENT_AMOUNT_INVALID")
        pending = self._pending.get(payment_id)
        if pending is None:
            pending = PaymentCreditPending(_id("CREDIT"), payment_id, account_id, amount_cents)
            self._pending[payment_id] = pending
        elif pending.account_id != account_id or pending.amount_cents != amount_cents:
            raise ValueError("PAYMENT_CREDIT_CONFLICT")
        return pending

    def list_payment_credit_pending(
        self, status: str | None = None
    ) -> tuple[PaymentCreditPending, ...]:
        normalized = status.strip().upper() if status else None
        if normalized not in {
            None,
            "CREDIT_PENDING",
            "REPAIRING",
            "REPAIR_REQUIRED",
            "RESOLVED",
        }:
            raise ValueError("PAYMENT_CREDIT_STATUS_INVALID")
        return tuple(
            pending
            for pending in sorted(self._pending.values(), key=lambda item: item.id)
            if normalized is None
            and pending.status in {"CREDIT_PENDING", "REPAIRING", "REPAIR_REQUIRED"}
            or normalized is not None
            and pending.status == normalized
        )

    def retry_payment_credit(self, payment_id: str, actor_id: str) -> PaymentCreditPending:
        if not actor_id.strip():
            raise ValueError("PAYMENT_CREDIT_ACTOR_REQUIRED")
        try:
            pending = self._pending[payment_id]
        except KeyError as exc:
            raise KeyError(payment_id) from exc
        if pending.status == "RESOLVED":
            return pending
        attempted_at = datetime.now(UTC)
        pending.attempts += 1
        pending.last_attempted_at = attempted_at
        pending.repair_actor_id = actor_id.strip()
        repair = self.repair_payment_credit
        if not callable(repair):
            pending.status = "REPAIR_REQUIRED"
            pending.last_error = "CREDIT_REPAIR_PORT_UNAVAILABLE"
            return pending
        try:
            result = repair(payment_id)
            if result is False:
                raise RuntimeError("CREDIT_REPAIR_REJECTED")
        except Exception as exc:  # noqa: BLE001 - preserve repair state for every failure
            pending.status = "REPAIR_REQUIRED"
            pending.last_error = str(exc) or type(exc).__name__
            return pending
        pending.status = "RESOLVED"
        pending.last_error = None
        pending.resolved_at = attempted_at
        return pending

    def auto_repair_payment_credits(self, *, limit: int = 10) -> tuple[PaymentCreditPending, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("PAYMENT_CREDIT_REPAIR_LIMIT_INVALID")
        pending = [
            item
            for item in sorted(self._pending.values(), key=lambda item: item.id)
            if item.status == "CREDIT_PENDING"
        ][:limit]
        return tuple(
            self.retry_payment_credit(item.payment_id, "system-credit-repair") for item in pending
        )

    def open_reconciliation(self, business_date: str) -> ReconciliationBatch:
        existing = next(
            (batch for batch in self._batches.values() if batch.business_date == business_date),
            None,
        )
        if existing is not None:
            return existing
        batch = ReconciliationBatch(_id("RECON"), business_date)
        self._batches[batch.id] = batch
        return batch

    def add_reconciliation_item(
        self,
        batch_id: str,
        reference: str,
        difference: ReconciliationDifference,
        amount_cents: int,
    ) -> ReconciliationItem:
        batch = self._batches[batch_id]
        if amount_cents < 0:
            raise ValueError("RECONCILIATION_AMOUNT_INVALID")
        item = ReconciliationItem(_id("RECON_ITEM"), batch_id, reference, difference, amount_cents)
        batch.items.append(item)
        return item

    def reconciliation_batch(self, batch_id: str) -> ReconciliationBatch:
        return self._batches[batch_id]

    def list_reconciliation_batches(
        self, status: str | None = None
    ) -> tuple[ReconciliationBatch, ...]:
        normalized = status.strip().upper() if status else None
        allowed = {item.value for item in ReconciliationStatus}
        if normalized not in {None, *allowed}:
            raise ValueError("RECONCILIATION_STATUS_INVALID")
        return tuple(
            sorted(
                (
                    batch
                    for batch in self._batches.values()
                    if normalized is None or batch.status.value == normalized
                ),
                key=lambda item: (item.business_date, item.id),
                reverse=True,
            )
        )

    def mark_reconciliation_repaired(self, batch_id: str, operator_id: str) -> ReconciliationBatch:
        if not operator_id.strip():
            raise ValueError("RECONCILIATION_OPERATOR_REQUIRED")
        batch = self._batches[batch_id]
        if batch.status is ReconciliationStatus.OPEN:
            batch.status = ReconciliationStatus.REPAIRED
        return batch

    def close_reconciliation(self, batch_id: str, operator_id: str) -> ReconciliationBatch:
        if not operator_id.strip():
            raise ValueError("RECONCILIATION_OPERATOR_REQUIRED")
        batch = self._batches[batch_id]
        if batch.status is ReconciliationStatus.OPEN:
            raise ValueError("RECONCILIATION_REPAIR_REQUIRED")
        batch.status = ReconciliationStatus.CLOSED
        return batch

    def pause_features(self, reason: str, features: set[str], operator_id: str) -> Emergency:
        if not reason.strip() or not features or not operator_id.strip():
            raise ValueError("EMERGENCY_INVALID")
        emergency = Emergency(_id("EMG"), reason.strip(), set(features), operator_id)
        self._emergencies[emergency.id] = emergency
        return emergency

    def resolve_emergency(self, emergency_id: str, operator_id: str) -> Emergency:
        emergency = self._emergencies[emergency_id]
        if not operator_id.strip():
            raise ValueError("EMERGENCY_OPERATOR_REQUIRED")
        emergency.status = "RESOLVED"
        return emergency

    def is_feature_paused(self, feature: str) -> bool:
        return any(
            emergency.status == "ACTIVE" and feature in emergency.features
            for emergency in self._emergencies.values()
        )

    def enqueue_outbox(
        self, event_type: str, aggregate_id: str, payload: dict[str, object]
    ) -> OutboxEvent:
        event = OutboxEvent(_id("OUTBOX"), event_type, aggregate_id, dict(payload))
        self._outbox[event.id] = event
        return event

    def outbox_event(self, event_id: str) -> OutboxEvent:
        return self._outbox[event_id]

    def claim_outbox(
        self,
        worker_id: str,
        *,
        limit: int = 10,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> tuple[OutboxEvent, ...]:
        if not worker_id.strip() or not 1 <= limit <= 100 or lease_seconds <= 0:
            raise ValueError("OUTBOX_CLAIM_INVALID")
        now = now or datetime.now(UTC)
        claimed: list[OutboxEvent] = []
        for event in sorted(self._outbox.values(), key=lambda item: item.id):
            available = event.available_at is None or event.available_at <= now
            lease_expired = event.locked_at is None or event.locked_at <= now
            if event.status not in {
                OutboxStatus.NEW,
                OutboxStatus.PROCESSING,
                OutboxStatus.PENDING,
                OutboxStatus.FAILED,
                OutboxStatus.CLAIMED,
            }:
                continue
            if not available or not lease_expired:
                continue
            claimed_status = (
                OutboxStatus.PROCESSING
                if event.status in {OutboxStatus.NEW, OutboxStatus.PROCESSING}
                else OutboxStatus.CLAIMED
            )
            updated = replace(
                event,
                status=claimed_status,
                locked_by=worker_id.strip(),
                locked_at=now,
                available_at=now + timedelta(seconds=lease_seconds),
            )
            self._outbox[event.id] = updated
            claimed.append(updated)
            if len(claimed) == limit:
                break
        return tuple(claimed)

    def ack_outbox(
        self, event_id: str, worker_id: str, *, now: datetime | None = None
    ) -> OutboxEvent:
        now = now or datetime.now(UTC)
        event = self._claimed_outbox(event_id, worker_id, now)
        processed_status = (
            OutboxStatus.PROCESSED
            if event.status is OutboxStatus.PROCESSING
            else OutboxStatus.PUBLISHED
        )
        updated = replace(
            event,
            status=processed_status,
            available_at=None,
            locked_by=None,
            locked_at=None,
            processed_at=now,
        )
        self._outbox[event_id] = updated
        return updated

    def fail_outbox(
        self,
        event_id: str,
        worker_id: str,
        error: str,
        *,
        retry_after_seconds: int = 30,
        now: datetime | None = None,
    ) -> OutboxEvent:
        if not error.strip() or retry_after_seconds <= 0:
            raise ValueError("OUTBOX_FAILURE_INVALID")
        now = now or datetime.now(UTC)
        event = self._claimed_outbox(event_id, worker_id, now)
        updated = replace(
            event,
            attempts=event.attempts + 1,
            status=OutboxStatus.FAILED,
            available_at=now + timedelta(seconds=retry_after_seconds),
            locked_by=None,
            locked_at=None,
            last_error=error.strip(),
        )
        self._outbox[event_id] = updated
        return updated

    def _claimed_outbox(
        self, event_id: str, worker_id: str, now: datetime | None = None
    ) -> OutboxEvent:
        if not worker_id.strip():
            raise ValueError("OUTBOX_WORKER_REQUIRED")
        event = self._outbox[event_id]
        if (
            event.status
            not in {
                OutboxStatus.CLAIMED,
                OutboxStatus.PROCESSING,
            }
            or event.locked_by != worker_id.strip()
        ):
            raise ValueError("OUTBOX_CLAIM_REQUIRED")
        if event.available_at is not None and event.available_at <= (now or datetime.now(UTC)):
            raise ValueError("OUTBOX_CLAIM_REQUIRED")
        return event

    def dispatch_outbox(
        self,
        worker_id: str,
        publisher: Callable[[OutboxEvent], object],
        *,
        limit: int = 10,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> tuple[OutboxEvent, ...]:
        now = now or datetime.now(UTC)
        published: list[OutboxEvent] = []
        for event in self.claim_outbox(
            worker_id, limit=limit, lease_seconds=lease_seconds, now=now
        ):
            try:
                publisher(event)
            except Exception as exc:  # noqa: BLE001 - every publisher failure must be retried
                self.fail_outbox(event.id, worker_id, str(exc) or type(exc).__name__, now=now)
            else:
                published.append(self.ack_outbox(event.id, worker_id, now=now))
        return tuple(published)

    def request_invoice(
        self, account_id: str, amount_cents: int, title: str, tax_id: str
    ) -> Invoice:
        if amount_cents <= 0 or not account_id.strip() or not title.strip() or not tax_id.strip():
            raise ValueError("INVOICE_INVALID")
        invoice = Invoice(_id("INV"), account_id, amount_cents, title.strip(), tax_id.strip())
        self._invoices[invoice.id] = invoice
        return invoice

    def issue_invoice(self, invoice_id: str, document_id: str) -> Invoice:
        invoice = self._invoices[invoice_id]
        if invoice.status != "APPLIED":
            raise ValueError("INVOICE_STATUS_INVALID")
        if not document_id.strip():
            raise ValueError("INVOICE_DOCUMENT_REQUIRED")
        invoice.status = "ISSUED"
        invoice.document_id = document_id
        return invoice

    def reverse_invoice(self, invoice_id: str, document_id: str) -> Invoice:
        invoice = self._invoices[invoice_id]
        if invoice.status != "ISSUED":
            raise ValueError("INVOICE_STATUS_INVALID")
        if not document_id.strip():
            raise ValueError("INVOICE_DOCUMENT_REQUIRED")
        invoice.status = "REVERSED"
        invoice.reversal_document_id = document_id
        return invoice
