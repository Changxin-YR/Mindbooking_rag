from collections.abc import Callable
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import require_staff_authorization
from novel_platform.modules.copyright.application import CopyrightService


class DossierRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: str = Field(min_length=1)


class RightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str = Field(min_length=1)
    language: str = Field(min_length=1)
    media: str = Field(min_length=1)
    exclusive: bool
    start_year: int = Field(ge=1900)
    end_year: int = Field(gt=1900)


class ComplaintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: str = Field(min_length=1)
    claimant_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class EvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)


class CounterNoticeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notice: str = Field(min_length=1)


def build_copyright_router(
    service: CopyrightService,
    *,
    auth_required: bool = False,
    authorize_staff: Callable[[SessionClaims, str], None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/admin/api/v1/copyright", tags=["copyright"])

    def require_copyright_staff(request: Request) -> None:
        if auth_required:
            require_staff_authorization(request, authorize_staff, "legal.write")

    @router.post("/dossiers", status_code=status.HTTP_201_CREATED)
    def create_dossier(payload: DossierRequest, request: Request) -> dict[str, object]:
        require_copyright_staff(request)
        return asdict(service.create_dossier(payload.book_id))

    @router.post("/dossiers/{dossier_id}/rights", status_code=status.HTTP_201_CREATED)
    def add_right(dossier_id: str, payload: RightRequest, request: Request) -> dict[str, object]:
        require_copyright_staff(request)
        try:
            return asdict(service.add_right(dossier_id, **payload.model_dump()))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="dossier not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.post("/complaints", status_code=status.HTTP_201_CREATED)
    def complain(payload: ComplaintRequest, request: Request) -> dict[str, object]:
        require_copyright_staff(request)
        return asdict(service.complain(**payload.model_dump()))

    @router.post("/complaints/{complaint_id}/evidence")
    def evidence(
        complaint_id: str, payload: EvidenceRequest, request: Request
    ) -> dict[str, object]:
        require_copyright_staff(request)
        try:
            return asdict(service.attach_evidence(complaint_id, payload.evidence_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="complaint not found") from exc

    @router.post("/complaints/{complaint_id}/counter-notice")
    def counter_notice(
        complaint_id: str, payload: CounterNoticeRequest, request: Request
    ) -> dict[str, object]:
        require_copyright_staff(request)
        try:
            return asdict(service.counter_notice(complaint_id, payload.notice))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="complaint not found") from exc

    return router
