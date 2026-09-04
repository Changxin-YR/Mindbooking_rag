from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

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


def build_library_router(service: LibraryService) -> APIRouter:
    router = APIRouter(tags=["reader-library"])

    @router.get(
        "/bookshelf", response_model=list[ShelfEntryResponse], operation_id="reader_list_bookshelf"
    )
    def list_bookshelf(account_id: str) -> list[ShelfEntryResponse]:
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
    def add_bookshelf(book_id: str, payload: ShelfRequest) -> ShelfEntryResponse:
        entry = service.add(payload.account_id, book_id, payload.group_name)
        return ShelfEntryResponse.model_validate(entry, from_attributes=True)

    @router.delete(
        "/books/{book_id}/bookshelf", status_code=204, operation_id="reader_remove_bookshelf"
    )
    def remove_bookshelf(book_id: str, account_id: str) -> None:
        service.remove(account_id, book_id)

    return router
