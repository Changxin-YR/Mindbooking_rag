import pytest

from novel_platform.modules.agent.api import AgentToolCall, ToolResource
from novel_platform.modules.agent.application import (
    AgentGateway,
    InMemoryAgentAuditLog,
    PermissionDenied,
)


class Permissions:
    def __init__(self, allowed: set[str]) -> None:
        self.allowed = allowed

    def has_permission(self, actor_id: str, permission: str) -> bool:
        return permission in self.allowed


def test_agent_audit_sink_can_reload_success_denial_and_callback_failure() -> None:
    sink = InMemoryAgentAuditLog()
    gateway = AgentGateway(Permissions({"content.read"}), audit_sink=sink)
    gateway.register(
        ToolResource(
            name="content.read",
            description="Read content",
            permission="content.read",
        ),
        lambda arguments: {"ok": True},
    )
    gateway.register(
        ToolResource(
            name="content.denied",
            description="Read restricted content",
            permission="content.restricted",
        ),
        lambda arguments: {"ok": False},
    )
    gateway.register(
        ToolResource(
            name="content.fail",
            description="Read content and fail",
            permission="content.read",
        ),
        lambda arguments: (_ for _ in ()).throw(RuntimeError("callback failed")),
    )

    gateway.execute(AgentToolCall(agent_id="agent-1", actor_id="staff-1", tool_name="content.read"))
    with pytest.raises(PermissionDenied):
        gateway.execute(
            AgentToolCall(
                agent_id="agent-1",
                actor_id="staff-2",
                tool_name="content.denied",
            )
        )
    with pytest.raises(RuntimeError, match="callback failed"):
        gateway.execute(
            AgentToolCall(agent_id="agent-1", actor_id="staff-1", tool_name="content.fail")
        )

    reloaded = sink.reload()
    assert [(audit.outcome, audit.reason) for audit in reloaded] == [
        ("SUCCESS", None),
        ("DENIED", "permission_denied"),
        ("FAILED", "callback_failed"),
    ]
    assert sink.records == reloaded
