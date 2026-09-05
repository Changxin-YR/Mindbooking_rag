from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import require_session, require_staff_session
from novel_platform.modules.platform.application import (
    AccessDeniedError,
    DuplicateStaffError,
    PlatformApplication,
    StaffNotFoundError,
)
from novel_platform.modules.platform.domain import StaffStatus


class StaffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_code: str = Field(min_length=1)
    department: str = Field(min_length=1)


class StaffResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    employee_code: str
    department: str
    status: str


class PermissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permission: str = Field(min_length=1)


class DataScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_type: str = Field(min_length=1)
    scope_value: str = Field(min_length=1)


class StaffStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: StaffStatus


class AccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: str = Field(min_length=1)
    permission: str = Field(min_length=1)
    scope_type: str = Field(min_length=1)
    scope_value: str = Field(min_length=1)


def build_platform_router(
    application: PlatformApplication,
    *,
    on_staff_inactive: Callable[[str], None] | None = None,
    auth_required: bool = False,
    authorize_staff: Callable[[SessionClaims, str], None] | None = None,
) -> APIRouter:
    router = APIRouter(tags=["platform"])

    def require_platform_admin(request: Request) -> None:
        if not auth_required:
            return
        claims = require_session(request)
        require_staff_session(request)
        if authorize_staff is not None:
            authorize_staff(claims, "platform.manage")

    @router.post(
        "/platform/staff", response_model=StaffResponse, status_code=status.HTTP_201_CREATED
    )
    def create_staff(payload: StaffRequest, request: Request) -> StaffResponse:
        require_platform_admin(request)
        try:
            staff = application.create_staff(payload.employee_code, payload.department)
        except DuplicateStaffError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"code": "STAFF_ALREADY_EXISTS", "message": str(exc)},
            ) from exc
        return StaffResponse(
            id=staff.id,
            employee_code=staff.employee_code,
            department=staff.department,
            status=staff.status.value,
        )

    @router.post("/platform/staff/{staff_id}/permissions", status_code=status.HTTP_204_NO_CONTENT)
    def grant_permission(staff_id: str, payload: PermissionRequest, request: Request) -> None:
        require_platform_admin(request)
        try:
            application.grant_permission(staff_id, payload.permission)
        except StaffNotFoundError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "STAFF_NOT_FOUND", "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_PERMISSION", "message": str(exc)},
            ) from exc

    @router.post("/platform/staff/{staff_id}/data-scopes", status_code=status.HTTP_204_NO_CONTENT)
    def grant_data_scope(staff_id: str, payload: DataScopeRequest, request: Request) -> None:
        require_platform_admin(request)
        try:
            application.grant_data_scope(staff_id, payload.scope_type, payload.scope_value)
        except StaffNotFoundError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "STAFF_NOT_FOUND", "message": str(exc)},
            ) from exc

        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_DATA_SCOPE", "message": str(exc)},
            ) from exc

    @router.post("/platform/staff/{staff_id}/status", response_model=StaffResponse)
    def change_staff_status(
        staff_id: str, payload: StaffStatusRequest, request: Request
    ) -> StaffResponse:
        require_platform_admin(request)
        try:
            result = application.change_staff_status(staff_id, payload.status)
        except StaffNotFoundError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "STAFF_NOT_FOUND", "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        if result.status is not StaffStatus.ACTIVE and on_staff_inactive is not None:
            on_staff_inactive(result.id)
        return StaffResponse(
            id=result.id,
            employee_code=result.employee_code,
            department=result.department,
            status=result.status.value,
        )

    @router.post("/platform/access/check", status_code=status.HTTP_204_NO_CONTENT)
    def check_access(payload: AccessRequest, request: Request) -> None:
        require_platform_admin(request)
        try:
            application.require_access(
                payload.staff_id,
                payload.permission,
                payload.scope_type,
                payload.scope_value,
            )
        except StaffNotFoundError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "STAFF_NOT_FOUND", "message": str(exc)},
            ) from exc
        except AccessDeniedError as exc:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={"code": "PERMISSION_DENIED", "message": str(exc)},
            ) from exc

    return router
