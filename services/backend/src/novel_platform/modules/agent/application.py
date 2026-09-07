from __future__ import annotations

import hashlib
import inspect
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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


class PendingActionStore(Protocol):
    def get(self, action_id: str) -> PendingAction | None: ...

    def save(self, action: PendingAction) -> None: ...

    def update(self, action: PendingAction) -> None: ...


class AgentSessionStore(Protocol):
    def create(
        self,
        session_id: str,
        actor_id: str,
        title: str | None = None,
        model_provider: str = "unknown",
    ) -> dict[str, Any]: ...

    def get(self, session_id: str, actor_id: str) -> dict[str, Any] | None: ...

    def list(self, actor_id: str) -> tuple[dict[str, Any], ...]: ...

    def save(self, session: dict[str, Any]) -> None: ...

    def append_message(
        self,
        session_id: str,
        actor_id: str,
        role: str,
        content: str,
        tool_name: str | None = None,
    ) -> dict[str, Any]: ...


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
    def __init__(self, message: str, *, pending_action: PendingAction | None = None) -> None:
        super().__init__(message)
        self.pending_action = pending_action


class WriteToolRejected(AgentError):
    pass


@dataclass
class PendingAction:
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
    status: str = "PENDING"
    confirmed_at: datetime | None = None
    executed_at: datetime | None = None


def _arguments_hash(arguments: dict[str, Any]) -> str:
    encoded = json.dumps(
        arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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


class InMemoryAgentSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    def create(
        self,
        session_id: str,
        actor_id: str,
        title: str | None = None,
        model_provider: str = "unknown",
    ) -> dict[str, Any]:
        existing = self._sessions.get(session_id)
        if existing is not None:
            if existing["actor_id"] != actor_id:
                raise PermissionDenied("agent session belongs to another staff")
            return existing
        now = datetime.now(UTC)
        session: dict[str, Any] = {
            "id": session_id,
            "actor_id": actor_id,
            "title": title,
            "status": "ACTIVE",
            "model_provider": model_provider,
            "context_version": 0,
            "created_at": now,
            "updated_at": now,
            "messages": [],
            "context": {},
        }
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str, actor_id: str) -> dict[str, Any] | None:
        session = self._sessions.get(session_id)
        if session is not None and session["actor_id"] != actor_id:
            raise PermissionDenied("agent session belongs to another staff")
        return session

    def list(self, actor_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(item for item in self._sessions.values() if item["actor_id"] == actor_id)

    def save(self, _session: dict[str, Any]) -> None:
        _session["context_version"] = int(_session.get("context_version", 0)) + 1

    def append_message(
        self,
        session_id: str,
        actor_id: str,
        role: str,
        content: str,
        tool_name: str | None = None,
    ) -> dict[str, Any]:
        session = self.get(session_id, actor_id)
        if session is None:
            session = self.create(session_id, actor_id)
        message = {
            "id": f"MSG_{uuid4().hex}",
            "session_id": session_id,
            "role": role,
            "content": content,
            "tool_name": tool_name,
            "created_at": datetime.now(UTC),
        }
        session["messages"].append(message)
        session["updated_at"] = datetime.now(UTC)
        return message


class AgentGateway:
    def __init__(
        self,
        permission_checker: AgentPermissionChecker,
        audit_recorder: AgentAuditRecorder | None = None,
        *,
        audit_sink: AgentAuditSink | None = None,
        pending_store: PendingActionStore | None = None,
    ) -> None:
        if audit_recorder is not None and audit_sink is not None:
            raise ValueError("provide either audit_recorder or audit_sink")
        self._permission_checker = permission_checker
        self.audit_recorder = audit_sink or audit_recorder or InMemoryAgentAuditLog()
        self._tools: dict[str, tuple[ToolResource, AgentCallback]] = {}
        self._pending_store = pending_store
        self._pending: dict[str, PendingAction] = {}
        # ponytail: one gateway lock prevents duplicate confirmation in-process;
        # a SQL conditional claim is the upgrade path for cross-instance execution.
        self._confirm_lock = threading.Lock()

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
            if self._permission_checker.has_permission(actor_id, resource.effective_permission)
        )

    def pending(self, action_id: str) -> PendingAction | None:
        if self._pending_store is not None:
            return self._pending_store.get(action_id)
        return self._pending.get(action_id)

    def audit_denied_instruction(
        self,
        *,
        agent_id: str,
        actor_id: str,
        session_id: str | None,
        request_id: str | None,
        instruction: str,
        reason: str,
    ) -> None:
        self._audit(
            AgentToolCall(
                agent_id=agent_id,
                actor_id=actor_id,
                tool_name="agent.orchestrator",
                arguments={"instruction": instruction[:20_000]},
                session_id=session_id,
                request_id=request_id,
            ),
            "agent.execute",
            "DENIED",
            reason,
            risk_level="HIGH",
        )

    def _save_pending(self, action: PendingAction) -> None:
        if self._pending_store is not None:
            self._pending_store.save(action)
        self._pending[action.id] = action

    def _update_pending(self, action: PendingAction) -> None:
        if self._pending_store is not None:
            self._pending_store.update(action)
        self._pending[action.id] = action

    def cancel(self, action_id: str, *, actor_id: str, session_id: str) -> PendingAction:
        action = self.pending(action_id)
        if action is None or action.actor_id != actor_id or action.session_id != session_id:
            raise PermissionDenied("pending action is not owned by this staff session")
        if action.status != "PENDING":
            return action
        action.status = "CANCELLED"
        self._update_pending(action)
        self._audit(
            AgentToolCall(
                agent_id=f"agt_{session_id}",
                actor_id=actor_id,
                tool_name=action.tool_name,
                arguments=action.arguments_snapshot,
                session_id=session_id,
            ),
            self._tools[action.tool_name][0].effective_permission,
            "CANCELLED",
            "pending_action_cancelled",
            risk_level=action.risk_level,
            pending_action_id=action.id,
        )
        return action

    def confirm(
        self,
        action_id: str,
        *,
        actor_id: str,
        session_id: str,
        confirmation_token: str | None = None,
        request_id: str | None = None,
    ) -> AgentToolResult:
        with self._confirm_lock:
            return self._confirm(
                action_id,
                actor_id=actor_id,
                session_id=session_id,
                confirmation_token=confirmation_token,
                request_id=request_id,
            )

    def _confirm(
        self,
        action_id: str,
        *,
        actor_id: str,
        session_id: str,
        confirmation_token: str | None = None,
        request_id: str | None = None,
    ) -> AgentToolResult:
        action = self.pending(action_id)
        if action is None or action.actor_id != actor_id or action.session_id != session_id:
            raise PermissionDenied("pending action is not owned by this staff session")
        now = datetime.now(UTC)
        if action.status != "PENDING":
            raise ConfirmationRequired(
                "pending action is no longer executable", pending_action=action
            )
        if action.expires_at <= now:
            action.status = "EXPIRED"
            self._update_pending(action)
            raise ConfirmationRequired("pending action has expired", pending_action=action)
        expected = f"{action.id}:{action.arguments_hash}"
        if confirmation_token is not None and confirmation_token != expected:
            raise PermissionDenied("confirmation token does not match pending action")
        resource, callback = self._tools[action.tool_name]
        if not self._permission_checker.has_permission(actor_id, resource.effective_permission):
            self._audit(
                AgentToolCall(
                    agent_id=f"agt_{session_id}",
                    actor_id=actor_id,
                    tool_name=action.tool_name,
                    arguments=action.arguments_snapshot,
                    session_id=session_id,
                    pending_action_id=action.id,
                ),
                resource.effective_permission,
                "DENIED",
                "permission_revoked",
                risk_level=action.risk_level,
                pending_action_id=action.id,
            )
            raise PermissionDenied("agent actor no longer has tool permission")
        call = AgentToolCall(
            agent_id=f"agt_{session_id}",
            actor_id=actor_id,
            tool_name=action.tool_name,
            arguments=dict(action.arguments_snapshot),
            confirmation=True,
            session_id=session_id,
            request_id=request_id,
            pending_action_id=action.id,
            confirmation_token=confirmation_token or expected,
        )
        permission_values = getattr(self._permission_checker, "permissions_for", None)
        scope_values = getattr(self._permission_checker, "scopes_for", None)
        context = AgentExecutionContext(
            actor_id=actor_id,
            session_id=session_id,
            request_id=request_id,
            permissions=tuple(permission_values(actor_id)) if callable(permission_values) else (),
            data_scopes=tuple(scope_values(actor_id)) if callable(scope_values) else (),
        )
        if callable(resource.scope_resolver):
            try:
                in_scope = resource.scope_resolver(call.arguments, context)
            except PermissionDenied:
                in_scope = False
            if in_scope is False:
                self._audit(
                    call,
                    resource.effective_permission,
                    "DENIED",
                    "data_scope_denied",
                    risk_level=action.risk_level,
                    pending_action_id=action.id,
                )
                raise PermissionDenied("agent resource is outside the staff data scope")
        claim = getattr(self._pending_store, "claim", None)
        if callable(claim):
            claimed = claim(action.id, actor_id, session_id, now)
            if claimed is None:
                raise ConfirmationRequired(
                    "pending action is no longer executable", pending_action=self.pending(action.id)
                )
            action = claimed
        else:
            action.status = "EXECUTING"
            action.confirmed_at = now
            self._update_pending(action)
        try:
            data = self._invoke_write(resource, callback, call.arguments, context)
        except Exception:
            action.status = "FAILED"
            self._update_pending(action)
            self._audit(
                call,
                resource.effective_permission,
                "FAILED",
                "callback_failed",
                risk_level=action.risk_level,
                pending_action_id=action.id,
            )
            raise
        action.status = "EXECUTED"
        action.executed_at = datetime.now(UTC)
        self._update_pending(action)
        self._audit(
            call,
            resource.effective_permission,
            "SUCCESS",
            None,
            result_summary="tool_result_verified",
            risk_level=action.risk_level,
            pending_action_id=action.id,
        )
        return AgentToolResult(tool_name=resource.name, data=data)

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
        if context is not None and context.actor_id != call.actor_id:
            self._audit(call, resource.effective_permission, "DENIED", "context_actor_mismatch")
            raise PermissionDenied("agent actor is not the authenticated staff actor")
        if not self._permission_checker.has_permission(
            call.actor_id, resource.effective_permission
        ):
            self._audit(
                call,
                resource.effective_permission,
                "DENIED",
                "permission_denied",
                risk_level="HIGH" if resource.high_risk else "LOW",
            )
            raise PermissionDenied("agent actor lacks tool permission")

        scope_resolver = resource.scope_resolver
        if callable(scope_resolver):
            try:
                scope_ok = scope_resolver(call.arguments, context)
            except PermissionDenied:
                scope_ok = False
            if scope_ok is False:
                self._audit(
                    call,
                    resource.effective_permission,
                    "DENIED",
                    "data_scope_denied",
                    risk_level=resource.risk_level,
                )
                raise PermissionDenied("agent resource is outside the staff data scope")

        if not resource.read_only and (
            resource.high_risk
            or resource.requires_confirmation
            or resource.confirmation_policy != "NONE"
        ):
            action = self._pending_action(call, resource)
            self._audit(
                call,
                resource.effective_permission,
                "PENDING",
                "confirmation_required",
                risk_level=action.risk_level,
                pending_action_id=action.id,
            )
            raise ConfirmationRequired(
                "a verified human confirmation is required for this write", pending_action=action
            )

        try:
            data = self._invoke_write(resource, callback, call.arguments, context)
        except Exception:
            self._audit(
                call,
                resource.effective_permission,
                "FAILED",
                "callback_failed",
                risk_level="HIGH" if resource.high_risk else "LOW",
            )
            raise

        self._audit(
            call,
            resource.effective_permission,
            "SUCCESS",
            None,
            result_summary="tool_result_returned",
            risk_level="HIGH" if resource.high_risk else "LOW",
        )
        return AgentToolResult(tool_name=resource.name, data=data)

    def _pending_action(self, call: AgentToolCall, resource: ToolResource) -> PendingAction:
        # Direct unit callers may omit a session; HTTP/MCP callers always bind one
        # to authenticated Staff claims before reaching this method.
        session_id = call.session_id or f"legacy-{call.actor_id}"
        action = PendingAction(
            id=f"ACT_{uuid4().hex}",
            actor_id=call.actor_id,
            session_id=session_id,
            tool_name=resource.name,
            arguments_hash=_arguments_hash(call.arguments),
            arguments_snapshot=dict(call.arguments),
            risk_level=resource.risk_level
            if resource.risk_level != "LOW"
            else ("HIGH" if resource.high_risk else "MEDIUM"),
            impact_summary=f"Execute {resource.name}",
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        self._save_pending(action)
        return action

    @staticmethod
    def _invoke_write(
        resource: ToolResource,
        callback: AgentCallback,
        arguments: dict[str, Any],
        context: AgentExecutionContext | None,
    ) -> Any:
        data = _invoke_callback(callback, arguments, context)
        validator = resource.result_validator
        if callable(validator) and not bool(validator(data, arguments, context)):
            raise AgentError("tool result verification failed")
        return data

    def _audit(
        self,
        call: AgentToolCall,
        permission: str,
        outcome: str,
        reason: str | None,
        *,
        result_summary: str | None = None,
        risk_level: str = "LOW",
        pending_action_id: str | None = None,
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
            pending_action_id=pending_action_id,
            resource_scope=(),
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
    "AgentSessionStore",
    "ConfirmationRequired",
    "InMemoryAgentAuditLog",
    "InMemoryAgentSessionStore",
    "PendingActionStore",
    "PermissionDenied",
    "ToolNotFound",
    "WriteToolRejected",
]
