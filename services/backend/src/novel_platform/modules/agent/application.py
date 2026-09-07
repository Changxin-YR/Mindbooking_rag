import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import uuid4

from novel_platform.modules.agent.api import (
    AgentAudit,
    AgentToolCall,
    AgentToolResult,
    ToolResource,
)


class AgentPermissionChecker(Protocol):
    def has_permission(self, actor_id: str, permission: str) -> bool: ...


class AgentAuditSink(Protocol):
    def append(self, audit: AgentAudit) -> None: ...

    def reload(self) -> tuple[AgentAudit, ...]: ...

    def query(
        self,
        *,
        actor_id: str | None = None,
        tool_name: str | None = None,
        outcome: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[tuple[AgentAudit, ...], int]: ...


class AgentAuditRecorder(Protocol):
    def record(self, audit: AgentAudit) -> None: ...


class AgentExecutionContext:
    """Server-owned identity and authorization context passed to adapters."""

    def __init__(
        self,
        *,
        actor_id: str,
        session_id: str | None,
        request_id: str | None,
        permissions: tuple[str, ...] = (),
        data_scopes: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self.actor_id = actor_id
        self.session_id = session_id
        self.request_id = request_id
        self.permissions = permissions
        self.data_scopes = data_scopes


AgentCallback = Callable[..., Any]


class AgentError(Exception):
    pass


class ToolNotFound(AgentError):
    pass


class PermissionDenied(AgentError):
    pass


class ConfirmationRequired(AgentError):
    pass


class WriteToolRejected(AgentError):
    pass


class InMemoryAgentAuditLog:
    def __init__(self) -> None:
        self._records: list[AgentAudit] = []

    @property
    def records(self) -> tuple[AgentAudit, ...]:
        return tuple(self._records)

    def append(self, audit: AgentAudit) -> None:
        self._records.append(audit)

    def record(self, audit: AgentAudit) -> None:
        self.append(audit)

    def reload(self) -> tuple[AgentAudit, ...]:
        return self.records

    def query(
        self,
        *,
        actor_id: str | None = None,
        tool_name: str | None = None,
        outcome: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[tuple[AgentAudit, ...], int]:
        if page < 1 or page_size < 1:
            raise ValueError("page and page_size must be positive")
        records = tuple(
            audit
            for audit in self._records
            if (actor_id is None or audit.actor_id == actor_id)
            and (tool_name is None or audit.tool_name == tool_name)
            and (outcome is None or audit.outcome == outcome)
        )
        start = (page - 1) * page_size
        return records[start : start + page_size], len(records)


class AgentGateway:
    def __init__(
        self,
        permission_checker: AgentPermissionChecker,
        audit_recorder: AgentAuditRecorder | None = None,
        *,
        audit_sink: AgentAuditSink | None = None,
    ) -> None:
        if audit_recorder is not None and audit_sink is not None:
            raise ValueError("provide either audit_recorder or audit_sink")
        self._permission_checker = permission_checker
        self.audit_recorder = audit_sink or audit_recorder or InMemoryAgentAuditLog()
        self._tools: dict[str, tuple[ToolResource, AgentCallback]] = {}

    @property
    def permission_checker(self) -> AgentPermissionChecker:
        return self._permission_checker

    def register(self, resource: ToolResource, callback: AgentCallback) -> None:
        if resource.name in self._tools:
            raise ValueError("tool resource already registered")
        self._tools[resource.name] = (resource, callback)

    def resources(self) -> tuple[ToolResource, ...]:
        return tuple(resource for resource, _ in self._tools.values())

    def resources_for(self, actor_id: str) -> tuple[ToolResource, ...]:
        return tuple(
            resource
            for resource, _ in self._tools.values()
            if self._permission_checker.has_permission(actor_id, resource.permission)
        )

    def execute(
        self,
        call: AgentToolCall,
        *,
        context: AgentExecutionContext | None = None,
    ) -> AgentToolResult:
        registered = self._tools.get(call.tool_name)
        if registered is None:
            self._audit(call, "", "DENIED", "tool_not_found")
            raise ToolNotFound("tool resource is not registered")

        resource, callback = registered
        if not self._permission_checker.has_permission(call.actor_id, resource.permission):
            self._audit(
                call,
                resource.permission,
                "DENIED",
                "permission_denied",
                risk_level="HIGH" if resource.high_risk else "LOW",
            )
            raise PermissionDenied("agent actor lacks tool permission")

        if not resource.read_only and (resource.high_risk or resource.requires_confirmation):
            self._audit(
                call,
                resource.permission,
                "REJECTED",
                "confirmation_required",
                risk_level="HIGH" if resource.high_risk else "LOW",
            )
            raise ConfirmationRequired("a verified human confirmation is required for this write")

        try:
            data = _invoke_callback(callback, call.arguments, context)
        except Exception:
            self._audit(
                call,
                resource.permission,
                "FAILED",
                "callback_failed",
                risk_level="HIGH" if resource.high_risk else "LOW",
            )
            raise

        self._audit(
            call,
            resource.permission,
            "SUCCESS",
            None,
            result_summary="tool_result_returned",
            risk_level="HIGH" if resource.high_risk else "LOW",
        )
        return AgentToolResult(tool_name=resource.name, data=data)

    def _audit(
        self,
        call: AgentToolCall,
        permission: str,
        outcome: str,
        reason: str | None,
        *,
        result_summary: str | None = None,
        risk_level: str = "LOW",
    ) -> None:
        audit = AgentAudit(
            id=f"AGT_{uuid4().hex}",
            agent_id=call.agent_id,
            actor_id=call.actor_id,
            tool_name=call.tool_name,
            permission=permission,
            outcome=outcome,
            reason=reason,
            occurred_at=datetime.now(UTC),
            session_id=call.session_id,
            arguments=dict(call.arguments),
            result_summary=result_summary,
            ip=call.ip,
            device_id=call.device_id,
            request_id=getattr(call, "request_id", None),
            confirmed=call.confirmation,
            risk_level=risk_level,
        )
        append = getattr(self.audit_recorder, "append", None)
        if callable(append):
            cast(Callable[[AgentAudit], None], append)(audit)
        else:
            cast(AgentAuditRecorder, self.audit_recorder).record(audit)


def _invoke_callback(
    callback: AgentCallback,
    arguments: dict[str, Any],
    context: AgentExecutionContext | None,
) -> Any:
    """Keep one-argument callbacks compatible while enabling context-aware adapters."""
    if context is not None:
        try:
            if len(inspect.signature(callback).parameters) >= 2:
                return callback(arguments, context)
        except TypeError, ValueError:
            pass
    return callback(arguments)


__all__ = [
    "AgentAuditRecorder",
    "AgentAuditSink",
    "AgentError",
    "AgentExecutionContext",
    "AgentGateway",
    "AgentPermissionChecker",
    "ConfirmationRequired",
    "InMemoryAgentAuditLog",
    "PermissionDenied",
    "ToolNotFound",
    "WriteToolRejected",
]
