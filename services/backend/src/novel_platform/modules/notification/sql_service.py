"""SQLAlchemy adapter for notification facts and preferences."""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
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
            connection.execute(
                self._notifications.insert().values(
                    id=notification.id,
                    account_id=notification.account_id,
                    category=notification.category.value,
                    priority=notification.priority.value,
                    channels=",".join(sorted(notification.channels)),
                    created_at=datetime.now(UTC),
                )
            )
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
