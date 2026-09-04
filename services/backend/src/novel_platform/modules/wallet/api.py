from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from novel_platform.modules.commerce.application import CommerceService


class RechargeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    product_code: str
    channel: str


class RechargeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_no: str
    recharge_no: str
    paid_cents: int
    recharge_coin: int
    gift_coin: int
    status: str


class PaymentCallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    event_id: str
    payment_no: str


class PaymentCallbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recharge_no: str
    status: str


class WalletResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    recharge_coin: int
    gift_coin: int
    total_coin: int


class PurchaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    chapter_id: str


class PurchaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_no: str
    chapter_id: str
    price_coin: int
    status: str


def build_reader_router(commerce: CommerceService) -> APIRouter:
    router = APIRouter(tags=["wallet", "commerce"])

    @router.get("/wallet", response_model=WalletResponse, operation_id="get_wallet")
    def get_wallet(account_id: str = Query(min_length=1)) -> WalletResponse:
        balance = commerce.wallet.balance(account_id)
        return WalletResponse(
            account_id=account_id,
            recharge_coin=balance.recharge_coin,
            gift_coin=balance.gift_coin,
            total_coin=balance.total_coin,
        )

    @router.post("/recharge", response_model=RechargeResponse, operation_id="create_recharge")
    def create_recharge(
        payload: RechargeRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> RechargeResponse:
        try:
            order = commerce.create_recharge(
                payload.account_id, payload.product_code, payload.channel, idempotency_key
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail={"code": str(exc), "message": str(exc)}
            ) from exc
        return RechargeResponse(
            payment_no=order.payment_order.payment_no,
            recharge_no=order.recharge_order.recharge_no,
            paid_cents=order.payment_order.paid_cents,
            recharge_coin=order.recharge_order.recharge_coin,
            gift_coin=order.recharge_order.gift_coin,
            status=order.recharge_order.status,
        )

    @router.post(
        "/recharge/callback",
        response_model=PaymentCallbackResponse,
        operation_id="payment_callback",
    )
    def payment_callback(payload: PaymentCallbackRequest) -> PaymentCallbackResponse:
        try:
            recharge_no = commerce.handle_payment_callback(
                payload.provider, payload.event_id, payload.payment_no
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail={"code": str(exc), "message": str(exc)}
            ) from exc
        return PaymentCallbackResponse(recharge_no=recharge_no, status="PAID")

    @router.post("/purchases", response_model=PurchaseResponse, operation_id="purchase_chapter")
    def purchase_chapter(payload: PurchaseRequest) -> PurchaseResponse:
        try:
            order = commerce.purchase_chapter(payload.account_id, payload.chapter_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail={"code": str(exc), "message": str(exc)}
            ) from exc
        return PurchaseResponse(
            purchase_no=order.purchase_no,
            chapter_id=order.chapter_id,
            price_coin=order.price_coin,
            status="PURCHASED",
        )

    return router
