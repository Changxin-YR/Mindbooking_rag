import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import cast

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import (
    require_session,
    require_staff_authorization,
)
from novel_platform.modules.author_finance.application import AuthorFinanceService
from novel_platform.modules.author_finance.domain import (
    Contract,
    PayoutOrder,
    RevenueEntry,
    Settlement,
)
from novel_platform.modules.payment import ProviderEvent, ProviderStatus, validate_event_freshness


class ContractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_id: str = Field(min_length=1)
    book_id: str = Field(min_length=1)
    share_bps: int | None = Field(default=None, ge=1, le=10000)


class ContractAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str = Field(min_length=1)


class RevenueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    book_id: str | None = Field(default=None, min_length=1)
    gross_cents: int = Field(gt=0)
    share_bps: int | None = Field(default=None, ge=0, le=10000)


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
    policy_version: str
    document_text: str
    document_hash: str
    signed_by: str | None = None
    signed_at: datetime | None = None
    signature_hash: str | None = None


class RevenueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    author_id: str
    source: str
    source_ref: str
    gross_cents: int
    author_cents: int
    status: str
    tax_cents: int
    net_author_cents: int
    policy_version: str | None


class SettlementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    author_id: str
    period: str
    amount_cents: int
    status: str
    withdrawn_cents: int
    gross_cents: int
    tax_cents: int


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
    provider_transaction_id: str | None = None


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


class SandboxPayoutSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payout_no: str = Field(min_length=1)
    status: ProviderStatus = ProviderStatus.SUCCESS
    delay_seconds: int = Field(default=0, ge=0)
    duplicate: bool = False


class SandboxPayoutSimulationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payout_no: str
    provider: str
    event_id: str
    status: str
    processed: bool
    available_at: datetime


def _contract(item: Contract) -> ContractResponse:
    return ContractResponse(
        id=item.id,
        author_id=item.author_id,
        book_id=item.book_id,
        status=item.status,
        policy_version=item.policy_version,
        document_text=item.document_text,
        document_hash=item.document_hash,
        signed_by=item.signed_by,
        signed_at=item.signed_at,
        signature_hash=item.signature_hash,
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
        tax_cents=item.tax_cents,
        net_author_cents=(
            item.net_author_cents
            if item.net_author_cents is not None
            else item.author_cents - item.tax_cents
        ),
        policy_version=item.policy_version,
    )


def _settlement(item: Settlement) -> SettlementResponse:
    return SettlementResponse(
        id=item.id,
        author_id=item.author_id,
        period=item.period,
        amount_cents=item.amount_cents,
        status=item.status,
        withdrawn_cents=item.withdrawn_cents,
        gross_cents=item.gross_cents,
        tax_cents=item.tax_cents,
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
        provider_transaction_id=item.provider_transaction_id,
    )


def build_author_finance_router(
    service: AuthorFinanceService,
    *,
    auth_required: bool = False,
    account_for_author: Callable[[str], str] | None = None,
    author_for_book: Callable[[str], str] | None = None,
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

    def staff_actor(request: Request, supplied: str, permission: str) -> str:
        if not auth_required:
            return supplied
        return authorize(request, permission)

    def writer_book(request: Request, author_id: str, book_id: str) -> None:
        writer_account(request, author_id)
        if author_for_book is None:
            return
        try:
            book_author_id = author_for_book(book_id)
        except LookupError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "BOOK_NOT_FOUND", "message": "book not found"},
            ) from exc
        if book_author_id != author_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "AUTHOR_BOOK_ACCESS_DENIED",
                    "message": "book is not owned by author",
                },
            )

    def authorize(request: Request, permission: str) -> str:
        claims = require_staff_authorization(request, authorize_staff, permission)
        return claims.account_id

    @writer.post("/contracts", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
    def create_contract(payload: ContractRequest, request: Request) -> ContractResponse:
        writer_book(request, payload.author_id, payload.book_id)
        try:
            return _contract(
                service.create_contract(payload.author_id, payload.book_id, payload.share_bps)
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @writer.get("/contracts/{contract_id}", response_model=ContractResponse)
    def get_contract(contract_id: str, request: Request) -> ContractResponse:
        try:
            contract = service.get_contract(contract_id)
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="contract not found") from exc
        writer_account(request, contract.author_id)
        return _contract(contract)

    @writer.post("/contracts/{contract_id}/sign", response_model=ContractResponse)
    def sign_contract(contract_id: str, request: Request) -> ContractResponse:
        try:
            contract = service.get_contract(contract_id)
            signer_id = writer_account(request, contract.author_id)
            return _contract(service.sign_contract(contract_id, signer_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="contract not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @admin.get("/contracts", response_model=list[ContractResponse])
    def list_contracts(
        request: Request,
        author_id: str | None = Query(default=None, min_length=1),
        status_filter: str | None = Query(default=None, min_length=1, alias="status"),
    ) -> list[ContractResponse]:
        if auth_required:
            authorize(request, "finance.read")
        try:
            contracts = service.list_contracts(author_id=author_id, status=status_filter)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return [_contract(item) for item in contracts]

    @admin.post("/contracts/{contract_id}/approve", response_model=ContractResponse)
    def approve_contract(
        contract_id: str, payload: ContractAction, request: Request
    ) -> ContractResponse:
        try:
            actor_id = staff_actor(request, payload.actor_id, "approval.write")
            return _contract(service.approve_contract(contract_id, actor_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="contract not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @admin.post("/contracts/{contract_id}/activate", response_model=ContractResponse)
    def activate_contract(
        contract_id: str, payload: ContractAction, request: Request
    ) -> ContractResponse:
        if auth_required:
            authorize(request, "approval.write")
        try:
            return _contract(service.activate_contract(contract_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="contract not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @admin.post("/revenue", response_model=RevenueResponse, status_code=status.HTTP_201_CREATED)
    def record_revenue(payload: RevenueRequest, request: Request) -> RevenueResponse:
        if auth_required:
            authorize(request, "finance.write")
        try:
            return _revenue(service.record_revenue(**payload.model_dump()))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @admin.post("/revenue/{revenue_id}/confirm", response_model=RevenueResponse)
    def confirm_revenue(revenue_id: str, request: Request) -> RevenueResponse:
        if auth_required:
            authorize(request, "finance.write")
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
            authorize(request, "finance.write")
        return _settlement(service.settle(payload.author_id, payload.period))

    @writer.get("/settlements", response_model=list[SettlementResponse])
    def list_settlements(
        request: Request, author_id: str = Query(min_length=1)
    ) -> list[SettlementResponse]:
        writer_account(request, author_id)
        try:
            return [_settlement(item) for item in service.list_settlements(author_id)]
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

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
            authorize(request, "finance.write")
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


def build_payout_callback_router(
    service: AuthorFinanceService,
    *,
    auth_required: bool = False,
    callback_max_skew_seconds: int = 300,
    authorize_staff: Callable[[SessionClaims, str], None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["author-finance-payout"])

    def authorize(request: Request, permission: str) -> str:
        claims = require_staff_authorization(request, authorize_staff, permission)
        return claims.account_id

    @router.post("/payouts/provider-callback", response_model=PayoutResponse)
    def payout_provider_callback(payload: PayoutProviderEventRequest) -> PayoutResponse:
        try:
            event = ProviderEvent(
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
            validate_event_freshness(event, max_skew_seconds=callback_max_skew_seconds)
            result = service.handle_payout_provider_event(event)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return _payout(result)

    @router.post(
        "/payouts/sandbox/simulate",
        response_model=SandboxPayoutSimulationResponse,
        operation_id="simulate_sandbox_payout",
    )
    def simulate_sandbox_payout(
        payload: SandboxPayoutSimulationRequest,
        background_tasks: BackgroundTasks,
        request: Request,
    ) -> SandboxPayoutSimulationResponse:
        if auth_required:
            authorize(request, "finance.write")
        provider = getattr(service, "payout_provider", None)
        provider_name = str(getattr(provider, "provider_name", ""))
        if provider is None or not provider_name.startswith("SANDBOX"):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "SANDBOX_PAYOUT_PROVIDER_UNAVAILABLE",
                    "message": "sandbox payout provider required",
                },
            )
        details = getattr(service, "payout_details", None)
        if not callable(details):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "PAYOUT_DETAILS_UNAVAILABLE",
                    "message": "payout details required",
                },
            )
        try:
            amount_cents, currency, destination = cast(
                Callable[[str], tuple[int, str, str]], details
            )(payload.payout_no)
            provider.create_payout(
                payload.payout_no,
                amount_cents,
                currency,
                destination,
            )
            events = provider.simulate_callback(
                payload.payout_no,
                payload.status,
                delay_seconds=payload.delay_seconds,
                duplicate=payload.duplicate,
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        event = events[0]
        if payload.delay_seconds:

            async def process_delayed() -> None:
                await asyncio.sleep(payload.delay_seconds)
                for delayed_event in events:
                    service.handle_payout_provider_event(
                        delayed_event, now=delayed_event.available_at
                    )

            background_tasks.add_task(process_delayed)
            return SandboxPayoutSimulationResponse(
                payout_no=payload.payout_no,
                provider=event.provider,
                event_id=event.event_id,
                status=ProviderStatus.PROCESSING.value,
                processed=False,
                available_at=event.available_at,
            )
        try:
            for callback_event in events:
                service.handle_payout_provider_event(callback_event)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return SandboxPayoutSimulationResponse(
            payout_no=payload.payout_no,
            provider=event.provider,
            event_id=event.event_id,
            status=event.status.value,
            processed=True,
            available_at=event.available_at,
        )

    return router
