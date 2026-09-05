from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import optional_session, require_account_access
from novel_platform.modules.library.application import LibraryService


class ShelfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    group_name: str = "default"


class ShelfEntryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    book_id: str
    group_name: str


def build_library_router(service: LibraryService, *, auth_required: bool = False) -> APIRouter:
    router = APIRouter(tags=["reader-library"])

    @router.get(
        "/bookshelf", response_model=list[ShelfEntryResponse], operation_id="reader_list_bookshelf"
    )
    def list_bookshelf(
        account_id: str, session: SessionClaims | None = Depends(optional_session)
    ) -> list[ShelfEntryResponse]:
        require_account_access(session, account_id, required=auth_required)
        return [
            ShelfEntryResponse.model_validate(entry, from_attributes=True)
            for entry in service.list(account_id)
        ]

    @router.post(
        "/books/{book_id}/bookshelf",
        response_model=ShelfEntryResponse,
        status_code=201,
        operation_id="reader_add_bookshelf",
    )
    def add_bookshelf(
        book_id: str,
        payload: ShelfRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> ShelfEntryResponse:
        require_account_access(session, payload.account_id, required=auth_required)
        entry = service.add(payload.account_id, book_id, payload.group_name)
        return ShelfEntryResponse.model_validate(entry, from_attributes=True)

    @router.delete(
        "/books/{book_id}/bookshelf", status_code=204, operation_id="reader_remove_bookshelf"
    )
    def remove_bookshelf(
        book_id: str, account_id: str, session: SessionClaims | None = Depends(optional_session)
    ) -> None:
        require_account_access(session, account_id, required=auth_required)
        service.remove(account_id, book_id)

    return router
