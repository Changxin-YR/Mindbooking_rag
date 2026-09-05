import pytest

from novel_platform.modules.agent.api import AgentToolCall, ToolResource
from novel_platform.modules.agent.application import (
    AgentGateway,
    ConfirmationRequired,
    InMemoryAgentAuditLog,
    PermissionDenied,
    WriteToolRejected,
)


class Permissions:
    def __init__(self, allowed: set[str]) -> None:
        self.allowed = allowed

    def has_permission(self, actor_id: str, permission: str) -> bool:
        return permission in self.allowed


def test_read_only_tool_calls_business_service_callback() -> None:
    audit = InMemoryAgentAuditLog()
    gateway = AgentGateway(Permissions({"content.read"}), audit)
    calls: list[dict[str, object]] = []
    gateway.register(
        ToolResource(
            name="content.get_book",
            description="Read a book through ContentService",
            permission="content.read",
        ),
        lambda arguments: calls.append(arguments) or {"id": "book-1", "title": "Book"},
    )

    result = gateway.execute(
        AgentToolCall(
            agent_id="agent-1",
            actor_id="staff-1",
            tool_name="content.get_book",
            arguments={"book_id": "book-1"},
            session_id="session-1",
            ip="127.0.0.1",
            device_id="device-1",
        )
    )

    assert result.data == {"id": "book-1", "title": "Book"}
    assert calls == [{"book_id": "book-1"}]
    assert audit.records[-1].outcome == "SUCCESS"
    assert audit.records[-1].session_id == "session-1"
    assert audit.records[-1].arguments == {"book_id": "book-1"}
    assert audit.records[-1].ip == "127.0.0.1"
    assert audit.records[-1].device_id == "device-1"
    assert audit.records[-1].confirmed is False
    assert audit.records[-1].risk_level == "LOW"


def test_tool_requires_permission_and_audits_denial() -> None:
    audit = InMemoryAgentAuditLog()
    gateway = AgentGateway(Permissions(set()), audit)
    gateway.register(
        ToolResource(
            name="wallet.read",
            description="Read wallet facts through WalletService",
            permission="wallet.read",
        ),
        lambda arguments: {"balance": 100},
    )

    with pytest.raises(PermissionDenied):
        gateway.execute(
            AgentToolCall(
                agent_id="agent-1",
                actor_id="staff-1",
                tool_name="wallet.read",
            )
        )

    assert audit.records[-1].outcome == "DENIED"
    assert audit.records[-1].reason == "permission_denied"


def test_high_risk_write_requires_confirmation_and_never_calls_business_write() -> None:
    audit = InMemoryAgentAuditLog()
    gateway = AgentGateway(Permissions({"wallet.adjust"}), audit)
    calls: list[dict[str, object]] = []
    gateway.register(
        ToolResource(
            name="wallet.adjust",
            description="High-risk wallet adjustment proposal",
            permission="wallet.adjust",
            read_only=False,
            high_risk=True,
        ),
        lambda arguments: calls.append(arguments),
    )

    with pytest.raises(ConfirmationRequired):
        gateway.execute(
            AgentToolCall(
                agent_id="agent-1",
                actor_id="staff-1",
                tool_name="wallet.adjust",
            )
        )

    assert calls == []
    assert audit.records[-1].reason == "confirmation_required"

    with pytest.raises(WriteToolRejected):
        gateway.execute(
            AgentToolCall(
                agent_id="agent-1",
                actor_id="staff-1",
                tool_name="wallet.adjust",
                confirmation=True,
            )
        )

    assert calls == []
    assert audit.records[-1].reason == "write_tools_not_supported"
