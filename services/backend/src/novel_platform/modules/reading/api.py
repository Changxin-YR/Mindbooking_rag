from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import optional_session, require_account_access
from novel_platform.modules.reading.application import ReadingService
from novel_platform.modules.reading.domain import ProgressConflict


class ProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    chapter_number: int
    position: int
    expected_revision: int
    session_id: str


class ProgressResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    book_id: str
    last_chapter_id: str | None
    last_chapter_number: int
    last_position: int
    furthest_chapter_id: str | None
    furthest_chapter_number: int
    furthest_position: int
    revision: int
    current_session_id: str | None


def _response(progress: object) -> ProgressResponse:
    return ProgressResponse.model_validate(progress, from_attributes=True)


def build_reading_router(service: ReadingService, *, auth_required: bool = False) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["reader-reading"])

    @router.get(
        "/books/{book_id}/progress",
        response_model=ProgressResponse,
        operation_id="reader_get_progress",
    )
    def get_progress(
        book_id: str,
        account_id: str,
        session: SessionClaims | None = Depends(optional_session),
    ) -> ProgressResponse:
        require_account_access(session, account_id, required=auth_required)
        return _response(service.get_progress(account_id, book_id))

    @router.put(
        "/books/{book_id}/progress",
        response_model=ProgressResponse,
        operation_id="reader_update_progress",
    )
    def update_progress(
        book_id: str,
        account_id: str,
        payload: ProgressRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> ProgressResponse:
        require_account_access(session, account_id, required=auth_required)
        try:
            progress = service.update_progress(
                account_id,
                book_id,
                chapter_id=payload.chapter_id,
                chapter_number=payload.chapter_number,
                position=payload.position,
                expected_revision=payload.expected_revision,
                session_id=payload.session_id,
            )
        except ProgressConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "REVISION_CONFLICT",
                    "message": "reading progress revision conflict",
                    "current": _response(exc.current).model_dump(),
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _response(progress)

    return router
