from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.modules.commerce.refund import RefundCalculationSnapshot, RefundService


class RefundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_no: str = Field(min_length=1)
    recharge_no: str = Field(min_length=1)
    refund_reference: str = Field(min_length=1)


class RefundResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_no: str
    recharge_no: str
    refund_reference: str
    refundable_cents: int
    recoverable_recharge_coin: int
    recoverable_promo_gift_coin: int
    executed: bool


def _response(snapshot: RefundCalculationSnapshot) -> RefundResponse:
    return RefundResponse(
        payment_no=snapshot.payment_no,
        recharge_no=snapshot.recharge_no,
        refund_reference=snapshot.refund_reference,
        refundable_cents=snapshot.refundable_cents,
        recoverable_recharge_coin=snapshot.recoverable_recharge_coin,
        recoverable_promo_gift_coin=snapshot.recoverable_promo_gift_coin,
        executed=snapshot.executed,
    )


def build_refund_router(service: RefundService) -> APIRouter:
    router = APIRouter(tags=["commerce-refund"])

    @router.post("/refunds", response_model=RefundResponse, operation_id="create_refund")
    def create_refund(payload: RefundRequest) -> RefundResponse:
        try:
            snapshot = service.refund(
                payload.payment_no, payload.recharge_no, payload.refund_reference
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail={"code": str(exc), "message": str(exc)}
            ) from exc
        return _response(snapshot)

    return router
