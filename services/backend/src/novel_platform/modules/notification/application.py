from collections.abc import Iterable
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
