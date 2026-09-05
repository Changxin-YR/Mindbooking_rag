"""HTTP boundary for configurable membership and community commercial facts."""

from collections.abc import Callable
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import (
    optional_session,
    require_account_access,
    require_staff_session,
)
from novel_platform.modules.membership.domain import TicketType
from novel_platform.modules.wallet.api import _valid_callback_signature


class MembershipStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    active: bool


class TicketBalanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    recommend: int
    monthly: int


class MembershipPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    duration_days: int = Field(gt=0)
    daily_recommend_tickets: int = Field(ge=0)
    monthly_chapter_tickets: int = Field(ge=0)
    price_cents: int = Field(gt=0)
    version: int = Field(default=1, gt=0)


class LibraryEntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: str = Field(min_length=1)
    book_id: str = Field(min_length=1)


class TicketGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    ticket_type: TicketType
    quantity: int = Field(gt=0)
    source_ref: str = Field(min_length=1)
    expires_at: str | None = None


class TicketVoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    book_id: str = Field(min_length=1)
    ticket_type: TicketType
    quantity: int = Field(default=1, gt=0)


class GiftDefinitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gift_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    price_coin: int = Field(gt=0)
    fan_value: int = Field(gt=0)
    spend_mode: str = Field(default="GIFT_AND_RECHARGE", min_length=1)


class GiftSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    book_id: str = Field(min_length=1)
    author_id: str = Field(min_length=1)
    gift_code: str = Field(min_length=1)
    quantity: int = Field(default=1, gt=0)


class MembershipOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    plan_code: str = Field(min_length=1)
    channel: str = Field(min_length=1)


class MembershipPaymentCallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    payment_no: str = Field(min_length=1)


def build_membership_router(
    service: object,
    *,
    auth_required: bool = False,
    callback_secret: str = "",
    callback_max_skew_seconds: int = 300,
    asset_spend: Callable[[Any, str, int, str], None] | None = None,
) -> APIRouter:
    router = APIRouter(tags=["membership", "tickets", "gifts"])

    def invoke(method_name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(service, method_name, None)
        if not callable(method):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "MEMBERSHIP_CAPABILITY_UNAVAILABLE",
                    "message": method_name,
                },
            )
        return cast(Callable[..., Any], method)(*args, **kwargs)

    @router.get("/api/v1/membership/status", response_model=MembershipStatusResponse)
    def membership_status(
        account_id: str = Query(min_length=1),
        session: SessionClaims | None = Depends(optional_session),
    ) -> MembershipStatusResponse:
        require_account_access(session, account_id, required=auth_required)
        return MembershipStatusResponse(
            account_id=account_id,
            active=bool(invoke("is_active", account_id)),
        )

    @router.get("/api/v1/membership/tickets", response_model=TicketBalanceResponse)
    def ticket_balance(
        account_id: str = Query(min_length=1),
        session: SessionClaims | None = Depends(optional_session),
    ) -> TicketBalanceResponse:
        require_account_access(session, account_id, required=auth_required)
        method = getattr(service, "ticket_balance", None)
        if not callable(method):
            return TicketBalanceResponse(account_id=account_id, recommend=0, monthly=0)
        balance = cast(Callable[..., Any], method)(account_id)
        return TicketBalanceResponse(
            account_id=account_id,
            recommend=int(balance.recommend),
            monthly=int(balance.monthly),
        )

    @router.post("/api/v1/membership/tickets/votes", status_code=status.HTTP_201_CREATED)
    def vote(
        payload: TicketVoteRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        session: SessionClaims | None = Depends(optional_session),
    ) -> dict[str, object]:
        require_account_access(session, payload.account_id, required=auth_required)
        if not idempotency_key:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key required")
        try:
            result = invoke(
                "vote",
                payload.account_id,
                payload.book_id,
                payload.ticket_type,
                quantity=payload.quantity,
                idempotency_key=idempotency_key,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return {
            "id": result.id,
            "account_id": result.account_id,
            "book_id": result.book_id,
            "ticket_type": result.ticket_type,
            "quantity": result.quantity,
            "risk_status": result.risk_status,
        }

    @router.post("/admin/api/v1/membership/plans", status_code=status.HTTP_201_CREATED)
    def create_plan(payload: MembershipPlanRequest, request: Request) -> dict[str, object]:
        require_staff_session(request)
        try:
            plan = invoke("create_plan", **payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return {
            "plan_code": plan.plan_code,
            "name": plan.name,
            "version": plan.version,
            "duration_days": plan.duration_days,
            "price_cents": plan.price_cents,
            "daily_recommend_tickets": plan.daily_recommend_tickets,
            "monthly_chapter_tickets": plan.monthly_chapter_tickets,
            "status": plan.status,
        }

    @router.post("/admin/api/v1/membership/library", status_code=status.HTTP_204_NO_CONTENT)
    def add_library_entry(payload: LibraryEntryRequest, request: Request) -> None:
        require_staff_session(request)
        try:
            invoke("add_library_book", payload.plan_code, payload.book_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @router.post("/api/v1/membership/orders", status_code=status.HTTP_201_CREATED)
    def create_membership_order(
        payload: MembershipOrderRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        session: SessionClaims | None = Depends(optional_session),
    ) -> dict[str, object]:
        require_account_access(session, payload.account_id, required=auth_required)
        if not idempotency_key:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key required")
        try:
            order = invoke(
                "create_order",
                payload.account_id,
                payload.plan_code,
                payload.channel,
                idempotency_key,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return {
            "id": order.id,
            "payment_no": order.payment_no,
            "account_id": order.account_id,
            "plan_code": order.plan_code,
            "plan_version": order.plan_version,
            "channel": order.channel,
            "price_cents": order.price_cents,
            "status": order.status,
        }

    @router.post("/api/v1/membership/payments/callback")
    def membership_payment_callback(
        payload: MembershipPaymentCallbackRequest,
        callback_timestamp: str | None = Header(default=None, alias="X-Payment-Timestamp"),
        callback_signature: str | None = Header(default=None, alias="X-Payment-Signature"),
    ) -> dict[str, str]:
        if not _valid_callback_signature(
            callback_secret,
            callback_max_skew_seconds,
            payload.provider,
            payload.event_id,
            payload.payment_no,
            callback_timestamp,
            callback_signature,
        ):
            raise HTTPException(status_code=401, detail="valid payment callback signature required")
        try:
            order_id = invoke(
                "handle_payment_callback",
                payload.provider,
                payload.event_id,
                payload.payment_no,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"order_id": str(order_id), "status": "PAID"}

    @router.post("/api/v1/gifts", status_code=status.HTTP_201_CREATED)
    def send_gift(
        payload: GiftSendRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        session: SessionClaims | None = Depends(optional_session),
    ) -> dict[str, object]:
        require_account_access(session, payload.account_id, required=auth_required)
        if not idempotency_key:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key required")
        if asset_spend is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "GIFT_CAPABILITY_UNAVAILABLE", "message": "wallet transaction"},
            )
        try:
            order = invoke(
                "send_gift",
                payload.account_id,
                payload.book_id,
                payload.author_id,
                payload.gift_code,
                quantity=payload.quantity,
                idempotency_key=idempotency_key,
                asset_spend=asset_spend,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return {
            "id": order.id,
            "account_id": order.account_id,
            "book_id": order.book_id,
            "author_id": order.author_id,
            "gift_code": order.gift_code,
            "quantity": order.quantity,
            "total_coin": order.total_coin,
            "fan_value": order.fan_value,
            "status": order.status,
        }

    @router.post("/admin/api/v1/membership/tickets/grant", response_model=TicketBalanceResponse)
    def grant_tickets(payload: TicketGrantRequest, request: Request) -> TicketBalanceResponse:
        require_staff_session(request)
        expires_at: datetime | None = None
        if payload.expires_at:
            try:
                expires_at = datetime.fromisoformat(payload.expires_at)
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid expires_at"
                ) from exc
        try:
            balance = invoke(
                "grant_tickets",
                payload.account_id,
                payload.ticket_type,
                payload.quantity,
                source_ref=payload.source_ref,
                expires_at=expires_at,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return TicketBalanceResponse(
            account_id=payload.account_id,
            recommend=int(balance.recommend),
            monthly=int(balance.monthly),
        )

    @router.post("/admin/api/v1/gifts", status_code=status.HTTP_201_CREATED)
    def register_gift(payload: GiftDefinitionRequest, request: Request) -> dict[str, object]:
        require_staff_session(request)
        try:
            gift = invoke("register_gift", **payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return {
            "gift_code": gift.gift_code,
            "name": gift.name,
            "price_coin": gift.price_coin,
            "fan_value": gift.fan_value,
            "spend_mode": gift.spend_mode,
        }

    return router


__all__ = ["build_membership_router"]
