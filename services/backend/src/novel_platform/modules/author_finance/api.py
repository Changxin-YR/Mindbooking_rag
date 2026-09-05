from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import require_session, require_staff_session
from novel_platform.modules.author_finance.application import AuthorFinanceService
from novel_platform.modules.author_finance.domain import (
    Contract,
    PayoutOrder,
    RevenueEntry,
    Settlement,
)
from novel_platform.modules.payment import ProviderEvent, ProviderStatus


class ContractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_id: str = Field(min_length=1)
    book_id: str = Field(min_length=1)
    share_bps: int = Field(default=7000, ge=1, le=10000)


class ContractAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str = Field(min_length=1)


class RevenueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    gross_cents: int = Field(gt=0)
    share_bps: int = Field(ge=0, le=10000)


class SettlementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_id: str = Field(min_length=1)
    period: str = Field(min_length=1)


class WithdrawalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_id: str = Field(min_length=1)
    amount_cents: int = Field(gt=0)
    payout_method: str = Field(min_length=1)
    holder_matches_real_name: bool


class ChargebackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ref: str = Field(min_length=1)
    amount_cents: int = Field(gt=0)


class ContractResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    author_id: str
    book_id: str
    status: str


class RevenueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    author_id: str
    source: str
    source_ref: str
    gross_cents: int
    author_cents: int
    status: str


class SettlementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    author_id: str
    period: str
    amount_cents: int
    status: str
    withdrawn_cents: int


class WithdrawalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    settlement_id: str
    amount_cents: int
    status: str


class PayoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    withdrawal_id: str
    payout_no: str
    provider: str
    amount_cents: int
    currency: str
    destination: str
    status: str
    provider_event_id: str | None = None


class PayoutProviderEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    event_type: str
    event_id: str
    reference_id: str
    provider_transaction_id: str
    status: str
    amount_cents: int
    currency: str
    occurred_at: datetime
    available_at: datetime
    signature: str


def _contract(item: Contract) -> ContractResponse:
    return ContractResponse(
        id=item.id, author_id=item.author_id, book_id=item.book_id, status=item.status
    )


def _revenue(item: RevenueEntry) -> RevenueResponse:
    return RevenueResponse(
        id=item.id,
        author_id=item.author_id,
        source=item.source,
        source_ref=item.source_ref,
        gross_cents=item.gross_cents,
        author_cents=item.author_cents,
        status=item.status,
    )


def _settlement(item: Settlement) -> SettlementResponse:
    return SettlementResponse(
        id=item.id,
        author_id=item.author_id,
        period=item.period,
        amount_cents=item.amount_cents,
        status=item.status,
        withdrawn_cents=item.withdrawn_cents,
    )


def _payout(item: PayoutOrder) -> PayoutResponse:
    return PayoutResponse(
        id=item.id,
        withdrawal_id=item.withdrawal_id,
        payout_no=item.payout_no,
        provider=item.provider,
        amount_cents=item.amount_cents,
        currency=item.currency,
        destination=item.destination,
        status=item.status,
        provider_event_id=item.provider_event_id,
    )


def build_author_finance_router(
    service: AuthorFinanceService,
    *,
    auth_required: bool = False,
    account_for_author: Callable[[str], str] | None = None,
    is_real_named: Callable[[str], bool] | None = None,
    authorize_staff: Callable[[SessionClaims, str], None] | None = None,
) -> tuple[APIRouter, APIRouter]:
    writer = APIRouter(prefix="/writer/api/v1/finance", tags=["author-finance"])
    admin = APIRouter(prefix="/admin/api/v1/finance", tags=["author-finance-admin"])

    def writer_account(request: Request, author_id: str) -> str:
        claims = require_session(request)
        if claims.subject_type != "ACCOUNT":
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "ACCOUNT_AUTHENTICATION_REQUIRED",
                    "message": "account session required",
                },
            )
        if account_for_author is None:
            if auth_required:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "code": "AUTHOR_ACCESS_CONFIGURATION_ERROR",
                        "message": "author access is not configured",
                    },
                )
            return claims.account_id
        try:
            account_id = account_for_author(author_id)
        except LookupError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "AUTHOR_NOT_FOUND", "message": "author profile not found"},
            ) from exc
        if account_id != claims.account_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "ACCOUNT_ACCESS_DENIED",
                    "message": "author is not owned by session",
                },
            )
        return account_id

    def staff_actor(request: Request, supplied: str) -> str:
        return require_staff_session(request).account_id if auth_required else supplied

    def authorize(request: Request, permission: str) -> str:
        claims = require_staff_session(request)
        if authorize_staff is not None:
            authorize_staff(claims, permission)
        return claims.account_id

    @writer.post("/contracts", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
    def create_contract(payload: ContractRequest, request: Request) -> ContractResponse:
        writer_account(request, payload.author_id)
        try:
            return _contract(
                service.create_contract(payload.author_id, payload.book_id, payload.share_bps)
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @admin.post("/contracts/{contract_id}/approve", response_model=ContractResponse)
    def approve_contract(
        contract_id: str, payload: ContractAction, request: Request
    ) -> ContractResponse:
        try:
            return _contract(
                service.approve_contract(contract_id, staff_actor(request, payload.actor_id))
            )
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="contract not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @admin.post("/contracts/{contract_id}/activate", response_model=ContractResponse)
    def activate_contract(
        contract_id: str, payload: ContractAction, request: Request
    ) -> ContractResponse:
        del payload
        if auth_required:
            require_staff_session(request)
        try:
            return _contract(service.activate_contract(contract_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="contract not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @admin.post("/revenue", response_model=RevenueResponse, status_code=status.HTTP_201_CREATED)
    def record_revenue(payload: RevenueRequest, request: Request) -> RevenueResponse:
        if auth_required:
            require_staff_session(request)
        try:
            return _revenue(service.record_revenue(**payload.model_dump()))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @admin.post("/revenue/{revenue_id}/confirm", response_model=RevenueResponse)
    def confirm_revenue(revenue_id: str, request: Request) -> RevenueResponse:
        if auth_required:
            require_staff_session(request)
        try:
            return _revenue(service.confirm_revenue(revenue_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="revenue not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @admin.post(
        "/settlements", response_model=SettlementResponse, status_code=status.HTTP_201_CREATED
    )
    def settle(payload: SettlementRequest, request: Request) -> SettlementResponse:
        if auth_required:
            require_staff_session(request)
        return _settlement(service.settle(payload.author_id, payload.period))

    @writer.post("/settlements/{settlement_id}/withdraw", response_model=WithdrawalResponse)
    def withdraw(
        settlement_id: str, payload: WithdrawalRequest, request: Request
    ) -> WithdrawalResponse:
        account_id = writer_account(request, payload.author_id)
        try:
            values = payload.model_dump()
            if is_real_named is not None:
                values["holder_matches_real_name"] = is_real_named(account_id)
            item = service.withdraw(settlement_id, **values)
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="settlement not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return WithdrawalResponse(
            id=item.id,
            settlement_id=item.settlement_id,
            amount_cents=item.amount_cents,
            status=item.status,
        )

    @admin.post("/withdrawals/{withdrawal_id}/risk-approve", response_model=WithdrawalResponse)
    def approve_withdrawal_risk(
        withdrawal_id: str, payload: ContractAction, request: Request
    ) -> WithdrawalResponse:
        actor_id = authorize(request, "risk.write") if auth_required else payload.actor_id
        try:
            item = service.approve_withdrawal_risk(withdrawal_id, actor_id)
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="withdrawal not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return WithdrawalResponse(
            id=item.id,
            settlement_id=item.settlement_id,
            amount_cents=item.amount_cents,
            status=item.status,
        )

    @admin.post("/withdrawals/{withdrawal_id}/finance-approve", response_model=PayoutResponse)
    def approve_withdrawal_finance(
        withdrawal_id: str, payload: ContractAction, request: Request
    ) -> PayoutResponse:
        actor_id = authorize(request, "finance.write") if auth_required else payload.actor_id
        try:
            return _payout(service.approve_withdrawal_finance(withdrawal_id, actor_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="withdrawal not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @admin.post("/chargebacks", status_code=status.HTTP_201_CREATED)
    def chargeback(payload: ChargebackRequest, request: Request) -> dict[str, int | str]:
        if auth_required:
            require_staff_session(request)
        try:
            item = service.chargeback(**payload.model_dump())
        except KeyError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="revenue source not found"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return {
            "id": item.id,
            "amount_cents": item.amount_cents,
            "recovered_cents": item.recovered_cents,
        }

    return writer, admin


def build_payout_callback_router(service: AuthorFinanceService) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["author-finance-payout"])

    @router.post("/payouts/provider-callback", response_model=PayoutResponse)
    def payout_provider_callback(payload: PayoutProviderEventRequest) -> PayoutResponse:
        try:
            result = service.handle_payout_provider_event(
                ProviderEvent(
                    provider=payload.provider,
                    event_type=payload.event_type,
                    event_id=payload.event_id,
                    reference_id=payload.reference_id,
                    provider_transaction_id=payload.provider_transaction_id,
                    status=ProviderStatus(payload.status),
                    amount_cents=payload.amount_cents,
                    currency=payload.currency,
                    occurred_at=payload.occurred_at,
                    available_at=payload.available_at,
                    signature=payload.signature,
                )
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return _payout(result)

    return router
