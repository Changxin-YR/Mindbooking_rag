from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

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


def build_author_router(application: AuthorApplication) -> APIRouter:
    router = APIRouter(tags=["author"])

    @router.post(
        "/author/profiles",
        response_model=AuthorProfileResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_profile(payload: AuthorProfileRequest) -> AuthorProfileResponse:
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

    @router.post("/author/profiles/{profile_id}/pen-name", response_model=AuthorProfileResponse)
    def change_pen_name(profile_id: str, payload: PenNameRequest) -> AuthorProfileResponse:
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
