from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.modules.admin_center.application import AdminCenterService


class ReviewRuleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    auto_block_policy: bool
    subject_types: tuple[str, ...] = Field(min_length=1)
    version: str = Field(min_length=1)


class QualityBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer_id: str = Field(min_length=1)
    accuracy_bps: int = Field(ge=0, le=10_000)
    false_positive_bps: int = Field(ge=0, le=10_000)
    miss_bps: int = Field(ge=0, le=10_000)
    overturn_bps: int = Field(ge=0, le=10_000)
    avg_handle_seconds: int = Field(ge=0)
    complaint_bps: int = Field(ge=0, le=10_000)


class AlertBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    author_id: str = Field(min_length=1)
    alert_type: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    risk_level: str = Field(min_length=1)


class User360Body(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str = Field(min_length=1)
    phone: str = Field(min_length=7)
    real_name: str = ""
    asset_cents: int = Field(ge=0)
    membership_level: int = Field(ge=0)
    growth_level: int = Field(ge=0)
    sensitive: bool = False


class CsatBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int = Field(ge=1, le=5)


def build_admin_center_router(service: AdminCenterService) -> APIRouter:
    router = APIRouter(prefix="/admin/api/v1", tags=["admin-center"])

    @router.post("/review-rules", status_code=status.HTTP_201_CREATED)
    def add_rule(payload: ReviewRuleBody) -> dict[str, object]:
        return asdict(service.add_review_rule(**payload.model_dump()))

    @router.get("/review-rules")
    def list_rules() -> list[dict[str, object]]:
        return [asdict(rule) for rule in service.list_review_rules()]

    @router.post("/reviewer-quality", status_code=status.HTTP_201_CREATED)
    def reviewer_quality(payload: QualityBody) -> dict[str, object]:
        return asdict(service.record_reviewer_quality(**payload.model_dump()))

    @router.post("/author-alerts", status_code=status.HTTP_201_CREATED)
    def author_alert(payload: AlertBody) -> dict[str, object]:
        return asdict(service.create_author_alert(**payload.model_dump()))

    @router.post("/user-360")
    def user360(payload: User360Body) -> dict[str, object]:
        try:
            return asdict(service.user360(**payload.model_dump()))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @router.post("/support/tickets/{ticket_id}/csat")
    def csat(ticket_id: str, payload: CsatBody) -> dict[str, object]:
        return asdict(service.record_csat(ticket_id, payload.score))

    @router.get("/support/dashboard")
    def support_dashboard() -> dict[str, int]:
        return service.support_dashboard()

    return router
