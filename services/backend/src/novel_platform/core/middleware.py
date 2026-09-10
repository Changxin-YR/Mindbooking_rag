import re
from typing import cast
from uuid import uuid4

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from novel_platform.core.request_context import request_id_context, trace_id_context
from novel_platform.modules.platform.staff_auth import StaffAuthService

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


class PrivateApiMiddleware(BaseHTTPMiddleware):
    """Require account sessions for writer and staff sessions for admin APIs."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)
        is_admin = request.url.path.startswith("/admin/api/")
        is_staff_login = (
            request.method == "POST" and request.url.path == "/admin/api/v1/auth/staff/sessions"
        )
        is_staff_logout = (
            request.method == "DELETE"
            and request.url.path == "/admin/api/v1/auth/staff/sessions/current"
        )
        if request.url.path.startswith("/writer/api/") or (is_admin and not is_staff_login):
            authorization = request.headers.get("Authorization", "")
            scheme, _, token = authorization.partition(" ")
            token = token.strip()
            if is_admin:
                staff_auth = cast(
                    StaffAuthService | None, getattr(request.app.state, "staff_auth", None)
                )
                claims = (
                    staff_auth.verify(token)
                    if scheme.lower() == "bearer" and isinstance(staff_auth, StaffAuthService)
                    else None
                )
                if claims is not None:
                    request.state.session_token = token
                    if not is_staff_logout and isinstance(staff_auth, StaffAuthService):
                        try:
                            permission = _admin_permission(request.url.path, request.method)
                            scope = _admin_scope(request.url.path)
                            if scope is None and _admin_collection_is_scoped(request.url.path):
                                staff_auth.authorize_permission(claims, permission)
                            elif scope is None:
                                staff_auth.authorize(claims, permission)
                            else:
                                staff_auth.authorize(claims, permission, *scope)
                            authorized_permissions: set[str] = getattr(
                                request.state, "staff_authorized_permissions", set()
                            )
                            authorized_permissions.add(permission)
                            request.state.staff_authorized_permissions = authorized_permissions
                        except HTTPException as exc:
                            return JSONResponse(
                                status_code=exc.status_code,
                                content={"error": exc.detail},
                            )
            else:
                signer = getattr(request.app.state, "session_signer", None)
                claims = signer.verify(token) if scheme.lower() == "bearer" and signer else None
                if claims is not None and claims.subject_type != "ACCOUNT":
                    claims = None
                if claims is not None:
                    request.state.session_token = token
            if claims is None:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "code": "AUTHENTICATION_REQUIRED",
                            "message": "Bearer session required",
                        }
                    },
                    headers={"WWW-Authenticate": "Bearer"},
                )
            request.state.session = claims
        return await call_next(request)


def _admin_permission(path: str, method: str) -> str:
    path = path.rstrip("/") or "/"
    if path in {
        "/admin/api/v1/author-tasks",
        "/admin/api/v1/campaigns",
        "/admin/api/v1/learning",
        "/admin/api/v1/author-alerts",
    }:
        return "operation.write"
    if path == "/admin/api/v1/review-rules":
        return "governance.write" if method != "GET" else "review.read"
    if path == "/admin/api/v1/reviewer-quality":
        return "review.decide"
    if path == "/admin/api/v1/user-360":
        return "admin.access"
    if path == "/admin/api/v1/agent/audits":
        return "agent.audit.read"
    if path.startswith("/admin/api/v1/support/tickets/") and path.endswith("/csat"):
        return "support.write"
    if path == "/admin/api/v1/support/dashboard":
        return "support.read"
    if "/chapters/" in path and path.endswith("/commercial-policy"):
        return "commerce.write"
    if "/finance/withdrawals/" in path and path.endswith("/risk-approve"):
        return "risk.write"
    if "/finance/withdrawals/" in path and path.endswith("/finance-approve"):
        return "finance.write"
    if "/finance/contracts/" in path and path.endswith(("/approve", "/activate")):
        return "approval.write"
    if "/auth/staff/credentials" in path:
        return "platform.manage"
    if "/reviews" in path:
        return "review.decide" if method != "GET" else "review.read"
    if "/approvals" in path:
        return "approval.write"
    if "/finance" in path:
        return "finance.write" if method != "GET" else "finance.read"
    if "/risk" in path:
        return "risk.write" if method != "GET" else "risk.read"
    if "/operation" in path:
        return "operation.write" if method != "GET" else "operation.read"
    if "/copyright" in path or "/legal" in path:
        return "legal.write"
    if "/invoices" in path:
        return "finance.write"
    if path.startswith("/admin/api/v1/agent/audits"):
        return "agent.audit.read"
    if path.startswith("/admin/api/v1/agent"):
        return "agent.execute"
    if "/support" in path:
        return "support.write" if method != "GET" else "support.read"
    if "/platform" in path:
        return "platform.manage"
    if "/parameters" in path or "/emergencies" in path:
        return "governance.write"
    if "/reconciliation" in path:
        return "governance.write" if method != "GET" else "governance.read"
    if "/membership" in path or "/gifts" in path:
        return "governance.write"
    return "admin.access"


def _admin_scope(path: str) -> tuple[str, str] | None:
    """Extract a resource id for exact server-side ASSIGNED scope checks."""
    path = path.rstrip("/") or "/"
    patterns = (
        r"/reviews/([^/]+)/",
        r"/approvals/([^/]+)/",
        r"/finance/(?:contracts|revenue|settlements)/([^/]+)",
        r"/risk/(?:signals|watchlist)/([^/]+)",
        r"/support/tickets/([^/]+)",
        r"/copyright/(?:dossiers|complaints)/([^/]+)",
        r"/legal/(?:cases|holds)/([^/]+)",
        r"/platform/staff/([^/]+)",
        r"/parameters/([^/]+)",
        r"/reconciliation/batches/([^/]+)",
        r"/emergencies/([^/]+)",
        r"/invoices/([^/]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, path)
        if match is not None:
            return ("ASSIGNED", match.group(1))
    return None


def _admin_collection_is_scoped(path: str) -> bool:
    return path in {
        "/admin/api/v1/reviews",
        "/admin/api/v1/agent/chat",
        "/admin/api/v1/agent/messages",
        "/admin/api/v1/agent/harness-url",
        "/admin/api/v1/agent/mcp",
        "/admin/api/v1/agent/resources",
        "/admin/api/v1/agent/tools/execute",
    } or path.startswith(("/admin/api/v1/agent/sessions", "/admin/api/v1/agent/actions/"))
