from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from novel_platform.modules.content.application import ContentService
from novel_platform.modules.content.domain import CommercialPolicy
from novel_platform.modules.reading.application import ContentAccessService


class CreateBookRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_id: str
    title: str
    synopsis: str = ""
    channel: str = "UNSPECIFIED"
    category: str = ""
    tags: tuple[str, ...] = ()


class BookResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    lifecycle: str
    visibility: str


class ReaderChapterSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    number: int
    title: str
    commercial_policy: str


class ReaderBookDetailResponse(BaseModel):
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
    chapters: list[ReaderChapterSummary]


class VolumeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    book_id: str
    number: int
    title: str


class CreateVolumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    number: int


class CreateChapterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    commercial_policy: CommercialPolicy
    number: int | None = None


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    save_mode: str = "AUTO"
    expected_revision: int | None = None


class VersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str | None = None


class DraftSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    chapter_id: str
    revision: int
    content: str
    save_mode: str


class ChapterVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    chapter_id: str
    version: int
    content: str
    word_count: int


class ChapterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    book_id: str
    title: str
    content: str
    commercial_policy: str
    access: str


class ChapterWriteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    volume_id: str
    number: int
    title: str
    commercial_policy: str


def _book_response(content: ContentService, book_id: str, public: bool = False) -> BookResponse:
    try:
        book = content.get_book(book_id)
        if public and book.visibility.value != "PUBLIC":
            raise KeyError(book_id)
        metadata = content.get_book_metadata(book_id, public_only=public)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="book not found") from exc
    return BookResponse(
        id=book.id,
        title=metadata.title,
        lifecycle=book.lifecycle.value,
        visibility=book.visibility.value,
    )


def build_content_routers(content: ContentService) -> tuple[APIRouter, APIRouter, APIRouter]:
    reader = APIRouter(prefix="/api/v1", tags=["reader-content"])
    writer = APIRouter(prefix="/writer/api/v1", tags=["writer-content"])
    admin = APIRouter(prefix="/admin/api/v1", tags=["admin-content"])
    access = ContentAccessService()

    @reader.get(
        "/books/{book_id}", response_model=ReaderBookDetailResponse, operation_id="reader_get_book"
    )
    def reader_get_book(book_id: str) -> ReaderBookDetailResponse:
        try:
            book = content.get_book(book_id)
            if book.visibility.value != "PUBLIC":
                raise KeyError(book_id)
            metadata = content.get_book_metadata(book_id, public_only=True)
            chapters = [
                ReaderChapterSummary(
                    id=chapter.id,
                    number=chapter.number,
                    title=chapter.title,
                    commercial_policy=chapter.commercial_policy.value,
                )
                for chapter in content.list_chapters(book_id)
                if chapter.published_version_id is not None
            ]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="book not found") from exc
        return ReaderBookDetailResponse(
            id=book.id,
            title=metadata.title,
            synopsis=metadata.synopsis,
            author_id=book.author_id,
            channel=metadata.channel,
            category=metadata.category,
            tags=metadata.tags,
            lifecycle=book.lifecycle.value,
            visibility=book.visibility.value,
            chapters=chapters,
        )

    @reader.get(
        "/books/{book_id}/chapters/{chapter_id}",
        response_model=ChapterResponse,
        operation_id="reader_get_chapter",
    )
    def reader_get_chapter(book_id: str, chapter_id: str) -> ChapterResponse:
        try:
            book = content.get_book(book_id)
            if book.visibility.value != "PUBLIC":
                raise KeyError(chapter_id)
            chapter = content.get_chapter_for_book(book_id, chapter_id)
            if chapter.published_version_id is None:
                raise KeyError(chapter_id)
            version = content.get_chapter_version(chapter.published_version_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="chapter not found") from exc
        decision = access.check(
            book_available=True,
            chapter_available=chapter.visibility_state.value == "PUBLIC",
            restricted=False,
            policy=chapter.commercial_policy,
            purchased=False,
            limited_free=False,
            member_free=False,
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=403,
                detail={"code": decision.result.value, "message": "chapter access required"},
            )
        return ChapterResponse(
            id=chapter.id,
            book_id=book_id,
            title=chapter.title,
            content=version.content,
            commercial_policy=chapter.commercial_policy.value,
            access=decision.result.value,
        )

    @writer.post(
        "/books", response_model=BookResponse, status_code=201, operation_id="writer_create_book"
    )
    def writer_create_book(payload: CreateBookRequest) -> BookResponse:
        book = content.create_book(
            payload.author_id,
            payload.title,
            payload.synopsis,
            payload.channel,
            payload.category,
            payload.tags,
        )
        return _book_response(content, book.id)

    @writer.post(
        "/books/{book_id}/volumes",
        response_model=VolumeResponse,
        status_code=201,
        operation_id="writer_create_volume",
    )
    def writer_create_volume(book_id: str, payload: CreateVolumeRequest) -> VolumeResponse:
        try:
            volume = content.create_volume(book_id, payload.title, payload.number)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="book not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return VolumeResponse.model_validate(volume, from_attributes=True)

    @writer.post(
        "/volumes/{volume_id}/chapters",
        response_model=ChapterWriteResponse,
        status_code=201,
        operation_id="writer_create_chapter",
    )
    def writer_create_chapter(
        volume_id: str, payload: CreateChapterRequest
    ) -> ChapterWriteResponse:
        try:
            chapter = content.create_chapter(
                volume_id, payload.title, payload.commercial_policy, payload.number
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="volume not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ChapterWriteResponse(
            id=chapter.id,
            volume_id=chapter.volume_id,
            number=chapter.number,
            title=chapter.title,
            commercial_policy=chapter.commercial_policy.value,
        )

    @writer.post(
        "/chapters/{chapter_id}/drafts",
        response_model=DraftSnapshotResponse,
        status_code=201,
        operation_id="writer_save_draft",
    )
    def writer_save_draft(chapter_id: str, payload: DraftRequest) -> DraftSnapshotResponse:
        try:
            snapshot = content.save_draft(
                chapter_id, payload.content, payload.save_mode, payload.expected_revision
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="chapter not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return DraftSnapshotResponse.model_validate(snapshot, from_attributes=True)

    @writer.post(
        "/chapters/{chapter_id}/versions",
        response_model=ChapterVersionResponse,
        status_code=201,
        operation_id="writer_create_chapter_version",
    )
    def writer_create_chapter_version(
        chapter_id: str, payload: VersionRequest
    ) -> ChapterVersionResponse:
        try:
            version = content.create_chapter_version(chapter_id, payload.snapshot_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="chapter or snapshot not found") from exc
        return ChapterVersionResponse.model_validate(version, from_attributes=True)

    return reader, writer, admin
