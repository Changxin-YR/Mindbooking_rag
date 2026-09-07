import pytest
import sqlalchemy as sa

from novel_platform.modules.agent.api import AgentToolCall, ToolResource
from novel_platform.modules.agent.application import (
    AgentGateway,
    InMemoryAgentAuditLog,
    PermissionDenied,
)
from novel_platform.modules.agent.sql_session import SqlAgentSessionStore


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


def test_sql_agent_session_store_restores_context_and_messages_after_new_store() -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "agent_sessions",
        metadata,
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("model_provider", sa.String(128), nullable=False),
        sa.Column("context_version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context_json", sa.Text, nullable=False),
    )
    sa.Table(
        "agent_messages",
        metadata,
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("tool_name", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    store = SqlAgentSessionStore(engine)
    session = store.create("agt-1", "staff-1", title="审核", model_provider="fake")
    session["context"] = {"candidates": [{"id": "book-1"}], "last_tool": "content.list_books"}
    store.append_message("agt-1", "staff-1", "user", "查书")
    store.save(session)

    restored = SqlAgentSessionStore(engine).get("agt-1", "staff-1")

    assert restored is not None
    assert restored["context"]["candidates"][0]["id"] == "book-1"
    assert restored["messages"][0]["content"] == "查书"
    assert "access_token" not in restored["context"]
