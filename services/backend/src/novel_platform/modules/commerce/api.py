from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import require_session
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


def build_refund_router(service: RefundService, *, auth_required: bool = False) -> APIRouter:
    router = APIRouter(tags=["commerce-refund"])

    @router.post("/refunds", response_model=RefundResponse, operation_id="create_refund")
    def create_refund(
        payload: RefundRequest,
        request: Request,
    ) -> RefundResponse:
        if auth_required:
            claims: SessionClaims = require_session(request)
            try:
                if (
                    service.account_id_for_refund(payload.payment_no, payload.recharge_no)
                    != claims.account_id
                ):
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "code": "ACCOUNT_ACCESS_DENIED",
                            "message": "refund source is not owned by session",
                        },
                    )
            except ValueError as exc:
                raise HTTPException(
                    status_code=422, detail={"code": str(exc), "message": str(exc)}
                ) from exc
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
