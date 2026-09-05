from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from novel_platform.modules.search.application import SearchService
from novel_platform.modules.search.domain import SearchQuery, SearchResultPage, SearchSort


class SearchItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: str
    title: str
    synopsis: str
    author_name: str
    category: str
    channel: str
    status: str
    tags: tuple[str, ...]
    word_count: int
    popularity: int
    updated_at: datetime | int


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SearchItemResponse]
    total: int
    page: int
    page_size: int
    degraded: bool


def _response(page: SearchResultPage) -> SearchResponse:
    return SearchResponse(
        items=[
            SearchItemResponse.model_validate(item, from_attributes=True) for item in page.items
        ],
        total=page.total,
        page=page.page,
        page_size=page.page_size,
        degraded=page.degraded,
    )


def build_search_router(service: SearchService) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["search"])

    @router.get("/search", response_model=SearchResponse, operation_id="reader_search_books")
    def search_books(
        q: str = Query(default="", max_length=100),
        channel: str | None = Query(default=None, max_length=64),
        category: str | None = Query(default=None, max_length=64),
        status: str | None = Query(default=None, max_length=64),
        tag: str | None = Query(default=None, max_length=64),
        min_word_count: int | None = Query(default=None, ge=0),
        max_word_count: int | None = Query(default=None, ge=0),
        sort: SearchSort = SearchSort.RELEVANCE,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> SearchResponse:
        if (
            min_word_count is not None
            and max_word_count is not None
            and min_word_count > max_word_count
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INVALID_WORD_COUNT_RANGE",
                    "message": "min_word_count cannot exceed max_word_count",
                },
            )
        query = SearchQuery(
            query=q,
            channel=channel,
            category=category,
            status=status,
            tag=tag,
            min_word_count=min_word_count,
            max_word_count=max_word_count,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        return _response(service.search(query))

    return router
