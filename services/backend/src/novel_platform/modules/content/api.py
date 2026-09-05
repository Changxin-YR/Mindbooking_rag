from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import (
    optional_session,
    require_account_access,
    require_staff_session,
)
from novel_platform.modules.content.application import ContentService
from novel_platform.modules.content.domain import CommercialPolicy
from novel_platform.modules.membership.domain import AccessMode, ChapterPolicy
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
    commercial_policy: CommercialPolicy = CommercialPolicy.FREE
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


class CommercialPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_coin: int


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


def build_content_routers(
    content: ContentService,
    *,
    auth_required: bool = False,
    account_for_author: Callable[[str], str] | None = None,
    configure_commercial_policy: Callable[[str, ChapterPolicy], object] | None = None,
    authorize_staff: Callable[[SessionClaims, str], None] | None = None,
) -> tuple[APIRouter, APIRouter, APIRouter]:
    reader = APIRouter(prefix="/api/v1", tags=["reader-content"])
    writer = APIRouter(prefix="/writer/api/v1", tags=["writer-content"])
    admin = APIRouter(prefix="/admin/api/v1", tags=["admin-content"])
    access = ContentAccessService()

    def require_writer(author_id: str, session: SessionClaims | None) -> None:
        if not auth_required:
            return
        if account_for_author is None:
            raise HTTPException(status_code=500, detail="writer ownership resolver unavailable")
        try:
            account_id = account_for_author(author_id)
        except KeyError, LookupError:
            raise HTTPException(
                status_code=403,
                detail={"code": "AUTHOR_ACCESS_DENIED", "message": "author profile not found"},
            ) from None
        require_account_access(session, account_id, required=True)

    def require_book_owner(book_id: str, session: SessionClaims | None) -> None:
        try:
            author_id = content.get_book(book_id).author_id
        except KeyError:
            raise HTTPException(status_code=404, detail="book not found") from None
        require_writer(author_id, session)

    def require_volume_owner(volume_id: str, session: SessionClaims | None) -> None:
        try:
            book_id = content.get_volume(volume_id).book_id
        except KeyError:
            raise HTTPException(status_code=404, detail="volume not found") from None
        require_book_owner(book_id, session)

    def require_chapter_owner(chapter_id: str, session: SessionClaims | None) -> None:
        try:
            volume_id = content.get_chapter(chapter_id).volume_id
        except KeyError:
            raise HTTPException(status_code=404, detail="chapter not found") from None
        require_volume_owner(volume_id, session)

    def require_commerce_staff(request: Request) -> None:
        if not auth_required:
            return
        claims = require_staff_session(request)
        if authorize_staff is not None:
            authorize_staff(claims, "commerce.write")

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
    def reader_get_chapter(
        book_id: str,
        chapter_id: str,
        request: Request,
        session: SessionClaims | None = Depends(optional_session),
    ) -> ChapterResponse:
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
        requires_account = chapter.commercial_policy is not CommercialPolicy.FREE
        require_account_access(
            session,
            session.account_id if session is not None else "",
            required=requires_account and session is not None,
        )
        purchased = False
        if requires_account:
            if session is None:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "CHAPTER_ACCESS_REQUIRED",
                        "message": "account session required",
                    },
                )
            commerce = getattr(request.app.state, "commerce_service", None)
            has_entitlement = getattr(commerce, "has_entitlement", None)
            if not callable(has_entitlement):
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "CHAPTER_ACCESS_PROVIDER_UNAVAILABLE",
                        "message": "chapter access provider unavailable",
                    },
                )
            purchased = bool(has_entitlement(session.account_id, chapter.id))
        decision = access.check(
            book_available=True,
            chapter_available=chapter.visibility_state.value == "PUBLIC",
            restricted=False,
            policy=chapter.commercial_policy,
            purchased=purchased,
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
    def writer_create_book(
        payload: CreateBookRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> BookResponse:
        require_writer(payload.author_id, session)
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
    def writer_create_volume(
        book_id: str,
        payload: CreateVolumeRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> VolumeResponse:
        require_book_owner(book_id, session)
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
        volume_id: str,
        payload: CreateChapterRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> ChapterWriteResponse:
        require_volume_owner(volume_id, session)
        if payload.commercial_policy is not CommercialPolicy.FREE:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "PLATFORM_COMMERCIAL_POLICY_REQUIRED",
                    "message": "commercial policy must be configured by platform staff",
                },
            )
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

    @admin.post(
        "/chapters/{chapter_id}/commercial-policy",
        response_model=ChapterWriteResponse,
        operation_id="admin_configure_chapter_commercial_policy",
    )
    def configure_chapter_commercial_policy(
        chapter_id: str,
        payload: CommercialPolicyRequest,
        request: Request,
    ) -> ChapterWriteResponse:
        require_commerce_staff(request)
        if configure_commercial_policy is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "COMMERCIAL_POLICY_PROVIDER_UNAVAILABLE",
                    "message": "commercial policy provider unavailable",
                },
            )
        if payload.price_coin <= 0:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_CHAPTER_PRICE", "message": "price_coin must be positive"},
            )
        try:
            configure_commercial_policy(
                chapter_id, ChapterPolicy(payload.price_coin, AccessMode.VIP_REQUIRED)
            )
            chapter = content.get_chapter(chapter_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="chapter not found") from exc
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
    def writer_save_draft(
        chapter_id: str,
        payload: DraftRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> DraftSnapshotResponse:
        require_chapter_owner(chapter_id, session)
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
        chapter_id: str,
        payload: VersionRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> ChapterVersionResponse:
        require_chapter_owner(chapter_id, session)
        try:
            version = content.create_chapter_version(chapter_id, payload.snapshot_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="chapter or snapshot not found") from exc
        return ChapterVersionResponse.model_validate(version, from_attributes=True)

    return reader, writer, admin
