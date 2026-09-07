from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import uuid4

from novel_platform.modules.notification.domain import (
    Notification,
    NotificationCategory,
    NotificationPriority,
)


class NotificationService:
    def __init__(self) -> None:
        self._notifications: dict[str, Notification] = {}
        self._marketing_enabled: dict[str, bool] = {}

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
        self._notifications[notification.id] = notification
        return notification

    def set_marketing_enabled(self, account_id: str, enabled: bool) -> None:
        if not enabled:
            raise ValueError("marketing notifications cannot be disabled")
        self._marketing_enabled[account_id] = enabled

    def list(
        self,
        account_id: str,
        *,
        category: NotificationCategory | None = None,
        limit: int = 50,
    ) -> tuple[Notification, ...]:
        if limit < 1 or limit > 100:
            raise ValueError("NOTIFICATION_LIMIT_INVALID")
        items = [
            item
            for item in self._notifications.values()
            if item.account_id == account_id and (category is None or item.category is category)
        ]
        return tuple(reversed(items[-limit:]))

    def mark_read(self, account_id: str, notification_id: str) -> Notification:
        notification = self._notifications.get(notification_id)
        if notification is None or notification.account_id != account_id:
            raise KeyError(notification_id)
        if notification.is_read:
            return notification
        updated = Notification(
            notification.id,
            notification.account_id,
            notification.category,
            notification.priority,
            notification.channels,
            datetime.now(UTC),
        )
        self._notifications[notification_id] = updated
        return updated

    def unread_count(self, account_id: str) -> int:
        return sum(
            item.account_id == account_id and not item.is_read
            for item in self._notifications.values()
        )
