from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel_platform.core.auth import SessionSigner
from novel_platform.modules.agent.api import build_agent_runtime_router
from novel_platform.modules.agent.application import AgentGateway
from novel_platform.modules.agent.sql_session import SqlAgentSessionStore


def _engine(tmp_path) -> sa.Engine:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'agent-sessions.db'}")
    metadata = sa.MetaData()
    sessions = sa.Table(
        "agent_sessions",
        metadata,
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("model_provider", sa.String(128), nullable=False),
        sa.Column("context_version", sa.Integer, nullable=False),
        sa.Column("context_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "agent_messages",
        metadata,
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("session_id", sa.String(128), sa.ForeignKey(sessions.c.id), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("tool_name", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    return engine


def test_sql_agent_session_store_survives_store_restart_and_scopes_actor(tmp_path) -> None:
    engine = _engine(tmp_path)
    first = SqlAgentSessionStore(engine)
    session = first.create("agt-1", "staff-1", "Review queue", model_provider="fake")
    session["context"] = {"candidates": [{"id": "book-1"}]}
    session["updated_at"] = datetime.now(UTC)
    first.save(session)
    first.append_message("agt-1", "staff-1", "user", "查一下作品")
    first.append_message("agt-1", "staff-1", "assistant", "找到 1 本", "content.list_books")

    restarted = SqlAgentSessionStore(engine)
    loaded = restarted.get("agt-1", "staff-1")
    assert loaded is not None
    assert loaded["context"] == {"candidates": [{"id": "book-1"}]}
    assert [item["role"] for item in loaded["messages"]] == ["user", "assistant"]
    assert restarted.list("staff-1")[0]["id"] == "agt-1"
    assert restarted.list("staff-2") == ()
    with pytest.raises(PermissionError):
        restarted.get("agt-1", "staff-2")


def test_sql_agent_session_store_rejects_message_from_other_actor(tmp_path) -> None:
    engine = _engine(tmp_path)
    store = SqlAgentSessionStore(engine)
    store.create("agt-1", "staff-1")
    with pytest.raises(PermissionError):
        store.append_message("agt-1", "staff-2", "user", "越权")


def test_sql_agent_session_store_redacts_secrets_in_messages(tmp_path) -> None:
    engine = _engine(tmp_path)
    store = SqlAgentSessionStore(engine)
    store.create("agt-1", "staff-1")
    store.append_message(
        "agt-1", "staff-1", "user", "Bearer abc.def password=secret cookie=tracking"
    )

    restored = store.get("agt-1", "staff-1")
    assert restored is not None
    content = restored["messages"][0]["content"]
    assert "abc.def" not in content
    assert "secret" not in content
    assert "tracking" not in content


def test_sql_agent_session_store_rejects_stale_context_update(tmp_path) -> None:
    engine = _engine(tmp_path)
    store = SqlAgentSessionStore(engine)
    store.create("agt-1", "staff-1")
    first = store.get("agt-1", "staff-1")
    second = store.get("agt-1", "staff-1")
    assert first is not None and second is not None
    first["context"] = {"selected": "book-1"}
    store.save(first)
    second["context"] = {"selected": "book-2"}
    with pytest.raises(RuntimeError, match="AGENT_SESSION_VERSION_CONFLICT"):
        store.save(second)


def test_runtime_router_reads_session_and_messages_from_second_store_instance(tmp_path) -> None:
    engine = _engine(tmp_path)
    signer = SessionSigner("agent-session-test", ttl_seconds=3600)
    token = signer.issue_staff("staff-1")

    def app_for(store: SqlAgentSessionStore) -> TestClient:
        app = FastAPI()
        app.state.session_signer = signer
        app.include_router(
            build_agent_runtime_router(
                AgentGateway(type("Permissions", (), {"has_permission": lambda *_: True})()),
                SimpleNamespace(
                    run=lambda **_: SimpleNamespace(
                        final_response="已完成", finish_reason="completed"
                    )
                ),
                auth_required=True,
                authorize_staff=lambda *_: None,
                session_store=store,
            )
        )
        return TestClient(app)

    first = app_for(SqlAgentSessionStore(engine))
    headers = {"Authorization": f"Bearer {token}"}
    created = first.post("/admin/api/v1/agent/sessions", headers=headers, json={})
    assert created.status_code == 200
    session_id = created.json()["id"]
    chat = first.post(
        "/admin/api/v1/agent/messages",
        headers=headers,
        json={"session_id": session_id, "message": "查询"},
    )
    assert chat.status_code == 200

    second = app_for(SqlAgentSessionStore(engine))
    messages = second.get(f"/admin/api/v1/agent/sessions/{session_id}/messages", headers=headers)
    assert messages.status_code == 200
    assert [item["role"] for item in messages.json()["items"]] == ["user", "assistant"]
