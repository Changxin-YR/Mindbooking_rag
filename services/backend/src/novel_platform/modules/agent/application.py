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


class AgentAuditRecorder(Protocol):
    def record(self, audit: AgentAudit) -> None: ...


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
        self._tools: dict[str, tuple[ToolResource, Callable[[dict[str, Any]], Any]]] = {}

    def register(self, resource: ToolResource, callback: Callable[[dict[str, Any]], Any]) -> None:
        if resource.name in self._tools:
            raise ValueError("tool resource already registered")
        self._tools[resource.name] = (resource, callback)

    def resources(self) -> tuple[ToolResource, ...]:
        return tuple(resource for resource, _ in self._tools.values())

    def execute(self, call: AgentToolCall) -> AgentToolResult:
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

        if not resource.read_only:
            if (resource.high_risk or resource.requires_confirmation) and not call.confirmation:
                self._audit(
                    call,
                    resource.permission,
                    "REJECTED",
                    "confirmation_required",
                    risk_level="HIGH" if resource.high_risk else "LOW",
                )
                raise ConfirmationRequired("confirmation is required for high-risk writes")
            self._audit(
                call,
                resource.permission,
                "REJECTED",
                "write_tools_not_supported",
                risk_level="HIGH" if resource.high_risk else "LOW",
            )
            raise WriteToolRejected("Agent cannot execute write tools")

        try:
            data = callback(call.arguments)
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
            confirmed=call.confirmation,
            risk_level=risk_level,
        )
        append = getattr(self.audit_recorder, "append", None)
        if callable(append):
            cast(Callable[[AgentAudit], None], append)(audit)
        else:
            cast(AgentAuditRecorder, self.audit_recorder).record(audit)


__all__ = [
    "AgentAuditRecorder",
    "AgentAuditSink",
    "AgentError",
    "AgentGateway",
    "AgentPermissionChecker",
    "ConfirmationRequired",
    "InMemoryAgentAuditLog",
    "PermissionDenied",
    "ToolNotFound",
    "WriteToolRejected",
]
