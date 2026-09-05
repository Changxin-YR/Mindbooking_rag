"""Durable append-only Agent audit sink."""

import json
from datetime import UTC
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from novel_platform.modules.agent.api import AgentAudit


class SqlAgentAuditSink:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        metadata = sa.MetaData()
        self._events: Any = sa.Table("agent_audit_events", metadata, autoload_with=engine)
        self._extended = all(
            name in self._events.c
            for name in (
                "session_id",
                "arguments_json",
                "result_summary",
                "ip",
                "device_id",
                "confirmed",
                "risk_level",
            )
        )

    def append(self, audit: AgentAudit) -> None:
        with self.engine.begin() as connection:
            values: dict[str, object] = {
                "id": audit.id,
                "agent_id": audit.agent_id,
                "actor_id": audit.actor_id,
                "tool_name": audit.tool_name,
                "permission": audit.permission,
                "outcome": audit.outcome,
                "reason": audit.reason,
                "occurred_at": audit.occurred_at,
            }
            if self._extended:
                values.update(
                    session_id=audit.session_id,
                    arguments_json=json.dumps(audit.arguments, ensure_ascii=False, sort_keys=True),
                    result_summary=audit.result_summary,
                    ip=audit.ip,
                    device_id=audit.device_id,
                    confirmed=audit.confirmed,
                    risk_level=audit.risk_level,
                )
            connection.execute(self._events.insert().values(**values))

    def reload(self) -> tuple[AgentAudit, ...]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(self._events).order_by(self._events.c.occurred_at, self._events.c.id)
            ).mappings()
            result = []
            for row in rows:
                occurred_at = row["occurred_at"]
                if occurred_at.tzinfo is None:
                    occurred_at = occurred_at.replace(tzinfo=UTC)
                result.append(
                    AgentAudit(
                        id=str(row["id"]),
                        agent_id=str(row["agent_id"]),
                        actor_id=str(row["actor_id"]),
                        tool_name=str(row["tool_name"]),
                        permission=str(row["permission"]),
                        outcome=str(row["outcome"]),
                        reason=str(row["reason"]) if row["reason"] is not None else None,
                        occurred_at=occurred_at,
                        session_id=str(row["session_id"])
                        if row.get("session_id") is not None
                        else None,
                        arguments=(
                            dict(json.loads(str(row["arguments_json"])))
                            if row.get("arguments_json") is not None
                            else {}
                        ),
                        result_summary=(
                            str(row["result_summary"])
                            if row.get("result_summary") is not None
                            else None
                        ),
                        ip=str(row["ip"]) if row.get("ip") is not None else None,
                        device_id=(
                            str(row["device_id"]) if row.get("device_id") is not None else None
                        ),
                        confirmed=bool(row.get("confirmed", False)),
                        risk_level=str(row.get("risk_level", "LOW")),
                    )
                )
            return tuple(result)


__all__ = ["SqlAgentAuditSink"]
