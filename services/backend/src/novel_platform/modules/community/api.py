from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import optional_session, require_account_access, require_session
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


def build_community_router(service: CommunityService, *, auth_required: bool = False) -> APIRouter:
    router = APIRouter(prefix="/api/v1/community", tags=["community"])

    @router.post(
        "/report-cases", response_model=ReportCaseResponse, status_code=status.HTTP_201_CREATED
    )
    def submit_report(
        payload: ReportRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> ReportCaseResponse:
        require_account_access(session, payload.reporter_id, required=auth_required)
        try:
            return _response(
                service.submit_report(
                    payload.content_type, payload.content_id, payload.reporter_id, payload.reason
                )
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.get("/report-cases/{case_id}", response_model=ReportCaseResponse)
    def get_report_case(
        case_id: str,
        request: Request,
        session: SessionClaims | None = Depends(optional_session),
    ) -> ReportCaseResponse:
        try:
            case = service.get_case(case_id)
            if auth_required:
                claims = require_session(request)
                if not any(item.reporter_id == claims.account_id for item in case.submissions):
                    raise HTTPException(
                        status.HTTP_403_FORBIDDEN,
                        detail={
                            "code": "REPORT_CASE_ACCESS_DENIED",
                            "message": "report is not owned by account",
                        },
                    )
            return _response(case)
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="report case not found") from exc

    return router
