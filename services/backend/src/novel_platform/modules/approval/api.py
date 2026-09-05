from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.http_auth import require_staff_session
from novel_platform.modules.approval.application import ApprovalService, MakerCheckerError
from novel_platform.modules.approval.domain import ApprovalRequest, ApprovalStatus


class CreateApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1)
    requester_id: str = Field(min_length=1)
    critical: bool


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approver_id: str = Field(min_length=1)
    decision: str = Field(pattern="^(APPROVE|REJECT)$")


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    action: str
    requester_id: str
    critical: bool
    status: ApprovalStatus


def _response(approval: ApprovalRequest) -> ApprovalResponse:
    return ApprovalResponse.model_validate(approval, from_attributes=True)


def build_approval_router(service: ApprovalService, *, auth_required: bool = False) -> APIRouter:
    router = APIRouter(prefix="/admin/api/v1/approvals", tags=["approval"])

    @router.post("", response_model=ApprovalResponse, status_code=status.HTTP_201_CREATED)
    def create_approval(payload: CreateApprovalRequest, request: Request) -> ApprovalResponse:
        requester_id = (
            require_staff_session(request).account_id if auth_required else payload.requester_id
        )
        return _response(service.request(payload.action, requester_id, payload.critical))

    @router.post("/{approval_id}/decision", response_model=ApprovalResponse)
    def decide(
        approval_id: str, payload: ApprovalDecisionRequest, request: Request
    ) -> ApprovalResponse:
        try:
            decision = service.approve if payload.decision == "APPROVE" else service.reject
            approver_id = (
                require_staff_session(request).account_id if auth_required else payload.approver_id
            )
            return _response(decision(approval_id, approver_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="approval not found") from exc
        except MakerCheckerError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return router
