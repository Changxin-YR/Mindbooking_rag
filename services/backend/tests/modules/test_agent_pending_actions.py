from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from novel_platform.modules.agent.api import AgentToolCall, ToolResource
from novel_platform.modules.agent.application import (
    AgentExecutionContext,
    AgentGateway,
    ConfirmationRequired,
    InMemoryAgentAuditLog,
    PendingAction,
    PermissionDenied,
)
from novel_platform.modules.agent.runtime import FakeAgentModelAdapter, HarnessSessionManager
from novel_platform.modules.agent.sql_pending import SqlPendingActionStore


class Permissions:
    def has_permission(self, actor_id: str, permission: str) -> bool:
        return actor_id == "staff-1" and permission == "review.decide"


def test_pending_action_binds_args_actor_session_and_executes_once(tmp_path) -> None:
    calls: list[dict[str, object]] = []
    gateway = AgentGateway(Permissions(), InMemoryAgentAuditLog())
    gateway.register(
        ToolResource(
            name="review.decide",
            description="Review",
            permission="review.decide",
            read_only=False,
            high_risk=True,
            risk_level="HIGH",
        ),
        lambda args: calls.append(args) or {"ok": True},
    )
    call = AgentToolCall(
        agent_id="agent-1",
        actor_id="staff-1",
        tool_name="review.decide",
        arguments={"submission_id": "sub-1", "decision": "APPROVE"},
        session_id="sess-1",
    )
    with pytest.raises(ConfirmationRequired) as raised:
        gateway.execute(
            call,
            context=AgentExecutionContext(
                actor_id="staff-1", session_id="sess-1", request_id="req-1"
            ),
        )
    action = raised.value.pending_action
    assert action is not None
    assert action.actor_id == "staff-1"
    assert action.session_id == "sess-1"
    token = f"{action.id}:{action.arguments_hash}"
    result = gateway.confirm(
        action.id, actor_id="staff-1", session_id="sess-1", confirmation_token=token
    )
    assert result.data == {"ok": True}
    assert calls == [call.arguments]
    with pytest.raises(ConfirmationRequired):
        gateway.confirm(
            action.id, actor_id="staff-1", session_id="sess-1", confirmation_token=token
        )

    with pytest.raises(PermissionDenied):
        gateway.confirm(
            action.id, actor_id="staff-2", session_id="sess-1", confirmation_token=token
        )


def test_pending_action_concurrent_confirmation_executes_business_callback_once() -> None:
    calls: list[dict[str, object]] = []
    gateway = AgentGateway(Permissions(), InMemoryAgentAuditLog())
    gateway.register(
        ToolResource(
            name="review.decide",
            description="Review",
            permission="review.decide",
            read_only=False,
            high_risk=True,
        ),
        lambda args: calls.append(args) or {"ok": True},
    )
    with pytest.raises(ConfirmationRequired) as raised:
        gateway.execute(
            AgentToolCall(
                agent_id="agent-1",
                actor_id="staff-1",
                tool_name="review.decide",
                arguments={"submission_id": "sub-2"},
                session_id="sess-2",
            ),
            context=AgentExecutionContext(
                actor_id="staff-1", session_id="sess-2", request_id="req-2"
            ),
        )
    action = raised.value.pending_action
    assert action is not None
    token = f"{action.id}:{action.arguments_hash}"

    def confirm() -> str:
        try:
            gateway.confirm(
                action.id, actor_id="staff-1", session_id="sess-2", confirmation_token=token
            )
        except ConfirmationRequired:
            return "conflict"
        return "success"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _item: confirm(), range(2)))

    assert sorted(outcomes) == ["conflict", "success"]
    assert calls == [{"submission_id": "sub-2"}]


def test_gateway_rejects_context_actor_spoof() -> None:
    gateway = AgentGateway(Permissions(), InMemoryAgentAuditLog())
    gateway.register(
        ToolResource(name="review.read", description="Read", permission="review.decide"),
        lambda _: {},
    )
    with pytest.raises(PermissionDenied):
        gateway.execute(
            AgentToolCall(agent_id="a", actor_id="staff-1", tool_name="review.read"),
            context=AgentExecutionContext(actor_id="staff-2", session_id="s", request_id="r"),
        )


def test_fake_model_adapter_and_manager_are_deterministic(tmp_path) -> None:
    adapter = FakeAgentModelAdapter("ok")
    assert adapter.run("hello", session_id="s").final_response == "ok"
    manager = HarnessSessionManager(
        backend_url="http://localhost",
        dsh_home=str(tmp_path),
        project_root=str(tmp_path),
        provider="fake",
        model="fake",
        runtime_mode="fake",
    )
    assert (
        manager.run(actor_id="staff-1", session_id="s", access_token="t", prompt="x").finish_reason
        == "completed"
    )
    manager.close_all()


def test_sql_pending_action_store_round_trips_and_updates(tmp_path) -> None:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'agent.db'}")
    metadata = sa.MetaData()
    sa.Table(
        "agent_pending_actions",
        metadata,
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("arguments_snapshot", sa.Text, nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("impact_summary", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
    )
    metadata.create_all(engine)
    store = SqlPendingActionStore(engine)
    action = PendingAction(
        id="ACT_sql",
        actor_id="staff-1",
        session_id="session-1",
        tool_name="review.decide",
        arguments_hash="hash",
        arguments_snapshot={"submission_id": "sub-1"},
        risk_level="HIGH",
        impact_summary="Execute review.decide",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    store.save(action)
    loaded = store.get(action.id)
    assert loaded is not None
    assert loaded.arguments_snapshot == action.arguments_snapshot
    loaded.status = "EXECUTED"
    loaded.executed_at = datetime.now(UTC)
    store.update(loaded)
    assert store.get(action.id).status == "EXECUTED"


def test_sql_pending_action_is_claimed_once_across_gateway_instances(tmp_path) -> None:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'agent-claim.db'}")
    metadata = sa.MetaData()
    sa.Table(
        "agent_pending_actions",
        metadata,
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("arguments_snapshot", sa.Text, nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("impact_summary", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
    )
    metadata.create_all(engine)
    calls: list[dict[str, object]] = []

    def gateway() -> AgentGateway:
        result = AgentGateway(
            Permissions(), InMemoryAgentAuditLog(), pending_store=SqlPendingActionStore(engine)
        )
        result.register(
            ToolResource(
                name="review.decide",
                description="Review",
                permission="review.decide",
                read_only=False,
                high_risk=True,
            ),
            lambda args: calls.append(args) or {"ok": True},
        )
        return result

    first = gateway()
    second = gateway()
    with pytest.raises(ConfirmationRequired) as raised:
        first.execute(
            AgentToolCall(
                agent_id="agent-1",
                actor_id="staff-1",
                tool_name="review.decide",
                arguments={"submission_id": "sub-sql"},
                session_id="session-sql",
            )
        )
    action = raised.value.pending_action
    assert action is not None
    token = f"{action.id}:{action.arguments_hash}"

    def confirm(instance: AgentGateway) -> str:
        try:
            instance.confirm(
                action.id,
                actor_id="staff-1",
                session_id="session-sql",
                confirmation_token=token,
            )
        except ConfirmationRequired:
            return "conflict"
        return "success"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(confirm, (first, second)))

    assert sorted(outcomes) == ["conflict", "success"]
    assert calls == [{"submission_id": "sub-sql"}]
