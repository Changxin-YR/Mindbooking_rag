from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.modules.community.application import CommunityService
from novel_platform.modules.community.domain import ReportCase


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_type: str = Field(min_length=1)
    content_id: str = Field(min_length=1)
    reporter_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ReportSubmissionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    reason: str


class ReportCaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    content_type: str
    content_id: str
    status: str
    submissions: list[ReportSubmissionResponse]


def _response(case: ReportCase) -> ReportCaseResponse:
    return ReportCaseResponse(
        id=case.id,
        content_type=case.content_type,
        content_id=case.content_id,
        status=case.status.value,
        submissions=[
            ReportSubmissionResponse(id=item.id, reason=item.reason) for item in case.submissions
        ],
    )


def build_community_router(service: CommunityService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/community", tags=["community"])

    @router.post(
        "/report-cases", response_model=ReportCaseResponse, status_code=status.HTTP_201_CREATED
    )
    def submit_report(payload: ReportRequest) -> ReportCaseResponse:
        try:
            return _response(
                service.submit_report(
                    payload.content_type, payload.content_id, payload.reporter_id, payload.reason
                )
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.get("/report-cases/{case_id}", response_model=ReportCaseResponse)
    def get_report_case(case_id: str) -> ReportCaseResponse:
        try:
            return _response(service.get_case(case_id))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="report case not found") from exc

    return router
