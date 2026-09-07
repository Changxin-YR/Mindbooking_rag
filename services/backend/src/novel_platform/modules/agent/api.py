from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import require_staff_authorization, require_staff_session
from novel_platform.core.request_context import current_request_id

if TYPE_CHECKING:
    from novel_platform.modules.agent.application import AgentAuditSink, AgentGateway

logger = logging.getLogger(__name__)


class ToolResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    permission: str = Field(min_length=1)
    read_only: bool = True
    high_risk: bool = False
    requires_confirmation: bool = False
    input_schema: dict[str, Any] = Field(default_factory=dict)


class AgentToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmation: bool = False
    session_id: str | None = None
    ip: str | None = None
    device_id: str | None = None
    request_id: str | None = None


class AgentToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    data: Any


class AgentAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    agent_id: str
    actor_id: str
    tool_name: str
    permission: str
    outcome: str
    reason: str | None = None
    occurred_at: datetime
    session_id: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = None
    ip: str | None = None
    device_id: str | None = None
    request_id: str | None = None
    confirmed: bool = False
    risk_level: str = "LOW"


class AgentAuditResponse(BaseModel):
    """Explicit admin DTO; arguments are withheld unless separately authorized."""

    model_config = ConfigDict(extra="forbid")

    id: str
    agent_id: str
    actor_id: str
    tool_name: str
    permission: str
    outcome: str
    reason: str | None = None
    occurred_at: datetime
    session_id: str | None = None
    arguments: dict[str, Any] | None = None
    result_summary: str | None = None
    ip: str | None = None
    device_id: str | None = None
    request_id: str | None = None
    confirmed: bool = False
    risk_level: str = "LOW"


class AgentAuditPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AgentAuditResponse]
    total: int
    page: int
    page_size: int


class AgentResourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    permission: str
    read_only: bool
    high_risk: bool
    requires_confirmation: bool
    input_schema: dict[str, Any] = Field(default_factory=dict)


class AgentResourcePageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AgentResourceResponse]


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=20_000)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    confirmation: bool = False
    confirmation_token: str | None = Field(default=None, min_length=1, max_length=256)


class AgentChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    response: str
    finish_reason: str | None = None


class AgentHarnessUrlResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    url: str


def _agent_context(request: Request, claims: SessionClaims) -> Any:
    from novel_platform.modules.agent.application import AgentExecutionContext

    checker = getattr(request.app.state, "agent_gateway", None)
    checker = getattr(checker, "permission_checker", None)
    permissions = (
        tuple(checker.repository.permissions_for(claims.account_id))
        if checker is not None and hasattr(checker, "repository")
        else ()
    )
    scopes = (
        tuple(checker.repository.scopes_for(claims.account_id))
        if checker is not None and hasattr(checker, "repository")
        else ()
    )
    return AgentExecutionContext(
        actor_id=claims.account_id,
        session_id=claims.session_id,
        request_id=current_request_id(),
        permissions=permissions,
        data_scopes=scopes,
    )


def build_agent_gateway_router(
    gateway: AgentGateway,
    *,
    auth_required: bool = False,
    authorize_staff: Callable[[SessionClaims, str], None] | None = None,
) -> APIRouter:
    """Expose the registered Agent Gateway without allowing actor spoofing."""

    router = APIRouter(prefix="/admin/api/v1/agent", tags=["agent"])

    def require_agent_staff(request: Request) -> SessionClaims:
        claims = require_staff_session(request)
        if auth_required:
            require_staff_authorization(request, authorize_staff, "agent.execute")
        return claims

    @router.get("/resources", response_model=AgentResourcePageResponse)
    def list_resources(request: Request) -> AgentResourcePageResponse:
        claims = require_agent_staff(request)
        resources = gateway.resources_for(claims.account_id)
        return AgentResourcePageResponse(
            items=[
                AgentResourceResponse.model_validate(item, from_attributes=True)
                for item in resources
            ]
        )

    @router.post("/tools/execute", response_model=AgentToolResult)
    def execute_tool(payload: AgentToolCall, request: Request) -> AgentToolResult:
        from novel_platform.modules.agent.application import (
            ConfirmationRequired,
            PermissionDenied,
            ToolNotFound,
            WriteToolRejected,
        )

        claims = require_agent_staff(request)
        if payload.actor_id != claims.account_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "AGENT_ACTOR_MISMATCH", "message": "actor must match session"},
            )
        try:
            checker = getattr(gateway, "permission_checker", None)
            permissions = (
                tuple(checker.permissions_for(claims.account_id))
                if checker is not None and callable(getattr(checker, "permissions_for", None))
                else ()
            )
            scopes = (
                tuple(checker.scopes_for(claims.account_id))
                if checker is not None and callable(getattr(checker, "scopes_for", None))
                else ()
            )
            from novel_platform.modules.agent.application import AgentExecutionContext

            context = AgentExecutionContext(
                actor_id=claims.account_id,
                session_id=payload.session_id or claims.session_id,
                request_id=payload.request_id or current_request_id(),
                permissions=permissions,
                data_scopes=scopes,
            )
            payload = payload.model_copy(
                update={"session_id": context.session_id, "request_id": context.request_id}
            )
            return gateway.execute(payload, context=context)
        except ToolNotFound as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except PermissionDenied as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        except ConfirmationRequired as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except WriteToolRejected as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return router


def build_agent_runtime_router(
    gateway: AgentGateway,
    runner: Any,
    *,
    auth_required: bool = False,
    authorize_staff: Callable[[SessionClaims, str], None] | None = None,
) -> APIRouter:
    """Expose text chat and the MCP transport used by the real Harness runtime."""
    router = APIRouter(prefix="/admin/api/v1/agent", tags=["agent-runtime"])

    def require_runtime_staff(request: Request) -> SessionClaims:
        claims = require_staff_session(request)
        if auth_required:
            require_staff_authorization(request, authorize_staff, "agent.execute")
        return claims

    @router.get("/harness-url", response_model=AgentHarnessUrlResponse)
    def harness_url(request: Request) -> AgentHarnessUrlResponse:
        from novel_platform.modules.agent.runtime import HarnessRuntimeError

        claims = require_runtime_staff(request)
        token = getattr(request.state, "session_token", "")
        session_id = claims.session_id
        try:
            url = runner.web_url(
                actor_id=claims.account_id,
                session_id=session_id,
                access_token=token,
            )
        except HarnessRuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": str(exc), "message": "DeepSeek Harness 工作台暂时不可用"},
            ) from exc
        return AgentHarnessUrlResponse(session_id=session_id, url=url)

    @router.post("/chat", response_model=AgentChatResponse)
    def chat(payload: AgentChatRequest, request: Request) -> AgentChatResponse:
        claims = require_runtime_staff(request)
        session_id = payload.session_id or f"agt_{uuid4().hex}"
        token = getattr(request.state, "session_token", "")
        prompt = (
            "You are the operations assistant inside the Admin Console. "
            "Use only the listed MCP tools. Never access a database, invent permissions, "
            "or reveal secrets. A tool denial is authoritative.\n"
            f"Current staff actor: {claims.account_id}.\n\nUser request:\n{payload.message}"
        )
        try:
            result = runner.run(
                actor_id=claims.account_id,
                session_id=session_id,
                access_token=token,
                prompt=prompt,
            )
        except Exception as exc:
            logger = getattr(request.app.state, "logger", None)
            if logger is not None:
                logger.exception("agent runtime failed", exc_info=exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "AGENT_RUNTIME_UNAVAILABLE", "message": "智能助手暂时不可用"},
            ) from exc
        return AgentChatResponse(
            session_id=session_id,
            response=str(getattr(result, "final_response", "")),
            finish_reason=getattr(result, "finish_reason", None),
        )

    @router.post("/mcp")
    async def mcp_transport(request: Request) -> Any:
        from novel_platform.modules.agent.application import (
            ConfirmationRequired,
            PermissionDenied,
            ToolNotFound,
            WriteToolRejected,
        )

        claims = require_runtime_staff(request)
        body = await request.json()
        if not isinstance(body, dict):
            return {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "invalid request"},
            }
        request_id = body.get("id")
        method = body.get("method")
        raw_params = body.get("params")
        params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "novel-platform-agent-tools", "version": "1"},
                },
            }
        if method == "notifications/initialized":
            return {"jsonrpc": "2.0", "method": "notifications/initialized"}
        if method == "tools/list":
            resources = gateway.resources_for(claims.account_id)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": resource.name,
                            "description": resource.description,
                            "inputSchema": resource.input_schema
                            or {"type": "object", "additionalProperties": False},
                        }
                        for resource in resources
                    ]
                },
            }
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments")
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32602, "message": "invalid tool arguments"},
                }
            session_id = request.headers.get("X-Agent-Session") or claims.session_id
            agent_id = request.headers.get("X-Agent-Id") or f"agt_{session_id}"
            try:
                result = gateway.execute(
                    AgentToolCall(
                        agent_id=agent_id,
                        actor_id=claims.account_id,
                        tool_name=name,
                        arguments=arguments,
                        session_id=session_id,
                        ip=request.client.host if request.client else None,
                        request_id=current_request_id(),
                    ),
                    context=_agent_context(request, claims),
                )
            except PermissionDenied:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32003, "message": "permission denied"},
                }
            except (ToolNotFound, ConfirmationRequired, WriteToolRejected) as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32004, "message": str(exc)},
                }
            except Exception:  # noqa: BLE001 - hide adapter internals from model
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": "tool execution failed"},
                }
            import json

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result.data, ensure_ascii=False, default=str),
                        }
                    ]
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "method not found"},
        }

    return router


def build_agent_admin_router(
    audit_sink: AgentAuditSink,
    *,
    auth_required: bool = False,
    authorize_staff: Callable[[SessionClaims, str], None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/admin/api/v1", tags=["agent-admin"])

    @router.get(
        "/agent/audits",
        response_model=AgentAuditPageResponse,
        operation_id="admin_list_agent_audits",
    )
    def list_agent_audits(
        request: Request,
        actor: str | None = Query(default=None, min_length=1),
        actor_id: str | None = Query(default=None, min_length=1),
        tool: str | None = Query(default=None, min_length=1),
        tool_name: str | None = Query(default=None, min_length=1),
        outcome: str | None = Query(default=None, min_length=1),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=100),
        include_arguments: bool = Query(default=False),
    ) -> AgentAuditPageResponse:
        if auth_required or include_arguments:
            require_staff_authorization(request, authorize_staff, "agent.audit.read")
        if include_arguments:
            require_staff_authorization(request, authorize_staff, "agent.audit.sensitive")
        query = getattr(audit_sink, "query", None)
        if callable(query):
            audits, total = query(
                actor_id=actor or actor_id,
                tool_name=tool or tool_name,
                outcome=outcome,
                page=page,
                page_size=page_size,
            )
        else:
            records = tuple(audit_sink.reload())
            filtered = tuple(
                item
                for item in records
                if (actor or actor_id) is None or item.actor_id == (actor or actor_id)
                if (tool or tool_name) is None or item.tool_name == (tool or tool_name)
                if outcome is None or item.outcome == outcome
            )
            total = len(filtered)
            start = (page - 1) * page_size
            audits = filtered[start : start + page_size]
        return AgentAuditPageResponse(
            items=[
                AgentAuditResponse(
                    id=item.id,
                    agent_id=item.agent_id,
                    actor_id=item.actor_id,
                    tool_name=item.tool_name,
                    permission=item.permission,
                    outcome=item.outcome,
                    reason=item.reason,
                    occurred_at=item.occurred_at,
                    session_id=item.session_id,
                    arguments=item.arguments if include_arguments else None,
                    result_summary=item.result_summary,
                    ip=item.ip,
                    device_id=item.device_id,
                    request_id=item.request_id,
                    confirmed=item.confirmed,
                    risk_level=item.risk_level,
                )
                for item in audits
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    return router
