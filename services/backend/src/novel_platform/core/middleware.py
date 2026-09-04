import re
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from novel_platform.core.request_context import request_id_context, trace_id_context

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _get_or_create(value: str | None, prefix: str) -> str:
    return value if value and _SAFE_ID.fullmatch(value) else f"{prefix}_{uuid4().hex}"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = _get_or_create(request.headers.get("x-request-id"), "REQ")
        trace_id = _get_or_create(request.headers.get("x-trace-id"), "TRACE")
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        request_token = request_id_context.set(request_id)
        trace_token = trace_id_context.set(trace_id)
        try:
            response = await call_next(request)
        finally:
            request_id_context.reset(request_token)
            trace_id_context.reset(trace_token)
        response.headers["x-request-id"] = request_id
        response.headers["x-trace-id"] = trace_id
        return response
