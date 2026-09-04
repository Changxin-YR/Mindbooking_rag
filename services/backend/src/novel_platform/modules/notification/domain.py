from dataclasses import dataclass
from enum import StrEnum


class NotificationCategory(StrEnum):
    SYSTEM = "SYSTEM"
    SECURITY = "SECURITY"
    MARKETING = "MARKETING"


class NotificationPriority(StrEnum):
    NORMAL = "NORMAL"
    P0 = "P0"


@dataclass(frozen=True, slots=True)
class Notification:
    id: str
    account_id: str
    category: NotificationCategory
    priority: NotificationPriority
    channels: frozenset[str]
