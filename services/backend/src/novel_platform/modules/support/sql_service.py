"""SQLAlchemy adapter for support tickets and immutable messages."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from novel_platform.modules.support.application import SupportService
from novel_platform.modules.support.domain import (
    SupportMessage,
    SupportPriority,
    SupportStatus,
    SupportTicket,
)


class SqlSupportService(SupportService):
    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        metadata = sa.MetaData()
        self._tickets: Any = sa.Table("support_tickets", metadata, autoload_with=engine)
        self._messages: Any = sa.Table("support_messages", metadata, autoload_with=engine)

    def open_ticket(
        self, account_id: str, category: str, priority: SupportPriority, description: str = ""
    ) -> SupportTicket:
        ticket = SupportTicket(
            id=f"TKT_{uuid4().hex}",
            account_id=account_id,
            category=category,
            priority=priority,
        )
        with self.engine.begin() as connection:
            connection.execute(
                self._tickets.insert().values(
                    id=ticket.id,
                    account_id=ticket.account_id,
                    category=ticket.category,
                    priority=ticket.priority.value,
                    status=ticket.status.value,
                    created_at=datetime.now(UTC),
                )
            )
            if description:
                connection.execute(
                    self._messages.insert().values(
                        id=f"MSG_{uuid4().hex}",
                        ticket_id=ticket.id,
                        author_type="USER",
                        body=description,
                        created_at=datetime.now(UTC),
                    )
                )
            return self._ticket_from_connection(connection, ticket.id)

    def get_ticket(self, ticket_id: str) -> SupportTicket:
        with self.engine.begin() as connection:
            return self._ticket_from_connection(connection, ticket_id)

    def list_tickets(self, account_id: str) -> list[SupportTicket]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(self._tickets.c.id)
                .where(self._tickets.c.account_id == account_id)
                .order_by(self._tickets.c.created_at, self._tickets.c.id)
            )
            return [self._ticket_from_connection(connection, str(row.id)) for row in rows]

    def resolve(self, ticket_id: str) -> SupportTicket:
        with self.engine.begin() as connection:
            ticket = self._ticket_from_connection(connection, ticket_id, lock=True)
            if ticket.status is SupportStatus.CLOSED:
                raise ValueError("closed ticket cannot be resolved")
            connection.execute(
                self._tickets.update()
                .where(self._tickets.c.id == ticket_id)
                .values(status=SupportStatus.RESOLVED.value)
            )
            return self._ticket_from_connection(connection, ticket_id)

    def reply(self, ticket_id: str, body: str, author: str) -> SupportMessage:
        if author not in {"USER", "STAFF"}:
            raise ValueError("support message author is invalid")
        with self.engine.begin() as connection:
            ticket = self._ticket_from_connection(connection, ticket_id, lock=True)
            message = SupportMessage(
                id=f"MSG_{uuid4().hex}", ticket_id=ticket.id, author=author, body=body
            )
            connection.execute(
                self._messages.insert().values(
                    id=message.id,
                    ticket_id=message.ticket_id,
                    author_type=message.author,
                    body=message.body,
                    created_at=datetime.now(UTC),
                )
            )
            if author == "USER" and ticket.status is SupportStatus.RESOLVED:
                connection.execute(
                    self._tickets.update()
                    .where(self._tickets.c.id == ticket_id)
                    .values(status=SupportStatus.IN_PROGRESS.value)
                )
            return message

    def modify_asset(self, account_id: str, asset_type: str, amount: int) -> None:
        raise PermissionError("support cannot modify assets")

    def _ticket_from_connection(
        self, connection: Connection, ticket_id: str, *, lock: bool = False
    ) -> SupportTicket:
        query = sa.select(self._tickets).where(self._tickets.c.id == ticket_id)
        if lock:
            query = query.with_for_update()
        row = connection.execute(query).mappings().one_or_none()
        if row is None:
            raise KeyError(ticket_id)
        messages = connection.execute(
            sa.select(self._messages)
            .where(self._messages.c.ticket_id == ticket_id)
            .order_by(self._messages.c.created_at, self._messages.c.id)
        ).mappings()
        return SupportTicket(
            id=str(row["id"]),
            account_id=str(row["account_id"]),
            category=str(row["category"]),
            priority=SupportPriority(str(row["priority"])),
            status=SupportStatus(str(row["status"])),
            messages=[
                SupportMessage(
                    id=str(item["id"]),
                    ticket_id=str(item["ticket_id"]),
                    author=str(item["author_type"]),
                    body=str(item["body"]),
                )
                for item in messages
            ],
        )
