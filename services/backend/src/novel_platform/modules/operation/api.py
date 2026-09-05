from dataclasses import asdict

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

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


def build_operation_router(service: OperationService) -> APIRouter:
    router = APIRouter(prefix="/admin/api/v1/operation", tags=["operation"])

    @router.post("/rankings", status_code=status.HTTP_201_CREATED)
    def publish_ranking(payload: RankingRequest) -> list[dict[str, object]]:
        try:
            return [asdict(item) for item in service.publish_ranking(**payload.model_dump())]
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @router.post("/editorial-slots", status_code=status.HTTP_201_CREATED)
    def editorial_slot(payload: EditorialRequest) -> dict[str, object]:
        try:
            return asdict(service.editorial_slot(**payload.model_dump()))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @router.post("/recommendations", status_code=status.HTTP_201_CREATED)
    def recommend(payload: RecommendationRequest) -> list[dict[str, object]]:
        return [asdict(item) for item in service.recommend(**payload.model_dump())]

    @router.post("/exports", status_code=status.HTTP_202_ACCEPTED)
    def export(payload: ExportRequest) -> dict[str, object]:
        return asdict(service.request_export(**payload.model_dump()))

    @router.post("/retention-policies", status_code=status.HTTP_201_CREATED)
    def retention(payload: RetentionRequest) -> dict[str, object]:
        return asdict(service.set_retention_policy(RetentionPolicy(**payload.model_dump())))

    @router.post("/campaigns", status_code=status.HTTP_201_CREATED)
    def campaign(payload: CampaignRequest) -> dict[str, object]:
        try:
            return asdict(service.create_campaign(**payload.model_dump()))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @router.post("/rewards", status_code=status.HTTP_201_CREATED)
    def reward(
        payload: RewardRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, object]:
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

    @router.get("/rankings")
    def list_public_rankings(kind: RankingKind = RankingKind.ALGORITHM) -> list[dict[str, object]]:
        return [asdict(item) for item in service.public_rankings(kind)]

    return router
