from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
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
    # The richer policy fields are server-owned metadata.  Callables are supplied
    # by application code when registering a tool and never accepted from HTTP.
    required_permission: str | None = None
    risk_level: str = "LOW"
    confirmation_policy: str = "NONE"
    idempotency_policy: str = "NONE"
    audit_policy: str = "REQUIRED"
    scope_resolver: Any | None = Field(default=None, exclude=True, repr=False)
    result_validator: Any | None = Field(default=None, exclude=True, repr=False)

    @property
    def effective_permission(self) -> str:
        return self.required_permission or self.permission


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
    pending_action_id: str | None = Field(default=None, min_length=1, max_length=128)
    confirmation_token: str | None = Field(default=None, min_length=1, max_length=256)


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
    pending_action_id: str | None = None
    normalized_intent: str | None = None
    resource_scope: tuple[tuple[str, str], ...] = ()
    error: str | None = None
    duration_ms: int | None = None


class PendingActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    actor_id: str
    session_id: str
    tool_name: str
    arguments_hash: str
    arguments_snapshot: dict[str, Any]
    risk_level: str
    impact_summary: str
    created_at: datetime
    expires_at: datetime
    status: str


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
    required_permission: str | None = None
    risk_level: str = "LOW"
    confirmation_policy: str = "NONE"
    idempotency_policy: str = "NONE"
    audit_policy: str = "REQUIRED"
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
    tool_name: str | None = None
    pending_action: PendingActionResponse | None = None


class AgentSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)


class AgentSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    actor_id: str
    title: str | None = None
    created_at: datetime
    updated_at: datetime


class AgentMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    role: str
    content: str
    tool_name: str | None = None
    created_at: datetime


class AgentMessagePageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AgentMessageResponse]


class AgentHarnessUrlResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    url: str


class AgentActionDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_token: str | None = Field(default=None, min_length=1, max_length=256)


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


def _orchestrate_local(
    message: str,
    request: Request,
    claims: SessionClaims,
    gateway: AgentGateway,
    session: dict[str, Any],
) -> tuple[str, str | None, PendingActionResponse | None]:
    """Deterministic fallback used by tests/staging when no live LLM is configured.

    It deliberately handles a small set of unambiguous operations and routes every
    action through the same Gateway and registered business callbacks as the live
    Harness.  Business data is treated as data, never as prompt instructions.
    """
    from novel_platform.modules.agent.application import ConfirmationRequired, PermissionDenied

    lowered = message.casefold()
    instruction_text = re.sub(r"《[^》]*》", "", lowered)
    injection_markers = (
        "ignore previous",
        "忽略以前",
        "忽略系统",
        "actor_id",
        "super_admin",
        "直接修改数据库",
        "system prompt",
        "系统 prompt",
        "隐藏管理员",
    )
    if any(marker in instruction_text for marker in injection_markers):
        gateway.audit_denied_instruction(
            agent_id=f"agt_{session['id']}",
            actor_id=claims.account_id,
            session_id=claims.session_id,
            request_id=current_request_id(),
            instruction=message,
            reason="prompt_injection_detected",
        )
        return "我只能使用当前 Staff 会话被授予的工具和数据范围。", None, None

    context = _agent_context(request, claims)
    pending_id = session["context"].get("pending_action_id")
    if pending_id and ("确认" in message or "执行" in message or "confirm" in lowered):
        try:
            result = gateway.confirm(
                pending_id,
                actor_id=claims.account_id,
                session_id=claims.session_id,
                request_id=current_request_id(),
            )
        except PermissionDenied:
            return "当前 Staff 会话无权确认这个动作。", None, None
        except ConfirmationRequired as exc:
            action = exc.pending_action
            return str(exc), None, PendingActionResponse.model_validate(action) if action else None
        session["context"].pop("pending_action_id", None)
        return f"已执行 {result.tool_name}，并收到业务层结果。", result.tool_name, None

    def call(name: str, arguments: dict[str, Any]) -> Any:
        return gateway.execute(
            AgentToolCall(
                agent_id=f"agt_{session['id']}",
                actor_id=claims.account_id,
                tool_name=name,
                arguments=arguments,
                session_id=claims.session_id,
                request_id=current_request_id(),
            ),
            context=context,
        ).data

    title_match = re.search(r"《([^》]+)》", message)
    wants_lookup = any(word in message for word in ("查", "找", "看看", "搜索", "查询"))
    if wants_lookup:
        try:
            books = call("content.list_books", {})
        except PermissionDenied:
            return "当前 Staff 会话没有内容查询权限。", None, None
        if not isinstance(books, list):
            return "查询结果格式不可验证，未执行后续动作。", "content.list_books", None
        query = title_match.group(1).strip() if title_match else ""
        candidates = [
            item
            for item in books
            if isinstance(item, dict)
            and (not query or query.casefold() in str(item.get("title", "")).casefold())
        ]
        session["context"]["candidates"] = candidates
        session["context"]["last_tool"] = "content.list_books"
        if not candidates:
            return "没有找到匹配的作品。", "content.list_books", None
        lines = [f"找到 {len(candidates)} 本："]
        lines.extend(
            f"{index}. {item.get('title', '')}（{item.get('id', '')}）"
            for index, item in enumerate(candidates, 1)
        )
        return "\n".join(lines), "content.list_books", None

    candidates = session["context"].get("candidates", [])
    selected: dict[str, Any] | None = None
    ordinal = re.search(r"第\s*(\d+)\s*本", message)
    if ordinal and isinstance(candidates, list):
        index = int(ordinal.group(1)) - 1
        if 0 <= index < len(candidates) and isinstance(candidates[index], dict):
            selected = candidates[index]
    if (
        selected is None
        and isinstance(candidates, list)
        and len(candidates) == 1
        and any(word in message for word in ("它", "这个", "该书"))
    ):
        selected = candidates[0]
    if selected is None and any(word in message for word in ("退回", "审核", "通过", "拒绝")):
        return "请先明确作品编号或从候选列表中选择目标。", None, None

    if selected is not None and any(word in message for word in ("退回", "审核", "通过", "拒绝")):
        try:
            pending = call("review.list_pending", {})
        except PermissionDenied:
            return "当前 Staff 会话没有审核队列权限。", None, None
        submission = next(
            (
                item
                for item in pending
                if isinstance(item, dict) and item.get("book_id") == selected.get("id")
            ),
            None,
        )
        if submission is None:
            return "目标作品当前没有处于待审核状态的提交。", "review.list_pending", None
        decision = (
            "RETURN_FOR_CHANGES"
            if "退回" in message
            else ("REJECT" if "拒绝" in message else "APPROVE")
        )
        try:
            result = call(
                "review.decide", {"submission_id": str(submission["id"]), "decision": decision}
            )
        except ConfirmationRequired as exc:
            action = exc.pending_action
            if action is not None:
                session["context"]["pending_action_id"] = action.id
            return (
                "这是需要确认的审核动作。",
                "review.decide",
                PendingActionResponse.model_validate(action) if action else None,
            )
        except PermissionDenied:
            return "当前 Staff 会话无权处理这个审核任务。", "review.decide", None
        return f"已通过业务审核服务提交 {decision}，结果已验证。", "review.decide", None

    return "我可以查询作品或处理明确的审核任务，请给出作品编号或使用《书名》。", None, None


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
            action = exc.pending_action
            detail: Any = str(exc)
            if action is not None:
                detail = {
                    "code": "AGENT_CONFIRMATION_REQUIRED",
                    "message": str(exc),
                    "pending_action": PendingActionResponse.model_validate(action).model_dump(
                        mode="json"
                    ),
                }
            raise HTTPException(status.HTTP_409_CONFLICT, detail=detail) from exc
        except WriteToolRejected as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return router


def build_agent_action_router(
    gateway: AgentGateway,
    *,
    auth_required: bool = False,
    authorize_staff: Callable[[SessionClaims, str], None] | None = None,
) -> APIRouter:
    """Confirm or cancel a server-created action, bound to this Staff session."""
    router = APIRouter(prefix="/admin/api/v1/agent", tags=["agent-actions"])

    def require_action_staff(request: Request) -> SessionClaims:
        claims = require_staff_session(request)
        if auth_required:
            require_staff_authorization(request, authorize_staff, "agent.execute")
        return claims

    @router.post("/actions/{pending_action_id}/confirm", response_model=AgentToolResult)
    def confirm_action(
        pending_action_id: str,
        payload: AgentActionDecisionRequest,
        request: Request,
    ) -> AgentToolResult:
        from novel_platform.modules.agent.application import ConfirmationRequired, PermissionDenied

        claims = require_action_staff(request)
        try:
            return gateway.confirm(
                pending_action_id,
                actor_id=claims.account_id,
                session_id=claims.session_id,
                confirmation_token=payload.confirmation_token,
                request_id=current_request_id(),
            )
        except PermissionDenied as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        except ConfirmationRequired as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.post("/actions/{pending_action_id}/cancel", response_model=PendingActionResponse)
    def cancel_action(pending_action_id: str, request: Request) -> PendingActionResponse:
        from novel_platform.modules.agent.application import PermissionDenied

        claims = require_action_staff(request)
        try:
            action = gateway.cancel(
                pending_action_id,
                actor_id=claims.account_id,
                session_id=claims.session_id,
            )
        except PermissionDenied as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return PendingActionResponse.model_validate(action)

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
    sessions: dict[str, dict[str, Any]] = {}

    def require_runtime_staff(request: Request) -> SessionClaims:
        claims = require_staff_session(request)
        if auth_required:
            require_staff_authorization(request, authorize_staff, "agent.execute")
        return claims

    def session_for(session_id: str, actor_id: str) -> dict[str, Any]:
        session = sessions.get(session_id)
        if session is None:
            now = datetime.now(UTC)
            session = {
                "id": session_id,
                "actor_id": actor_id,
                "title": None,
                "created_at": now,
                "updated_at": now,
                "messages": [],
                "context": {},
            }
            sessions[session_id] = session
        elif session["actor_id"] != actor_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="agent session belongs to another staff"
            )
        return session

    def session_response(session: dict[str, Any]) -> AgentSessionResponse:
        return AgentSessionResponse(
            id=session["id"],
            actor_id=session["actor_id"],
            title=session["title"],
            created_at=session["created_at"],
            updated_at=session["updated_at"],
        )

    def append_message(
        session: dict[str, Any], role: str, content: str, tool_name: str | None = None
    ) -> None:
        session["messages"].append(
            AgentMessageResponse(
                id=f"MSG_{uuid4().hex}",
                session_id=session["id"],
                role=role,
                content=content,
                tool_name=tool_name,
                created_at=datetime.now(UTC),
            )
        )
        session["updated_at"] = datetime.now(UTC)

    @router.post("/sessions", response_model=AgentSessionResponse)
    def create_session(
        payload: AgentSessionCreateRequest, request: Request
    ) -> AgentSessionResponse:
        claims = require_runtime_staff(request)
        session = session_for(f"agt_{uuid4().hex}", claims.account_id)
        session["title"] = (
            payload.title.strip() if payload.title and payload.title.strip() else None
        )
        return session_response(session)

    @router.get("/sessions", response_model=list[AgentSessionResponse])
    def list_sessions(request: Request) -> list[AgentSessionResponse]:
        claims = require_runtime_staff(request)
        return [
            session_response(item)
            for item in sessions.values()
            if item["actor_id"] == claims.account_id
        ]

    @router.get("/sessions/{session_id}", response_model=AgentSessionResponse)
    def get_session(session_id: str, request: Request) -> AgentSessionResponse:
        claims = require_runtime_staff(request)
        return session_response(session_for(session_id, claims.account_id))

    @router.get("/sessions/{session_id}/messages", response_model=AgentMessagePageResponse)
    def get_messages(session_id: str, request: Request) -> AgentMessagePageResponse:
        claims = require_runtime_staff(request)
        session = session_for(session_id, claims.account_id)
        return AgentMessagePageResponse(items=list(session["messages"]))

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
        session = session_for(session_id, claims.account_id)
        append_message(session, "user", payload.message)
        token = getattr(request.state, "session_token", "")
        prompt = (
            "You are the operations assistant inside the Admin Console. "
            "Use only the listed MCP tools. Never access a database, invent permissions, "
            "or reveal secrets. A tool denial is authoritative.\n"
            f"Current staff actor: {claims.account_id}.\n\nUser request:\n{payload.message}"
        )
        tool_name: str | None = None
        pending_action: PendingActionResponse | None = None
        try:
            if getattr(runner, "runtime_mode", "").lower() in {"fake", "test", "deterministic"}:
                response, tool_name, pending_action = _orchestrate_local(
                    payload.message, request, claims, gateway, session
                )
                result = type(
                    "Result", (), {"final_response": response, "finish_reason": "completed"}
                )()
            else:
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
        response = str(getattr(result, "final_response", ""))
        append_message(session, "assistant", response, tool_name)
        return AgentChatResponse(
            session_id=session_id,
            response=response,
            finish_reason=getattr(result, "finish_reason", None),
            tool_name=tool_name,
            pending_action=pending_action,
        )

    @router.post("/messages", response_model=AgentChatResponse)
    def messages(payload: AgentChatRequest, request: Request) -> AgentChatResponse:
        """Explicit message resource alias for clients that do not use /chat."""
        return chat(payload, request)

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
                detail: Any = str(exc)
                if isinstance(exc, ConfirmationRequired) and exc.pending_action is not None:
                    detail = {
                        "code": "AGENT_CONFIRMATION_REQUIRED",
                        "message": str(exc),
                        "pending_action": PendingActionResponse.model_validate(
                            exc.pending_action
                        ).model_dump(mode="json"),
                    }
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32004, "message": detail},
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
