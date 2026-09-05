from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import optional_session, require_account_access
from novel_platform.modules.membership.domain import AccessMode, ChapterPolicy
from novel_platform.modules.reading.application import ContentAccessService, ReadingService
from novel_platform.modules.reading.domain import ProgressConflict, TtsMetadata


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


class TtsSegmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    text: str
    start_ms: int
    end_ms: int


class TtsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: str
    chapter_id: str
    access: str
    voice: str
    speed: float
    provider: str
    segments: list[TtsSegmentResponse]


def _response(progress: object) -> ProgressResponse:
    return ProgressResponse.model_validate(progress, from_attributes=True)


def _tts_response(metadata: TtsMetadata) -> TtsResponse:
    return TtsResponse(
        book_id=metadata.book_id,
        chapter_id=metadata.chapter_id,
        access=metadata.access.value,
        voice=metadata.voice,
        speed=metadata.speed,
        provider=metadata.provider,
        segments=[
            TtsSegmentResponse.model_validate(segment, from_attributes=True)
            for segment in metadata.segments
        ],
    )


def _chapter_policy(request: Request, chapter_id: str) -> ChapterPolicy:
    resolver = getattr(request.app.state, "chapter_policy_resolver", None)
    commerce = getattr(request.app.state, "commerce_service", None)
    if not callable(resolver):
        resolver = getattr(commerce, "get_chapter_policy", None)
    if not callable(resolver):
        resolver = getattr(commerce, "chapter_policy", None)
    if callable(resolver):
        policy = resolver(chapter_id)
        if isinstance(policy, ChapterPolicy):
            return policy
    policies = getattr(commerce, "_chapter_policies", None)
    policy = policies.get(chapter_id) if isinstance(policies, dict) else None
    if isinstance(policy, ChapterPolicy):
        return policy
    return ChapterPolicy(1, AccessMode.VIP_REQUIRED)


def build_reading_router(service: ReadingService, *, auth_required: bool = False) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["reader-reading"])

    @router.get(
        "/books/{book_id}/chapters/{chapter_id}/tts",
        response_model=TtsResponse,
        operation_id="reader_get_chapter_tts",
    )
    def get_chapter_tts(
        book_id: str,
        chapter_id: str,
        request: Request,
        account_id: str | None = None,
        voice: str = "female-1",
        speed: float = 1.0,
        session: SessionClaims | None = Depends(optional_session),
    ) -> TtsResponse:
        if voice not in {"female-1", "female-2", "male-1", "male-2"}:
            raise HTTPException(status_code=422, detail="unsupported TTS voice")
        if speed not in {0.75, 1.0, 1.25, 1.5, 2.0}:
            raise HTTPException(status_code=422, detail="unsupported TTS speed")

        content = getattr(request.app.state, "content_service", None)
        if content is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "TTS_CONTENT_PROVIDER_UNAVAILABLE",
                    "message": "content provider unavailable",
                },
            )
        try:
            book = content.get_book(book_id)
            chapter = content.get_chapter_for_book(book_id, chapter_id)
            if book.visibility.value != "PUBLIC" or chapter.published_version_id is None:
                raise KeyError(chapter_id)
            version = content.get_chapter_version(chapter.published_version_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="chapter not found") from exc

        if account_id is not None:
            require_account_access(session, account_id, required=True)

        chapter_policy = _chapter_policy(request, chapter_id)
        requires_account = chapter.commercial_policy.value != "FREE"
        purchased = False
        limited_free = chapter_policy.access_mode is AccessMode.LIMITED_FREE
        member_free = False
        if requires_account:
            if session is None or session.subject_type != "ACCOUNT":
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
            membership = getattr(request.app.state, "membership_service", None)
            membership_access = getattr(membership, "access", None)
            if callable(membership_access):
                member_mode = membership_access(
                    session.account_id,
                    chapter.id,
                    chapter_policy,
                    purchased,
                    book_id=book_id,
                )
                limited_free = limited_free or member_mode is AccessMode.LIMITED_FREE
                member_free = member_mode is AccessMode.MEMBER_FREE

        decision = ContentAccessService().check(
            book_available=True,
            chapter_available=(
                chapter.publish_state.value == "PUBLISHED"
                and chapter.visibility_state.value == "PUBLIC"
            ),
            restricted=False,
            policy=chapter.commercial_policy,
            purchased=purchased,
            limited_free=limited_free,
            member_free=member_free,
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=403,
                detail={"code": decision.result.value, "message": "chapter access required"},
            )
        return _tts_response(
            service.build_tts_metadata(
                book_id=book_id,
                chapter_id=chapter_id,
                content=version.content,
                access=decision.result,
                voice=voice,
                speed=speed,
            )
        )

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
