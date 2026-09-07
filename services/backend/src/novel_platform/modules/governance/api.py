from collections.abc import Callable
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import (
    optional_session,
    require_account_access,
    require_staff_authorization,
)
from novel_platform.modules.governance.application import GovernanceService
from novel_platform.modules.governance.domain import (
    ReconciliationBatch,
    ReconciliationDifference,
)


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


class PaymentCreditPendingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    payment_id: str
    account_id: str
    amount_cents: int
    status: str
    attempts: int
    last_error: str | None = None
    last_attempted_at: str | None = None
    resolved_at: str | None = None
    repair_actor_id: str | None = None


class ReconciliationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_date: str = Field(min_length=1)


class ReconciliationItemBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str = Field(min_length=1)
    difference: ReconciliationDifference
    amount_cents: int = Field(ge=0)


class ReconciliationBatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    business_date: str
    status: str
    items: list[dict[str, object]]


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


def build_governance_router(
    service: GovernanceService,
    *,
    auth_required: bool = False,
    authorize_staff: Callable[[SessionClaims, str], None] | None = None,
) -> APIRouter:
    router = APIRouter(tags=["governance"])

    def require_governance_staff(request: Request) -> SessionClaims | None:
        if auth_required:
            return require_staff_authorization(request, authorize_staff, "governance.write")
        return None

    def require_finance_staff(request: Request) -> None:
        if auth_required:
            require_staff_authorization(request, authorize_staff, "finance.write")

    def staff_actor(request: Request, supplied: str) -> str:
        claims = require_governance_staff(request)
        return claims.account_id if claims is not None else supplied

    def reconciliation_response(batch: ReconciliationBatch) -> ReconciliationBatchResponse:
        return ReconciliationBatchResponse(
            id=batch.id,
            business_date=batch.business_date,
            status=batch.status.value,
            items=[
                {
                    "id": item.id,
                    "reference": item.reference,
                    "difference": item.difference.value,
                    "amount_cents": item.amount_cents,
                }
                for item in batch.items
            ],
        )

    @router.post("/api/v1/privacy/requests", status_code=status.HTTP_201_CREATED)
    def privacy_request(
        payload: PrivacyRequestBody,
        session: SessionClaims | None = Depends(optional_session),
    ) -> dict[str, object]:
        require_account_access(session, payload.account_id, required=auth_required)
        return asdict(service.open_privacy_request(**payload.model_dump()))

    @router.post("/api/v1/agreements/acceptances", status_code=status.HTTP_201_CREATED)
    def accept_agreement(
        payload: AgreementBody,
        session: SessionClaims | None = Depends(optional_session),
    ) -> dict[str, object]:
        require_account_access(session, payload.account_id, required=auth_required)
        try:
            return asdict(service.accept_agreement(**payload.model_dump()))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @router.post("/admin/api/v1/parameters", status_code=status.HTTP_201_CREATED)
    def draft_parameter(payload: ParameterBody, request: Request) -> dict[str, object]:
        return asdict(
            service.draft_parameter(
                payload.key, payload.value, staff_actor(request, payload.maker_id)
            )
        )

    @router.post("/admin/api/v1/parameters/{parameter_id}/approve")
    def approve_parameter(
        parameter_id: str, request: Request, checker_id: str | None = None
    ) -> dict[str, object]:
        try:
            return asdict(
                service.approve_parameter(parameter_id, staff_actor(request, checker_id or ""))
            )
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="parameter not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.post("/admin/api/v1/parameters/{parameter_id}/activate")
    def activate_parameter(
        parameter_id: str, payload: ParameterActivationBody, request: Request
    ) -> dict[str, object]:
        require_governance_staff(request)
        try:
            return asdict(service.activate_parameter(parameter_id, payload.effective_at))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="parameter not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.post("/admin/api/v1/reconciliation/credit-pending", status_code=status.HTTP_201_CREATED)
    def credit_pending(payload: CreditFailureBody, request: Request) -> dict[str, object]:
        require_governance_staff(request)
        return asdict(service.record_payment_credit_failure(**payload.model_dump()))

    @router.get(
        "/admin/api/v1/reconciliation/credit-pending",
        response_model=list[PaymentCreditPendingResponse],
    )
    def list_credit_pending(
        request: Request, status_filter: str | None = Query(default=None, alias="status")
    ) -> list[PaymentCreditPendingResponse]:
        if auth_required:
            require_staff_authorization(request, authorize_staff, "governance.read")
        try:
            items = service.list_payment_credit_pending(status_filter)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return [
            PaymentCreditPendingResponse(
                **{
                    **asdict(item),
                    "last_attempted_at": item.last_attempted_at.isoformat()
                    if item.last_attempted_at is not None
                    else None,
                    "resolved_at": item.resolved_at.isoformat()
                    if item.resolved_at is not None
                    else None,
                }
            )
            for item in items
        ]

    @router.post(
        "/admin/api/v1/reconciliation/credit-pending/{payment_id}/retry",
        response_model=PaymentCreditPendingResponse,
    )
    def retry_credit_pending(
        payment_id: str, request: Request, operator_id: str | None = None
    ) -> PaymentCreditPendingResponse:
        actor = staff_actor(request, operator_id or "")
        try:
            item = service.retry_payment_credit(payment_id, actor)
        except KeyError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="credit pending not found"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return PaymentCreditPendingResponse(
            **{
                **asdict(item),
                "last_attempted_at": item.last_attempted_at.isoformat()
                if item.last_attempted_at is not None
                else None,
                "resolved_at": item.resolved_at.isoformat()
                if item.resolved_at is not None
                else None,
            }
        )

    @router.post("/admin/api/v1/reconciliation/batches", status_code=status.HTTP_201_CREATED)
    def reconciliation(payload: ReconciliationBody, request: Request) -> dict[str, object]:
        require_governance_staff(request)
        return asdict(service.open_reconciliation(**payload.model_dump()))

    @router.post(
        "/admin/api/v1/reconciliation/batches/{batch_id}/items", status_code=status.HTTP_201_CREATED
    )
    def reconciliation_item(
        batch_id: str, payload: ReconciliationItemBody, request: Request
    ) -> dict[str, object]:
        require_governance_staff(request)
        try:
            return asdict(service.add_reconciliation_item(batch_id, **payload.model_dump()))
        except KeyError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="reconciliation batch not found"
            ) from exc

    @router.get(
        "/admin/api/v1/reconciliation/batches",
        response_model=list[ReconciliationBatchResponse],
    )
    def list_reconciliation_batches(
        request: Request, status_filter: str | None = None
    ) -> list[ReconciliationBatchResponse]:
        if auth_required:
            require_staff_authorization(request, authorize_staff, "governance.read")
        try:
            return [
                reconciliation_response(item)
                for item in service.list_reconciliation_batches(status_filter)
            ]
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @router.post(
        "/admin/api/v1/reconciliation/batches/{batch_id}/repair",
        response_model=ReconciliationBatchResponse,
    )
    def repair_reconciliation_batch(
        batch_id: str, request: Request, operator_id: str | None = None
    ) -> ReconciliationBatchResponse:
        actor = staff_actor(request, operator_id or "")
        try:
            return reconciliation_response(service.mark_reconciliation_repaired(batch_id, actor))
        except KeyError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="reconciliation batch not found"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.post(
        "/admin/api/v1/reconciliation/batches/{batch_id}/close",
        response_model=ReconciliationBatchResponse,
    )
    def close_reconciliation_batch(
        batch_id: str, request: Request, operator_id: str | None = None
    ) -> ReconciliationBatchResponse:
        actor = staff_actor(request, operator_id or "")
        try:
            return reconciliation_response(service.close_reconciliation(batch_id, actor))
        except KeyError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="reconciliation batch not found"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.post("/admin/api/v1/emergencies", status_code=status.HTTP_201_CREATED)
    def emergency(payload: EmergencyBody, request: Request) -> dict[str, object]:
        return asdict(
            service.pause_features(
                payload.reason,
                payload.features,
                staff_actor(request, payload.operator_id),
            )
        )

    @router.post("/admin/api/v1/emergencies/{emergency_id}/resolve")
    def resolve_emergency(
        emergency_id: str, request: Request, operator_id: str | None = None
    ) -> dict[str, object]:
        actor = staff_actor(request, operator_id or "")
        try:
            return asdict(service.resolve_emergency(emergency_id, actor))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="emergency not found") from exc

    @router.post("/admin/api/v1/outbox/events", status_code=status.HTTP_201_CREATED)
    def outbox_event(payload: OutboxBody, request: Request) -> dict[str, object]:
        require_governance_staff(request)
        return asdict(service.enqueue_outbox(**payload.model_dump()))

    @router.post("/api/v1/invoices", status_code=status.HTTP_201_CREATED)
    def invoice(
        payload: InvoiceBody,
        session: SessionClaims | None = Depends(optional_session),
    ) -> dict[str, object]:
        require_account_access(session, payload.account_id, required=auth_required)
        return asdict(service.request_invoice(**payload.model_dump()))

    @router.post("/admin/api/v1/invoices/{invoice_id}/issue")
    def issue_invoice(
        invoice_id: str, payload: InvoiceDocumentBody, request: Request
    ) -> dict[str, object]:
        require_finance_staff(request)
        try:
            return asdict(service.issue_invoice(invoice_id, payload.document_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="invoice not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.post("/admin/api/v1/invoices/{invoice_id}/reverse")
    def reverse_invoice(
        invoice_id: str, payload: InvoiceDocumentBody, request: Request
    ) -> dict[str, object]:
        require_finance_staff(request)
        try:
            return asdict(service.reverse_invoice(invoice_id, payload.document_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="invoice not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return router
