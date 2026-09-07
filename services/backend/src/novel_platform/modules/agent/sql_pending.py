"""Durable PendingAction storage for SQL deployments."""

import json
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from novel_platform.modules.agent.application import PendingAction


class SqlPendingActionStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        metadata = sa.MetaData()
        self._actions: Any = sa.Table("agent_pending_actions", metadata, autoload_with=engine)

    def save(self, action: PendingAction) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                self._actions.insert().values(
                    id=action.id,
                    actor_id=action.actor_id,
                    session_id=action.session_id,
                    tool_name=action.tool_name,
                    arguments_hash=action.arguments_hash,
                    arguments_snapshot=json.dumps(
                        action.arguments_snapshot, ensure_ascii=False, sort_keys=True
                    ),
                    risk_level=action.risk_level,
                    impact_summary=action.impact_summary,
                    created_at=action.created_at,
                    expires_at=action.expires_at,
                    status=action.status,
                    confirmed_at=action.confirmed_at,
                    executed_at=action.executed_at,
                )
            )

    def get(self, action_id: str) -> PendingAction | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(sa.select(self._actions).where(self._actions.c.id == action_id))
                .mappings()
                .one_or_none()
            )
        return self._from_row(row) if row is not None else None

    def update(self, action: PendingAction) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                self._actions.update()
                .where(self._actions.c.id == action.id)
                .values(
                    status=action.status,
                    confirmed_at=action.confirmed_at,
                    executed_at=action.executed_at,
                )
            )

    @staticmethod
    def _from_row(row: Any) -> PendingAction:
        def timestamp(value: Any) -> datetime:
            if not isinstance(value, datetime):
                raise TypeError("pending action timestamp is invalid")
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

        return PendingAction(
            id=str(row["id"]),
            actor_id=str(row["actor_id"]),
            session_id=str(row["session_id"]),
            tool_name=str(row["tool_name"]),
            arguments_hash=str(row["arguments_hash"]),
            arguments_snapshot=dict(json.loads(str(row["arguments_snapshot"]))),
            risk_level=str(row["risk_level"]),
            impact_summary=str(row["impact_summary"]),
            created_at=timestamp(row["created_at"]),
            expires_at=timestamp(row["expires_at"]),
            status=str(row["status"]),
            confirmed_at=timestamp(row["confirmed_at"]) if row["confirmed_at"] else None,
            executed_at=timestamp(row["executed_at"]) if row["executed_at"] else None,
        )


__all__ = ["SqlPendingActionStore"]
