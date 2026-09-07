"""SQLAlchemy adapter for notification facts and preferences."""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from novel_platform.modules.notification.application import NotificationService
from novel_platform.modules.notification.domain import (
    Notification,
    NotificationCategory,
    NotificationPriority,
)


class SqlNotificationService(NotificationService):
    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        metadata = sa.MetaData()
        self._notifications: Any = sa.Table("notifications", metadata, autoload_with=engine)
        self._preferences: Any = sa.Table(
            "notification_preferences", metadata, autoload_with=engine
        )
        self._read_at = self._notifications.c.get("read_at")
        self._read_ids: set[str] = set()

    def send(
        self,
        account_id: str,
        category: NotificationCategory,
        priority: NotificationPriority,
        channels: Iterable[str],
    ) -> Notification:
        selected = frozenset(channels)
        if category is NotificationCategory.SECURITY and priority is NotificationPriority.P0:
            selected = frozenset({"IN_APP", "SMS"})
        notification = Notification(
            id=f"NTF_{uuid4().hex}",
            account_id=account_id,
            category=category,
            priority=priority,
            channels=selected,
        )
        with self.engine.begin() as connection:
            values: dict[str, object] = {
                "id": notification.id,
                "account_id": notification.account_id,
                "category": notification.category.value,
                "priority": notification.priority.value,
                "channels": ",".join(sorted(notification.channels)),
                "created_at": datetime.now(UTC),
            }
            if self._read_at is not None:
                values["read_at"] = None
            connection.execute(self._notifications.insert().values(**values))
        return notification

    def set_marketing_enabled(self, account_id: str, enabled: bool) -> None:
        if not enabled:
            raise ValueError("marketing notifications cannot be disabled")
        with self.engine.begin() as connection:
            exists = connection.execute(
                sa.select(self._preferences.c.account_id).where(
                    self._preferences.c.account_id == account_id
                )
            ).scalar_one_or_none()
            if exists is None:
                connection.execute(
                    self._preferences.insert().values(
                        account_id=account_id,
                        marketing_enabled=True,
                        created_at=datetime.now(UTC),
                    )
                )
            else:
                connection.execute(
                    self._preferences.update()
                    .where(self._preferences.c.account_id == account_id)
                    .values(marketing_enabled=True)
                )

    def list(
        self,
        account_id: str,
        *,
        category: NotificationCategory | None = None,
        limit: int = 50,
    ) -> tuple[Notification, ...]:
        if limit < 1 or limit > 100:
            raise ValueError("NOTIFICATION_LIMIT_INVALID")
        query = sa.select(self._notifications).where(self._notifications.c.account_id == account_id)
        if category is not None:
            query = query.where(self._notifications.c.category == category.value)
        query = query.order_by(
            self._notifications.c.created_at.desc(), self._notifications.c.id.desc()
        ).limit(limit)
        with self.engine.begin() as connection:
            rows = connection.execute(query).mappings()
            return tuple(self._from_row(row) for row in rows)

    def mark_read(self, account_id: str, notification_id: str) -> Notification:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._notifications)
                    .where(
                        self._notifications.c.id == notification_id,
                        self._notifications.c.account_id == account_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(notification_id)
            if self._read_at is None:
                self._read_ids.add(notification_id)
                return self._from_row(row)
            if row["read_at"] is None:
                read_at = datetime.now(UTC)
                connection.execute(
                    self._notifications.update()
                    .where(self._notifications.c.id == notification_id)
                    .values(read_at=read_at)
                )
                updated_row = dict(row)
                updated_row["read_at"] = read_at
                return self._from_row(updated_row)
            return self._from_row(row)

    def unread_count(self, account_id: str) -> int:
        with self.engine.begin() as connection:
            query = (
                sa.select(sa.func.count())
                .select_from(self._notifications)
                .where(self._notifications.c.account_id == account_id)
            )
            if self._read_at is not None:
                query = query.where(self._read_at.is_(None))
            else:
                rows = connection.execute(
                    sa.select(self._notifications.c.id).where(
                        self._notifications.c.account_id == account_id
                    )
                )
                return sum(str(row.id) not in self._read_ids for row in rows)
            return int(connection.execute(query).scalar_one())

    def _from_row(self, row: Any) -> Notification:
        channels = frozenset(filter(None, str(row["channels"]).split(",")))
        read_at = row.get("read_at")
        if read_at is None and str(row["id"]) in getattr(self, "_read_ids", set()):
            read_at = datetime.now(UTC)
        return Notification(
            id=str(row["id"]),
            account_id=str(row["account_id"]),
            category=NotificationCategory(str(row["category"])),
            priority=NotificationPriority(str(row["priority"])),
            channels=channels,
            read_at=cast(datetime | None, read_at),
        )
