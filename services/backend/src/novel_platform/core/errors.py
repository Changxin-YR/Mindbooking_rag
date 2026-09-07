from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from novel_platform.core.request_context import current_request_id, current_trace_id


class ErrorAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    request_id: str | None = None
    trace_id: str | None = None
    action: ErrorAction | None = None
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail


def _response(
    status_code: int,
    code: str,
    message: str,
    action: dict[str, str] | None = None,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            request_id=current_request_id(),
            trace_id=current_trace_id(),
            action=ErrorAction(**action) if action else None,
            details=details,
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        return _response(500, "INTERNAL_SERVER_ERROR", "Internal server error")
    if exc.status_code == 404:
        return _response(404, "RESOURCE_NOT_FOUND", "Resource not found")
    detail: Any = exc.detail
    if isinstance(detail, dict):
        details = {
            str(key): value
            for key, value in detail.items()
            if key not in {"code", "message", "action"}
        }
        return _response(
            exc.status_code,
            detail.get("code", "HTTP_ERROR"),
            detail.get("message", "Request failed"),
            detail.get("action"),
            details or None,
        )
    return _response(exc.status_code, "HTTP_ERROR", str(detail))


async def validation_exception_handler(_: Request, __: Exception) -> JSONResponse:
    return _response(422, "VALIDATION_ERROR", "Request validation failed")


async def unhandled_exception_handler(_: Request, __: Exception) -> JSONResponse:
    return _response(500, "INTERNAL_SERVER_ERROR", "Internal server error")
