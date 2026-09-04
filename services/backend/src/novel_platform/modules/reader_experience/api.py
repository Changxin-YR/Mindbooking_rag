from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.modules.content.application import ContentService
from novel_platform.modules.content.domain import (
    Book,
    BookLifecycle,
    BookMetadataVersion,
    CommercialPolicy,
)
from novel_platform.modules.reader_experience.application import ReaderExperienceService
from novel_platform.modules.reader_experience.domain import CorrectionKind


class CatalogItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    synopsis: str
    author_id: str
    channel: str
    category: str
    tags: tuple[str, ...]
    lifecycle: str
    visibility: str


class CatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CatalogItemResponse]
    total: int


class RatingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    overall_score: int = Field(ge=1, le=5)
    plot_score: int = Field(ge=1, le=5)
    character_score: int = Field(ge=1, le=5)
    writing_score: int = Field(ge=1, le=5)
    update_score: int = Field(ge=1, le=5)
    eligible_words: int = Field(ge=0)


class FollowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    target_type: str
    target_id: str = Field(min_length=1)


class GrowthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    points: int = Field(gt=0)


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    book_id: str = Field(min_length=1)
    chapter_id: str = Field(min_length=1)
    kind: CorrectionKind
    position: int = Field(ge=0)
    description: str = Field(min_length=1)


class MinorProtectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_minor: bool
    policy_version: str = Field(min_length=1)


def _catalog_item(book: Book, metadata: BookMetadataVersion) -> CatalogItemResponse:
    return CatalogItemResponse(
        id=book.id,
        title=metadata.title,
        synopsis=metadata.synopsis,
        author_id=book.author_id,
        channel=metadata.channel,
        category=metadata.category,
        tags=metadata.tags,
        lifecycle=book.lifecycle.value,
        visibility=book.visibility.value,
    )


def build_reader_experience_router(
    content: ContentService, service: ReaderExperienceService
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["reader-experience"])

    @router.get("/books", response_model=CatalogResponse, operation_id="reader_list_books")
    def list_books(
        channel: str | None = None,
        category: str | None = None,
        tag: str | None = None,
        lifecycle: BookLifecycle | None = None,
        commercial_policy: CommercialPolicy | None = None,
        q: str | None = None,
    ) -> CatalogResponse:
        items = [
            _catalog_item(book, metadata)
            for book, metadata in content.list_public_books(
                channel=channel,
                category=category,
                tag=tag,
                lifecycle=lifecycle,
                commercial_policy=commercial_policy,
                keyword=q,
            )
        ]
        return CatalogResponse(items=items, total=len(items))

    @router.post("/books/{book_id}/ratings", status_code=status.HTTP_201_CREATED)
    def rate(book_id: str, payload: RatingRequest) -> dict[str, object]:
        try:
            return asdict(service.rate(book_id=book_id, **payload.model_dump()))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @router.post("/social/follows", status_code=status.HTTP_201_CREATED)
    def follow(payload: FollowRequest) -> dict[str, object]:
        try:
            created = service.follow(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return {**payload.model_dump(), "created": created}

    @router.delete("/social/follows", status_code=status.HTTP_204_NO_CONTENT)
    def unfollow(payload: FollowRequest) -> None:
        try:
            service.unfollow(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @router.get("/accounts/{account_id}/follows")
    def following(account_id: str) -> dict[str, object]:
        return {"account_id": account_id, "items": service.following(account_id)}

    @router.post("/accounts/growth/events", status_code=status.HTTP_201_CREATED)
    def add_growth(payload: GrowthRequest) -> dict[str, object]:
        try:
            event = service.add_growth(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return asdict(event)

    @router.get("/accounts/{account_id}/growth")
    def growth(account_id: str) -> dict[str, object]:
        return asdict(service.growth(account_id))

    @router.post("/content-corrections", status_code=status.HTTP_201_CREATED)
    def correction(payload: CorrectionRequest) -> dict[str, object]:
        try:
            return asdict(service.submit_correction(**payload.model_dump()))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @router.put("/accounts/{account_id}/minor-protection")
    def minor_protection(account_id: str, payload: MinorProtectionRequest) -> dict[str, object]:
        try:
            protection = service.set_minor_protection(account_id, **payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return {
            "account_id": protection.account_id,
            "is_minor": protection.is_minor,
            "policy_version": protection.policy_version,
            "purchase_allowed": protection.purchase_allowed,
        }

    return router
