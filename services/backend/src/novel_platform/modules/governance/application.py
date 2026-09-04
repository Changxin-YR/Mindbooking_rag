from uuid import uuid4

from novel_platform.modules.governance.domain import (
    AgreementAcceptance,
    Emergency,
    Invoice,
    OutboxEvent,
    ParameterStatus,
    ParameterVersion,
    PaymentCreditPending,
    PrivacyRequest,
    ReconciliationBatch,
    ReconciliationDifference,
    ReconciliationItem,
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
        if amount_cents <= 0:
            raise ValueError("PAYMENT_AMOUNT_INVALID")
        pending = self._pending.get(payment_id)
        if pending is None:
            pending = PaymentCreditPending(_id("CREDIT"), payment_id, account_id, amount_cents)
            self._pending[payment_id] = pending
        return pending

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
