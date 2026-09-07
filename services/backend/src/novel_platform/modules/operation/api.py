from collections.abc import Callable
from dataclasses import asdict

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import require_staff_authorization
from novel_platform.modules.operation.application import OperationService
from novel_platform.modules.operation.domain import RankingKind, RetentionAction, RetentionPolicy


class RankingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_ids: list[str] = Field(min_length=1)
    kind: RankingKind
    scores: list[int] = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)


class EditorialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: str = Field(min_length=1)
    position: int = Field(ge=1)
    snapshot_id: str = Field(min_length=1)


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    book_ids: list[str] = Field(min_length=1)
    personalized: bool = False


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requester_id: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)


class RetentionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_type: str = Field(min_length=1)
    action: RetentionAction
    days: int = Field(ge=0)


class CampaignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    start_date: str = Field(min_length=1)
    end_date: str = Field(min_length=1)


class RewardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: str = Field(min_length=1)
    reward_type: str = Field(min_length=1)
    amount: int = Field(gt=0)


def build_operation_router(
    service: OperationService,
    *,
    auth_required: bool = False,
    authorize_staff: Callable[[SessionClaims, str], None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/admin/api/v1/operation", tags=["operation"])

    def require_operation_staff(request: Request) -> None:
        if auth_required:
            require_staff_authorization(request, authorize_staff, "operation.write")

    @router.post("/rankings", status_code=status.HTTP_201_CREATED)
    def publish_ranking(payload: RankingRequest, request: Request) -> list[dict[str, object]]:
        require_operation_staff(request)
        try:
            return [asdict(item) for item in service.publish_ranking(**payload.model_dump())]
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @router.post("/editorial-slots", status_code=status.HTTP_201_CREATED)
    def editorial_slot(payload: EditorialRequest, request: Request) -> dict[str, object]:
        require_operation_staff(request)
        try:
            return asdict(service.editorial_slot(**payload.model_dump()))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @router.post("/recommendations", status_code=status.HTTP_201_CREATED)
    def recommend(payload: RecommendationRequest, request: Request) -> list[dict[str, object]]:
        require_operation_staff(request)
        return [asdict(item) for item in service.recommend(**payload.model_dump())]

    @router.post("/exports", status_code=status.HTTP_202_ACCEPTED)
    def export(payload: ExportRequest, request: Request) -> dict[str, object]:
        require_operation_staff(request)
        return asdict(service.request_export(**payload.model_dump()))

    @router.post("/retention-policies", status_code=status.HTTP_201_CREATED)
    def retention(payload: RetentionRequest, request: Request) -> dict[str, object]:
        require_operation_staff(request)
        return asdict(service.set_retention_policy(RetentionPolicy(**payload.model_dump())))

    @router.post("/campaigns", status_code=status.HTTP_201_CREATED)
    def campaign(payload: CampaignRequest, request: Request) -> dict[str, object]:
        require_operation_staff(request)
        try:
            return asdict(service.create_campaign(**payload.model_dump()))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @router.post("/rewards", status_code=status.HTTP_201_CREATED)
    def reward(
        payload: RewardRequest,
        request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, object]:
        require_operation_staff(request)
        if not idempotency_key:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail="IDEMPOTENCY_KEY_REQUIRED"
            )
        try:
            return asdict(
                service.grant_reward(idempotency_key=idempotency_key, **payload.model_dump())
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return router


def build_reader_operation_router(service: OperationService) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["reader-operation"])

    aliases = {
        "hot": RankingKind.ALGORITHM,
        "popular": RankingKind.ALGORITHM,
        "algorithm": RankingKind.ALGORITHM,
        "recommendation": RankingKind.RECOMMENDATION_SCORE,
        "recommendation_score": RankingKind.RECOMMENDATION_SCORE,
        "editorial": RankingKind.EDITORIAL,
        "campaign": RankingKind.CAMPAIGN,
    }

    def resolve_kind(value: str) -> RankingKind:
        normalized = value.strip().lower()
        try:
            alias = aliases.get(normalized)
            return alias if alias is not None else RankingKind(value.strip().upper())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "RANKING_KIND_INVALID", "message": "unsupported ranking kind"},
            ) from exc

    def ranking_items(kind: str) -> list[dict[str, object]]:
        return [asdict(item) for item in service.public_rankings(resolve_kind(kind))]

    @router.get("/rankings")
    def list_public_rankings(kind: str = "ALGORITHM") -> list[dict[str, object]]:
        return ranking_items(kind)

    @router.get("/rankings/{kind}")
    def list_public_rankings_by_path(kind: str) -> list[dict[str, object]]:
        return ranking_items(kind)

    @router.get("/rankings/{kind}/explanation")
    def ranking_explanation(kind: str) -> dict[str, object]:
        resolved = resolve_kind(kind)
        labels = {
            RankingKind.ALGORITHM: ("热度上升", "按公开热度快照排序", "日榜"),
            RankingKind.RECOMMENDATION_SCORE: ("推荐榜", "按推荐分排序", "日榜"),
            RankingKind.EDITORIAL: ("编辑精选", "由编辑策划排序", "不定期"),
            RankingKind.CAMPAIGN: ("活动榜", "按活动规则快照排序", "活动周期"),
        }
        title, rule, period = labels[resolved]
        return {
            "kind": resolved.value,
            "title": title,
            "rule": rule,
            "update_period": period,
            "data_time": "latest_snapshot",
        }

    return router
