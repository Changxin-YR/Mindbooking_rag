from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import (
    optional_session,
    require_account_access,
    require_session,
    require_staff_session,
)
from novel_platform.modules.support.application import SupportService
from novel_platform.modules.support.domain import SupportPriority, SupportStatus


class CreateTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    priority: SupportPriority
    description: str = Field(min_length=1)


class ReplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1)
    author: str = Field(min_length=1)


class TicketResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    account_id: str
    category: str
    priority: SupportPriority
    status: SupportStatus


def build_support_router(
    service: SupportService,
    *,
    auth_required: bool = False,
    authorize_staff: Callable[[SessionClaims, str], None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/support", tags=["support"])

    @router.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
    def create_ticket(
        payload: CreateTicketRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> TicketResponse:
        require_account_access(session, payload.account_id, required=auth_required)
        ticket = service.open_ticket(
            payload.account_id, payload.category, payload.priority, payload.description
        )
        return TicketResponse.model_validate(ticket, from_attributes=True)

    @router.get(
        "/tickets", response_model=list[TicketResponse], operation_id="reader_list_support_tickets"
    )
    def list_tickets(
        account_id: str,
        session: SessionClaims | None = Depends(optional_session),
    ) -> list[TicketResponse]:
        require_account_access(session, account_id, required=auth_required)
        return [
            TicketResponse.model_validate(ticket, from_attributes=True)
            for ticket in service.list_tickets(account_id)
        ]

    @router.post("/tickets/{ticket_id}/resolve", response_model=TicketResponse)
    def resolve_ticket(ticket_id: str, request: Request) -> TicketResponse:
        if auth_required:
            claims = require_session(request)
            require_staff_session(request)
            if authorize_staff is not None:
                authorize_staff(claims, "support.write")
        try:
            return TicketResponse.model_validate(service.resolve(ticket_id), from_attributes=True)
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="ticket not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.post("/tickets/{ticket_id}/replies", response_model=TicketResponse)
    def reply(
        ticket_id: str,
        payload: ReplyRequest,
        request: Request,
        session: SessionClaims | None = Depends(optional_session),
    ) -> TicketResponse:
        try:
            ticket = service.get_ticket(ticket_id)
            author = payload.author
            if auth_required:
                claims = require_session(request)
                if claims.subject_type == "STAFF":
                    if authorize_staff is not None:
                        authorize_staff(claims, "support.write")
                    author = "STAFF"
                else:
                    require_account_access(session, ticket.account_id, required=True)
                    author = "USER"
            service.reply(ticket_id, payload.body, author)
            return TicketResponse.model_validate(
                service.get_ticket(ticket_id), from_attributes=True
            )
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="ticket not found") from exc

    return router
