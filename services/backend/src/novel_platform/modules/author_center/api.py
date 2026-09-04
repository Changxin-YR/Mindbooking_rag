from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.modules.author_center.application import AuthorCenterService


class WritingStatBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_date: str = Field(min_length=1)
    words: int = Field(ge=0)
    goal: int = Field(ge=0)


class TaskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1)
    title: str = Field(min_length=1)
    target: int = Field(gt=0)


class TaskProgressBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    author_id: str = Field(min_length=1)
    progress: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1)


class CampaignBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    start_date: str = Field(min_length=1)
    end_date: str = Field(min_length=1)


class EnrollmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    author_id: str = Field(min_length=1)


class LearningBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field(min_length=1)
    title: str = Field(min_length=1)


class LearningProgressBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    author_id: str = Field(min_length=1)
    percent: int = Field(ge=0, le=100)


class FunnelBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entrants: int = Field(ge=0)
    completion_bps: int = Field(ge=0, le=10_000)
    next_chapter_bps: int = Field(ge=0, le=10_000)
    subscription_bps: int = Field(ge=0, le=10_000)


class AppealBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    author_id: str = Field(min_length=1)
    subject_type: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


def build_author_center_router(service: AuthorCenterService) -> tuple[APIRouter, APIRouter]:
    writer = APIRouter(prefix="/writer/api/v1", tags=["author-center"])
    admin = APIRouter(prefix="/admin/api/v1", tags=["author-center-admin"])

    @writer.post("/authors/{author_id}/writing-stats", status_code=status.HTTP_201_CREATED)
    def writing_stat(author_id: str, payload: WritingStatBody) -> dict[str, object]:
        return asdict(service.record_daily_writing(author_id, **payload.model_dump()))

    @writer.get("/authors/{author_id}/calendar")
    def calendar(author_id: str) -> list[dict[str, object]]:
        return [asdict(item) for item in service.calendar(author_id)]

    @admin.post("/author-tasks", status_code=status.HTTP_201_CREATED)
    def create_task(payload: TaskBody) -> dict[str, object]:
        return asdict(service.create_task(**payload.model_dump()))

    @writer.post("/authors/{author_id}/tasks/{task_id}/progress")
    def progress_task(task_id: str, payload: TaskProgressBody) -> dict[str, object]:
        try:
            return asdict(service.progress_task(task_id=task_id, **payload.model_dump()))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found") from exc

    @admin.post("/campaigns", status_code=status.HTTP_201_CREATED)
    def campaign(payload: CampaignBody) -> dict[str, object]:
        return asdict(service.create_campaign(**payload.model_dump()))

    @writer.post("/campaigns/{campaign_id}/enroll")
    def enroll(campaign_id: str, payload: EnrollmentBody) -> dict[str, object]:
        try:
            return {
                "campaign_id": campaign_id,
                "author_id": payload.author_id,
                "created": service.enroll_campaign(payload.author_id, campaign_id),
            }
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="campaign not found") from exc

    @admin.post("/learning", status_code=status.HTTP_201_CREATED)
    def learning(payload: LearningBody) -> dict[str, object]:
        return asdict(service.publish_learning(**payload.model_dump()))

    @writer.post("/learning/{content_id}/progress")
    def learning_progress(content_id: str, payload: LearningProgressBody) -> dict[str, object]:
        try:
            value = service.mark_learning_progress(content_id=content_id, **payload.model_dump())
        except KeyError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="learning content not found"
            ) from exc
        return {"content_id": content_id, "author_id": payload.author_id, "percent": value}

    @writer.post(
        "/books/{book_id}/chapters/{chapter_id}/funnel", status_code=status.HTTP_201_CREATED
    )
    def funnel(book_id: str, chapter_id: str, payload: FunnelBody) -> dict[str, object]:
        return asdict(service.record_chapter_funnel(book_id, chapter_id, **payload.model_dump()))

    @writer.post("/appeals", status_code=status.HTTP_201_CREATED)
    def appeal(payload: AppealBody) -> dict[str, object]:
        return asdict(service.open_appeal(**payload.model_dump()))

    return writer, admin
