from collections.abc import Callable
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import require_staff_authorization
from novel_platform.modules.legal.application import LegalService


class CaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1)


class HoldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(min_length=1)


def build_legal_router(
    service: LegalService,
    *,
    auth_required: bool = False,
    authorize_staff: Callable[[SessionClaims, str], None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/admin/api/v1/legal", tags=["legal"])

    def require_legal_staff(request: Request) -> None:
        if auth_required:
            require_staff_authorization(request, authorize_staff, "legal.write")

    @router.post("/cases", status_code=status.HTTP_201_CREATED)
    def open_case(payload: CaseRequest, request: Request) -> dict[str, object]:
        require_legal_staff(request)
        return asdict(service.open_case(payload.subject))

    @router.post("/cases/{case_id}/holds", status_code=status.HTTP_201_CREATED)
    def hold(case_id: str, payload: HoldRequest, request: Request) -> dict[str, object]:
        require_legal_staff(request)
        try:
            return asdict(service.hold(case_id, payload.resource_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="case not found") from exc

    @router.post("/holds/{hold_id}/release")
    def release(hold_id: str, request: Request) -> dict[str, object]:
        require_legal_staff(request)
        try:
            return asdict(service.release(hold_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="hold not found") from exc

    return router
