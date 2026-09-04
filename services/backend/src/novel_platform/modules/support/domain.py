from dataclasses import dataclass, field
from enum import StrEnum


class SupportStatus(StrEnum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_USER = "WAITING_USER"
    WAITING_INTERNAL = "WAITING_INTERNAL"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class SupportPriority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


@dataclass(frozen=True, slots=True)
class SupportMessage:
    id: str
    ticket_id: str
    author: str
    body: str


@dataclass(slots=True)
class SupportTicket:
    id: str
    account_id: str
    category: str
    priority: SupportPriority
    status: SupportStatus = SupportStatus.NEW
    messages: list[SupportMessage] = field(default_factory=list)
