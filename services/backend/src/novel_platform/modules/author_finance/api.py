from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.modules.author_finance.application import AuthorFinanceService
from novel_platform.modules.author_finance.domain import (
    Contract,
    RevenueEntry,
    Settlement,
)


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


def build_author_finance_router(service: AuthorFinanceService) -> tuple[APIRouter, APIRouter]:
    writer = APIRouter(prefix="/writer/api/v1/finance", tags=["author-finance"])
    admin = APIRouter(prefix="/admin/api/v1/finance", tags=["author-finance-admin"])

    @writer.post("/contracts", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
    def create_contract(payload: ContractRequest) -> ContractResponse:
        try:
            return _contract(
                service.create_contract(payload.author_id, payload.book_id, payload.share_bps)
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @admin.post("/contracts/{contract_id}/approve", response_model=ContractResponse)
    def approve_contract(contract_id: str, payload: ContractAction) -> ContractResponse:
        try:
            return _contract(service.approve_contract(contract_id, payload.actor_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="contract not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @admin.post("/contracts/{contract_id}/activate", response_model=ContractResponse)
    def activate_contract(contract_id: str, payload: ContractAction) -> ContractResponse:
        del payload
        try:
            return _contract(service.activate_contract(contract_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="contract not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @admin.post("/revenue", response_model=RevenueResponse, status_code=status.HTTP_201_CREATED)
    def record_revenue(payload: RevenueRequest) -> RevenueResponse:
        try:
            return _revenue(service.record_revenue(**payload.model_dump()))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @admin.post("/revenue/{revenue_id}/confirm", response_model=RevenueResponse)
    def confirm_revenue(revenue_id: str) -> RevenueResponse:
        try:
            return _revenue(service.confirm_revenue(revenue_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="revenue not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @admin.post(
        "/settlements", response_model=SettlementResponse, status_code=status.HTTP_201_CREATED
    )
    def settle(payload: SettlementRequest) -> SettlementResponse:
        return _settlement(service.settle(payload.author_id, payload.period))

    @writer.post("/settlements/{settlement_id}/withdraw", response_model=WithdrawalResponse)
    def withdraw(settlement_id: str, payload: WithdrawalRequest) -> WithdrawalResponse:
        try:
            item = service.withdraw(settlement_id, **payload.model_dump())
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

    @admin.post("/chargebacks", status_code=status.HTTP_201_CREATED)
    def chargeback(payload: ChargebackRequest) -> dict[str, int | str]:
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
