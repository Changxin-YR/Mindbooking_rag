"""Durable SQL storage for Agent sessions and immutable messages."""

import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine

_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_FIELD_RE = re.compile(
    r'(?i)("?(?:access_token|authorization|cookie|password|secret)"?\s*[:=]\s*["\']?)([^\s,"\'}]+)'
)


def _sanitize_content(content: str) -> str:
    content = _BEARER_RE.sub("Bearer [REDACTED]", content)
    return _SECRET_FIELD_RE.sub(r"\1[REDACTED]", content)


class SqlAgentSessionStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        metadata = sa.MetaData()
        self._sessions: Any = sa.Table("agent_sessions", metadata, autoload_with=engine)
        self._messages: Any = sa.Table("agent_messages", metadata, autoload_with=engine)

    def create(
        self,
        session_id: str,
        actor_id: str,
        title: str | None = None,
        model_provider: str = "unknown",
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._sessions).where(self._sessions.c.id == session_id)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                connection.execute(
                    self._sessions.insert().values(
                        id=session_id,
                        actor_id=actor_id,
                        title=title,
                        status="ACTIVE",
                        model_provider=model_provider,
                        context_version=0,
                        context_json="{}",
                        created_at=now,
                        updated_at=now,
                    )
                )
                return self._session_dict(
                    {
                        "id": session_id,
                        "actor_id": actor_id,
                        "title": title,
                        "status": "ACTIVE",
                        "model_provider": model_provider,
                        "context_version": 0,
                        "context_json": "{}",
                        "created_at": now,
                        "updated_at": now,
                    },
                    (),
                )
            if str(row["actor_id"]) != actor_id:
                raise PermissionError("agent session belongs to another staff")
            return self._load_from_connection(connection, session_id)

    def get(self, session_id: str, actor_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._sessions).where(self._sessions.c.id == session_id)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            if str(row["actor_id"]) != actor_id:
                raise PermissionError("agent session belongs to another staff")
            messages = connection.execute(
                sa.select(self._messages)
                .where(self._messages.c.session_id == session_id)
                .order_by(self._messages.c.created_at, self._messages.c.id)
            ).mappings()
            return self._session_dict(row, tuple(messages))

    def list(self, actor_id: str) -> tuple[dict[str, Any], ...]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(self._sessions)
                .where(self._sessions.c.actor_id == actor_id)
                .order_by(self._sessions.c.updated_at.desc(), self._sessions.c.id)
            ).mappings()
            return tuple(
                self._session_dict(row, self._messages_for(connection, str(row["id"])))
                for row in rows
            )

    def save(self, session: dict[str, Any]) -> None:
        context = _sanitize(dict(session.get("context", {})))
        version = int(session.get("context_version", 0))
        with self.engine.begin() as connection:
            result = connection.execute(
                self._sessions.update()
                .where(
                    self._sessions.c.id == session["id"],
                    self._sessions.c.context_version == version,
                )
                .values(
                    title=session.get("title"),
                    context_json=json.dumps(context, ensure_ascii=False),
                    context_version=version + 1,
                    updated_at=session["updated_at"],
                )
            )
            if result.rowcount != 1:
                raise RuntimeError("AGENT_SESSION_VERSION_CONFLICT")
        session["context"] = context
        session["context_version"] = version + 1

    def append_message(
        self,
        session_id: str,
        actor_id: str,
        role: str,
        content: str,
        tool_name: str | None = None,
    ) -> dict[str, Any]:
        message = {
            "id": f"MSG_{uuid4().hex}",
            "session_id": session_id,
            "role": role,
            "content": _sanitize_content(content),
            "tool_name": tool_name,
            "created_at": datetime.now(UTC),
        }
        with self.engine.begin() as connection:
            owner = connection.execute(
                sa.select(self._sessions.c.actor_id).where(self._sessions.c.id == session_id)
            ).scalar_one_or_none()
            if owner is None:
                raise KeyError("agent session not found")
            if str(owner) != actor_id:
                raise PermissionError("agent session belongs to another staff")
            connection.execute(self._messages.insert().values(**message))
            connection.execute(
                self._sessions.update()
                .where(self._sessions.c.id == session_id)
                .values(updated_at=message["created_at"])
            )
        return message

    def _load_from_connection(self, connection: Any, session_id: str) -> dict[str, Any]:
        row = (
            connection.execute(sa.select(self._sessions).where(self._sessions.c.id == session_id))
            .mappings()
            .one()
        )
        return self._session_dict(row, self._messages_for(connection, session_id))

    def _messages_for(self, connection: Any, session_id: str) -> tuple[Any, ...]:
        return tuple(
            connection.execute(
                sa.select(self._messages)
                .where(self._messages.c.session_id == session_id)
                .order_by(self._messages.c.created_at, self._messages.c.id)
            ).mappings()
        )

    @staticmethod
    def _datetime(value: Any) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError("agent session timestamp is invalid")
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    def _session_dict(self, row: Any, messages: tuple[Any, ...]) -> dict[str, Any]:
        context_raw = row.get("context_json") or "{}"
        context = json.loads(str(context_raw))
        if not isinstance(context, dict):
            context = {}
        return {
            "id": str(row["id"]),
            "actor_id": str(row["actor_id"]),
            "title": str(row["title"]) if row.get("title") is not None else None,
            "status": str(row.get("status") or "ACTIVE"),
            "model_provider": str(row.get("model_provider") or "unknown"),
            "context_version": int(row.get("context_version") or 0),
            "created_at": self._datetime(row["created_at"]),
            "updated_at": self._datetime(row["updated_at"]),
            "messages": [
                {
                    "id": str(item["id"]),
                    "session_id": str(item["session_id"]),
                    "role": str(item["role"]),
                    "content": str(item["content"]),
                    "tool_name": str(item["tool_name"]) if item.get("tool_name") else None,
                    "created_at": self._datetime(item["created_at"]),
                }
                for item in messages
            ],
            "context": context,
        }


__all__ = ["SqlAgentSessionStore"]


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if str(key).lower() not in {"access_token", "authorization", "cookie", "password"}
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
