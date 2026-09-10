from collections.abc import Callable
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import (
    optional_session,
    require_account_access,
    require_staff_authorization,
)
from novel_platform.modules.author.application import AuthorProfileNotFoundError
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


def build_author_center_router(
    service: AuthorCenterService,
    *,
    auth_required: bool = False,
    account_for_author: Callable[[str], str] | None = None,
    author_for_book: Callable[[str], str] | None = None,
    chapter_for_book: Callable[[str, str], object] | None = None,
    authorize_staff: Callable[[SessionClaims, str], None] | None = None,
) -> tuple[APIRouter, APIRouter]:
    writer = APIRouter(prefix="/writer/api/v1", tags=["author-center"])
    admin = APIRouter(prefix="/admin/api/v1", tags=["author-center-admin"])

    def require_author(request: Request, author_id: str, session: SessionClaims | None) -> None:
        if not auth_required:
            return
        if account_for_author is None:
            require_account_access(session, author_id, required=True)
            return
        try:
            account_id = account_for_author(author_id)
        except AuthorProfileNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="author not found") from exc
        require_account_access(session, account_id, required=True)

    def require_book_author(
        request: Request,
        book_id: str,
        chapter_id: str,
        session: SessionClaims | None,
    ) -> None:
        if not auth_required:
            return
        if author_for_book is None:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "AUTHOR_ACCESS_CONFIGURATION_ERROR",
                    "message": "book ownership resolver is not configured",
                },
            )
        try:
            author_id = author_for_book(book_id)
        except LookupError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="book not found") from exc
        require_author(request, author_id, session)
        if chapter_for_book is None:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "CHAPTER_ACCESS_CONFIGURATION_ERROR",
                    "message": "chapter ownership resolver is not configured",
                },
            )
        try:
            chapter_for_book(book_id, chapter_id)
        except LookupError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="chapter not found") from exc

    def require_staff(request: Request, permission: str) -> None:
        if not auth_required:
            return
        require_staff_authorization(request, authorize_staff, permission)

    @writer.post("/authors/{author_id}/writing-stats", status_code=status.HTTP_201_CREATED)
    def writing_stat(
        author_id: str,
        payload: WritingStatBody,
        request: Request,
        session: SessionClaims | None = Depends(optional_session),
    ) -> dict[str, object]:
        require_author(request, author_id, session)
        return asdict(service.record_daily_writing(author_id, **payload.model_dump()))

    @writer.get("/authors/{author_id}/calendar")
    def calendar(
        author_id: str,
        request: Request,
        session: SessionClaims | None = Depends(optional_session),
    ) -> list[dict[str, object]]:
        require_author(request, author_id, session)
        return [asdict(item) for item in service.calendar(author_id)]

    @admin.post("/author-tasks", status_code=status.HTTP_201_CREATED)
    def create_task(payload: TaskBody, request: Request) -> dict[str, object]:
        require_staff(request, "operation.write")
        return asdict(service.create_task(**payload.model_dump()))

    @writer.post("/authors/{author_id}/tasks/{task_id}/progress")
    def progress_task(
        author_id: str,
        task_id: str,
        payload: TaskProgressBody,
        request: Request,
        session: SessionClaims | None = Depends(optional_session),
    ) -> dict[str, object]:
        if payload.author_id != author_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "AUTHOR_ACCESS_DENIED",
                    "message": "path author does not match body",
                },
            )
        require_author(request, author_id, session)
        try:
            return asdict(service.progress_task(task_id=task_id, **payload.model_dump()))
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found") from exc

    @admin.post("/campaigns", status_code=status.HTTP_201_CREATED)
    def campaign(payload: CampaignBody, request: Request) -> dict[str, object]:
        require_staff(request, "operation.write")
        return asdict(service.create_campaign(**payload.model_dump()))

    @writer.post("/campaigns/{campaign_id}/enroll")
    def enroll(
        campaign_id: str,
        payload: EnrollmentBody,
        request: Request,
        session: SessionClaims | None = Depends(optional_session),
    ) -> dict[str, object]:
        require_author(request, payload.author_id, session)
        try:
            return {
                "campaign_id": campaign_id,
                "author_id": payload.author_id,
                "created": service.enroll_campaign(payload.author_id, campaign_id),
            }
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="campaign not found") from exc

    @admin.post("/learning", status_code=status.HTTP_201_CREATED)
    def learning(payload: LearningBody, request: Request) -> dict[str, object]:
        require_staff(request, "operation.write")
        return asdict(service.publish_learning(**payload.model_dump()))

    @writer.post("/learning/{content_id}/progress")
    def learning_progress(
        content_id: str,
        payload: LearningProgressBody,
        request: Request,
        session: SessionClaims | None = Depends(optional_session),
    ) -> dict[str, object]:
        require_author(request, payload.author_id, session)
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
    def funnel(
        book_id: str,
        chapter_id: str,
        payload: FunnelBody,
        request: Request,
        session: SessionClaims | None = Depends(optional_session),
    ) -> dict[str, object]:
        require_book_author(request, book_id, chapter_id, session)
        return asdict(service.record_chapter_funnel(book_id, chapter_id, **payload.model_dump()))

    @writer.post("/appeals", status_code=status.HTTP_201_CREATED)
    def appeal(
        payload: AppealBody,
        request: Request,
        session: SessionClaims | None = Depends(optional_session),
    ) -> dict[str, object]:
        require_author(request, payload.author_id, session)
        return asdict(service.open_appeal(**payload.model_dump()))

    return writer, admin
