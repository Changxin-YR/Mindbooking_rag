from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.agent.api import AgentAudit
from novel_platform.modules.agent.sql_audit import SqlAgentAuditSink


def test_sql_agent_audit_sink_reloads_append_only_events() -> None:
    metadata = sa.MetaData()
    sa.Table(
        "agent_audit_events",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("permission", sa.String(128), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(255)),
        sa.Column("occurred_at", sa.DateTime, nullable=False),
        sa.Column("session_id", sa.String(64)),
        sa.Column("arguments_json", sa.Text),
        sa.Column("result_summary", sa.String(255)),
        sa.Column("ip", sa.String(64)),
        sa.Column("device_id", sa.String(128)),
        sa.Column("confirmed", sa.Boolean, nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("pending_action_id", sa.String(128)),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    audit = AgentAudit(
        id="AGT-1",
        agent_id="agent-1",
        actor_id="staff-1",
        tool_name="content.read",
        permission="content.read",
        outcome="SUCCESS",
        occurred_at=datetime.now(UTC),
        session_id="session-1",
        arguments={"book_id": "book-1"},
        result_summary="tool_result_returned",
        ip="127.0.0.1",
        device_id="device-1",
        confirmed=True,
        risk_level="HIGH",
        pending_action_id="ACT-1",
    )

    SqlAgentAuditSink(engine).append(audit)

    assert SqlAgentAuditSink(engine).reload() == (audit,)
