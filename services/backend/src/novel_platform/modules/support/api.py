from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

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


def build_support_router(service: SupportService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/support", tags=["support"])

    @router.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
    def create_ticket(payload: CreateTicketRequest) -> TicketResponse:
        ticket = service.open_ticket(
            payload.account_id, payload.category, payload.priority, payload.description
        )
        return TicketResponse.model_validate(ticket, from_attributes=True)

    @router.post("/tickets/{ticket_id}/resolve", response_model=TicketResponse)
    def resolve_ticket(ticket_id: str) -> TicketResponse:
        try:
            return TicketResponse.model_validate(service.resolve(ticket_id), from_attributes=True)
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="ticket not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.post("/tickets/{ticket_id}/replies", response_model=TicketResponse)
    def reply(ticket_id: str, payload: ReplyRequest) -> TicketResponse:
        try:
            service.reply(ticket_id, payload.body, payload.author)
            return TicketResponse.model_validate(
                service.get_ticket(ticket_id), from_attributes=True
            )
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="ticket not found") from exc

    return router
