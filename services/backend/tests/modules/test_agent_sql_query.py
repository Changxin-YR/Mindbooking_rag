from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from novel_platform.modules.agent.api import AgentAudit
from novel_platform.modules.agent.sql_audit import SqlAgentAuditSink


def test_sql_agent_audit_query_filters_and_paginates() -> None:
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
    )
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    sink = SqlAgentAuditSink(engine)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(3):
        sink.append(
            AgentAudit(
                id=f"evt-{index}",
                agent_id="agent-1",
                actor_id="staff-1",
                tool_name="content.read",
                permission="content.read",
                outcome="SUCCESS",
                occurred_at=base + timedelta(minutes=index),
            )
        )

    audits, total = sink.query(
        actor_id="staff-1",
        tool_name="content.read",
        outcome="SUCCESS",
        page=2,
        page_size=2,
    )

    assert total == 3
    assert [audit.id for audit in audits] == ["evt-2"]
