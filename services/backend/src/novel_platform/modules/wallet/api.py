import asyncio
from datetime import datetime
from hashlib import sha256
from hmac import compare_digest
from hmac import new as hmac_new
from time import time

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import optional_session, require_account_access
from novel_platform.modules.commerce.application import CommerceService
from novel_platform.modules.payment import ProviderStatus, validate_event_freshness


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
    provider: str | None = None
    checkout_url: str | None = None


class PaymentCallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    event_id: str
    payment_no: str


class PaymentCallbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recharge_no: str
    status: str


class PaymentProviderEventRequest(BaseModel):
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


class SandboxPaymentSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    payment_no: str
    status: ProviderStatus = ProviderStatus.SUCCESS
    delay_seconds: int = 0
    duplicate: bool = False


class SandboxPaymentSimulationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_no: str
    recharge_no: str | None = None
    provider: str
    event_id: str
    status: str
    processed: bool
    available_at: datetime


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


def build_reader_router(
    commerce: CommerceService,
    *,
    auth_required: bool = False,
    callback_secret: str = "",
    callback_max_skew_seconds: int = 300,
) -> APIRouter:
    router = APIRouter(tags=["wallet", "commerce"])

    @router.get("/wallet", response_model=WalletResponse, operation_id="get_wallet")
    def get_wallet(
        account_id: str = Query(min_length=1),
        session: SessionClaims | None = Depends(optional_session),
    ) -> WalletResponse:
        require_account_access(session, account_id, required=auth_required)
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
        session: SessionClaims | None = Depends(optional_session),
    ) -> RechargeResponse:
        require_account_access(session, payload.account_id, required=auth_required)
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
            provider=order.provider_checkout.provider if order.provider_checkout else None,
            checkout_url=order.provider_checkout.checkout_url if order.provider_checkout else None,
        )

    @router.post(
        "/recharge/provider-callback",
        response_model=PaymentCallbackResponse,
        operation_id="payment_provider_callback",
    )
    def payment_provider_callback(
        payload: PaymentProviderEventRequest,
    ) -> PaymentCallbackResponse:
        from novel_platform.modules.payment import ProviderEvent, ProviderStatus

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
            handler = commerce.handle_payment_provider_event
            recharge_no = handler(event)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail={"code": str(exc), "message": str(exc)}
            ) from exc
        return PaymentCallbackResponse(
            recharge_no=str(recharge_no),
            status="PAID" if payload.status == "SUCCESS" else payload.status,
        )

    @router.post(
        "/recharge/sandbox/simulate",
        response_model=SandboxPaymentSimulationResponse,
        operation_id="simulate_sandbox_payment",
    )
    def simulate_sandbox_payment(
        payload: SandboxPaymentSimulationRequest,
        background_tasks: BackgroundTasks,
        session: SessionClaims | None = Depends(optional_session),
    ) -> SandboxPaymentSimulationResponse:
        require_account_access(session, payload.account_id, required=auth_required)
        if payload.delay_seconds < 0:
            raise HTTPException(status_code=422, detail="delay_seconds must be non-negative")
        provider = getattr(commerce, "payment_provider", None)
        provider_name = str(getattr(provider, "provider_name", ""))
        if provider is None or not provider_name.startswith("SANDBOX"):
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "SANDBOX_PROVIDER_UNAVAILABLE",
                    "message": "sandbox provider required",
                },
            )
        try:
            owner, amount_cents = commerce.payment_details(payload.payment_no)
            if owner != payload.account_id:
                raise HTTPException(status_code=403, detail="payment does not belong to account")
            provider.create_checkout(payload.payment_no, amount_cents, currency="CNY")
            events = provider.simulate_callback(
                payload.payment_no,
                payload.status,
                delay_seconds=payload.delay_seconds,
                duplicate=payload.duplicate,
            )
        except HTTPException:
            raise
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        event = events[0]
        if payload.delay_seconds:

            async def process_delayed() -> None:
                await asyncio.sleep(payload.delay_seconds)
                for delayed_event in events:
                    commerce.handle_payment_provider_event(
                        delayed_event, now=delayed_event.available_at
                    )

            background_tasks.add_task(process_delayed)
            return SandboxPaymentSimulationResponse(
                payment_no=payload.payment_no,
                provider=event.provider,
                event_id=event.event_id,
                status=ProviderStatus.PROCESSING.value,
                processed=False,
                available_at=event.available_at,
            )
        recharge_no: str | None = None
        for callback_event in events:
            recharge_no = str(commerce.handle_payment_provider_event(callback_event))
        return SandboxPaymentSimulationResponse(
            payment_no=payload.payment_no,
            recharge_no=recharge_no,
            provider=event.provider,
            event_id=event.event_id,
            status=event.status.value,
            processed=True,
            available_at=event.available_at,
        )

    @router.post(
        "/recharge/callback",
        response_model=PaymentCallbackResponse,
        operation_id="payment_callback",
    )
    def payment_callback(
        payload: PaymentCallbackRequest,
        request: Request,
        callback_timestamp: str | None = Header(default=None, alias="X-Payment-Timestamp"),
        callback_signature: str | None = Header(default=None, alias="X-Payment-Signature"),
    ) -> PaymentCallbackResponse:
        if not _valid_callback_signature(
            callback_secret,
            callback_max_skew_seconds,
            payload.provider,
            payload.event_id,
            payload.payment_no,
            callback_timestamp,
            callback_signature,
        ):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "PAYMENT_CALLBACK_UNAUTHORIZED",
                    "message": "valid payment callback signature required",
                },
            )
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
    def purchase_chapter(
        payload: PurchaseRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> PurchaseResponse:
        require_account_access(session, payload.account_id, required=auth_required)
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


def payment_callback_signature(
    secret: str, provider: str, event_id: str, payment_no: str, timestamp: str
) -> str:
    canonical = f"{provider}:{event_id}:{payment_no}:{timestamp}"
    return hmac_new(secret.encode("utf-8"), canonical.encode("utf-8"), sha256).hexdigest()


def _valid_callback_signature(
    secret: str,
    max_skew_seconds: int,
    provider: str,
    event_id: str,
    payment_no: str,
    timestamp: str | None,
    signature: str | None,
) -> bool:
    if not secret or not timestamp or not signature:
        return False
    try:
        timestamp_value = int(timestamp)
    except ValueError:
        return False
    if abs(int(time()) - timestamp_value) > max_skew_seconds:
        return False
    expected = payment_callback_signature(secret, provider, event_id, payment_no, timestamp)
    return compare_digest(expected, signature)
