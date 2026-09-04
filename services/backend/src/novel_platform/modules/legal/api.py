from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.modules.legal.application import LegalService


class CaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1)


class HoldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(min_length=1)


def build_legal_router(service: LegalService) -> APIRouter:
    router = APIRouter(prefix="/admin/api/v1/legal", tags=["legal"])

    @router.post("/cases", status_code=status.HTTP_201_CREATED)
    def open_case(payload: CaseRequest) -> dict[str, object]:
        return asdict(service.open_case(payload.subject))

    @router.post("/cases/{case_id}/holds", status_code=status.HTTP_201_CREATED)
    def hold(case_id: str, payload: HoldRequest) -> dict[str, object]:
        try:
            return asdict(service.hold(case_id, payload.resource_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="case not found") from exc

    @router.post("/holds/{hold_id}/release")
    def release(hold_id: str) -> dict[str, object]:
        try:
            return asdict(service.release(hold_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="hold not found") from exc

    return router
