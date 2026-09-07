from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import optional_session, require_account_access
from novel_platform.modules.content.application import ContentService
from novel_platform.modules.library.application import LibraryService
from novel_platform.modules.library.domain import BookshelfEntry


class ShelfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    group_name: str = "default"


class ShelfEntryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    book_id: str
    group_name: str
    title: str | None = None
    synopsis: str | None = None
    author_id: str | None = None
    lifecycle: str | None = None
    visibility: str | None = None
    availability: str | None = None


def build_library_router(
    service: LibraryService,
    *,
    auth_required: bool = False,
    content: ContentService | None = None,
) -> APIRouter:
    router = APIRouter(tags=["reader-library"])

    def response(entry: BookshelfEntry) -> ShelfEntryResponse:
        values = asdict(entry)  # explicit DTO boundary; never serialize the domain object directly
        values.pop("added_at", None)
        if content is not None:
            try:
                book = content.get_book(str(values["book_id"]))
                metadata = content.get_book_metadata(book.id, public_only=True)
            except KeyError:
                # A shelf entry survives a takedown so users can see why it is unavailable.
                try:
                    book = content.get_book(str(values["book_id"]))
                    metadata = content.get_book_metadata(book.id)
                except KeyError:
                    return ShelfEntryResponse(**values, availability="NOT_FOUND")
                return ShelfEntryResponse(
                    **values,
                    title=metadata.title,
                    synopsis=metadata.synopsis,
                    author_id=book.author_id,
                    lifecycle=book.lifecycle.value,
                    visibility=book.visibility.value,
                    availability="UNAVAILABLE",
                )
            return ShelfEntryResponse(
                **values,
                title=metadata.title,
                synopsis=metadata.synopsis,
                author_id=book.author_id,
                lifecycle=book.lifecycle.value,
                visibility=book.visibility.value,
                availability="AVAILABLE" if book.visibility.value == "PUBLIC" else "UNAVAILABLE",
            )
        return ShelfEntryResponse(**values)

    @router.get(
        "/bookshelf", response_model=list[ShelfEntryResponse], operation_id="reader_list_bookshelf"
    )
    def list_bookshelf(
        account_id: str, session: SessionClaims | None = Depends(optional_session)
    ) -> list[ShelfEntryResponse]:
        require_account_access(session, account_id, required=auth_required)
        return [response(entry) for entry in service.list(account_id)]

    @router.get(
        "/books/{book_id}/bookshelf/status",
        response_model=dict[str, object],
        operation_id="reader_bookshelf_status",
    )
    def bookshelf_status(
        book_id: str,
        account_id: str,
        session: SessionClaims | None = Depends(optional_session),
    ) -> dict[str, object]:
        require_account_access(session, account_id, required=auth_required)
        return {"account_id": account_id, "book_id": book_id, "in_bookshelf": any(
            entry.book_id == book_id for entry in service.list(account_id)
        )}

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
        if content is not None:
            try:
                book = content.get_book(book_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="book not found") from exc
            if book.visibility.value != "PUBLIC":
                raise HTTPException(status_code=404, detail="book unavailable")
        try:
            entry = service.add(payload.account_id, book_id, payload.group_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="book not found") from exc
        return response(entry)

    @router.delete(
        "/books/{book_id}/bookshelf", status_code=204, operation_id="reader_remove_bookshelf"
    )
    def remove_bookshelf(
        book_id: str, account_id: str, session: SessionClaims | None = Depends(optional_session)
    ) -> None:
        require_account_access(session, account_id, required=auth_required)
        service.remove(account_id, book_id)

    return router
