from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.modules.governance.application import GovernanceService
from novel_platform.modules.governance.domain import ReconciliationDifference


class PrivacyRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)


class AgreementBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str = Field(min_length=1)
    agreement_code: str = Field(min_length=1)
    version: str = Field(min_length=1)


class ParameterBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    maker_id: str = Field(min_length=1)


class ParameterActivationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    effective_at: str = Field(min_length=1)


class CreditFailureBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    amount_cents: int = Field(gt=0)


class ReconciliationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_date: str = Field(min_length=1)


class ReconciliationItemBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str = Field(min_length=1)
    difference: ReconciliationDifference
    amount_cents: int = Field(ge=0)


class EmergencyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1)
    features: set[str] = Field(min_length=1)
    operator_id: str = Field(min_length=1)


class OutboxBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str = Field(min_length=1)
    aggregate_id: str = Field(min_length=1)
    payload: dict[str, object]


class InvoiceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str = Field(min_length=1)
    amount_cents: int = Field(gt=0)
    title: str = Field(min_length=1)
    tax_id: str = Field(min_length=1)


class InvoiceDocumentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str = Field(min_length=1)


def build_governance_router(service: GovernanceService) -> APIRouter:
    router = APIRouter(tags=["governance"])

    @router.post("/api/v1/privacy/requests", status_code=status.HTTP_201_CREATED)
    def privacy_request(payload: PrivacyRequestBody) -> dict[str, object]:
        return asdict(service.open_privacy_request(**payload.model_dump()))

    @router.post("/api/v1/agreements/acceptances", status_code=status.HTTP_201_CREATED)
    def accept_agreement(payload: AgreementBody) -> dict[str, object]:
        try:
            return asdict(service.accept_agreement(**payload.model_dump()))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @router.post("/admin/api/v1/parameters", status_code=status.HTTP_201_CREATED)
    def draft_parameter(payload: ParameterBody) -> dict[str, object]:
        return asdict(service.draft_parameter(**payload.model_dump()))

    @router.post("/admin/api/v1/parameters/{parameter_id}/approve")
    def approve_parameter(parameter_id: str, checker_id: str) -> dict[str, object]:
        try:
            return asdict(service.approve_parameter(parameter_id, checker_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="parameter not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.post("/admin/api/v1/parameters/{parameter_id}/activate")
    def activate_parameter(
        parameter_id: str, payload: ParameterActivationBody
    ) -> dict[str, object]:
        try:
            return asdict(service.activate_parameter(parameter_id, payload.effective_at))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="parameter not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.post("/admin/api/v1/reconciliation/credit-pending", status_code=status.HTTP_201_CREATED)
    def credit_pending(payload: CreditFailureBody) -> dict[str, object]:
        return asdict(service.record_payment_credit_failure(**payload.model_dump()))

    @router.post("/admin/api/v1/reconciliation/batches", status_code=status.HTTP_201_CREATED)
    def reconciliation(payload: ReconciliationBody) -> dict[str, object]:
        return asdict(service.open_reconciliation(**payload.model_dump()))

    @router.post(
        "/admin/api/v1/reconciliation/batches/{batch_id}/items", status_code=status.HTTP_201_CREATED
    )
    def reconciliation_item(batch_id: str, payload: ReconciliationItemBody) -> dict[str, object]:
        try:
            return asdict(service.add_reconciliation_item(batch_id, **payload.model_dump()))
        except KeyError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="reconciliation batch not found"
            ) from exc

    @router.post("/admin/api/v1/emergencies", status_code=status.HTTP_201_CREATED)
    def emergency(payload: EmergencyBody) -> dict[str, object]:
        return asdict(service.pause_features(**payload.model_dump()))

    @router.post("/admin/api/v1/emergencies/{emergency_id}/resolve")
    def resolve_emergency(emergency_id: str, operator_id: str) -> dict[str, object]:
        try:
            return asdict(service.resolve_emergency(emergency_id, operator_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="emergency not found") from exc

    @router.post("/admin/api/v1/outbox/events", status_code=status.HTTP_201_CREATED)
    def outbox_event(payload: OutboxBody) -> dict[str, object]:
        return asdict(service.enqueue_outbox(**payload.model_dump()))

    @router.post("/api/v1/invoices", status_code=status.HTTP_201_CREATED)
    def invoice(payload: InvoiceBody) -> dict[str, object]:
        return asdict(service.request_invoice(**payload.model_dump()))

    @router.post("/admin/api/v1/invoices/{invoice_id}/issue")
    def issue_invoice(invoice_id: str, payload: InvoiceDocumentBody) -> dict[str, object]:
        try:
            return asdict(service.issue_invoice(invoice_id, payload.document_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="invoice not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.post("/admin/api/v1/invoices/{invoice_id}/reverse")
    def reverse_invoice(invoice_id: str, payload: InvoiceDocumentBody) -> dict[str, object]:
        try:
            return asdict(service.reverse_invoice(invoice_id, payload.document_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="invoice not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return router
