from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import optional_session, require_account_access
from novel_platform.modules.author.application import (
    AuthorApplication,
    AuthorProfileNotFoundError,
    DuplicateAuthorProfileError,
    DuplicatePenNameError,
)
from novel_platform.modules.author.domain import InvalidPenNameError


class AuthorProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    pen_name: str = Field(min_length=1, max_length=64)


class PenNameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pen_name: str = Field(min_length=1, max_length=64)


class AuthorProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    account_id: str
    pen_name: str
    normalized_pen_name: str


def build_author_router(
    application: AuthorApplication, *, auth_required: bool = False
) -> APIRouter:
    router = APIRouter(tags=["author"])

    @router.post(
        "/author/profiles",
        response_model=AuthorProfileResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_profile(
        payload: AuthorProfileRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> AuthorProfileResponse:
        require_account_access(session, payload.account_id, required=auth_required)
        try:
            result = application.create_profile(payload.account_id, payload.pen_name)
        except (DuplicateAuthorProfileError, DuplicatePenNameError) as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"code": "AUTHOR_UNIQUENESS_CONFLICT", "message": str(exc)},
            ) from exc
        except InvalidPenNameError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_PEN_NAME", "message": str(exc)},
            ) from exc
        return AuthorProfileResponse(
            id=result.id,
            account_id=result.account_id,
            pen_name=result.pen_name,
            normalized_pen_name=result.normalized_pen_name,
        )

    @router.get("/author/profile", response_model=AuthorProfileResponse)
    def get_current_profile(
        session: SessionClaims | None = Depends(optional_session),
    ) -> AuthorProfileResponse:
        if session is None or session.subject_type != "ACCOUNT":
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail={"code": "AUTHENTICATION_REQUIRED", "message": "account session required"},
            )
        try:
            result = application.profile_for_account(session.account_id)
        except AuthorProfileNotFoundError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "AUTHOR_PROFILE_NOT_FOUND", "message": str(exc)},
            ) from exc
        return AuthorProfileResponse(
            id=result.id,
            account_id=result.account_id,
            pen_name=result.pen_name,
            normalized_pen_name=result.normalized_pen_name,
        )

    @router.post("/author/profiles/{profile_id}/pen-name", response_model=AuthorProfileResponse)
    def change_pen_name(
        profile_id: str,
        payload: PenNameRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> AuthorProfileResponse:
        try:
            account_id = application.account_id_for_profile(profile_id)
        except AuthorProfileNotFoundError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "AUTHOR_PROFILE_NOT_FOUND", "message": str(exc)},
            ) from exc
        require_account_access(session, account_id, required=auth_required)
        try:
            result = application.change_pen_name(profile_id, payload.pen_name)
        except AuthorProfileNotFoundError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "AUTHOR_PROFILE_NOT_FOUND", "message": str(exc)},
            ) from exc
        except DuplicatePenNameError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"code": "PEN_NAME_ALREADY_USED", "message": str(exc)},
            ) from exc
        except InvalidPenNameError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_PEN_NAME", "message": str(exc)},
            ) from exc
        return AuthorProfileResponse(
            id=result.id,
            account_id=result.account_id,
            pen_name=result.pen_name,
            normalized_pen_name=result.normalized_pen_name,
        )

    return router
