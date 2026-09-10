from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class AccessMode(StrEnum):
    FREE = "FREE"
    PURCHASED = "PURCHASED"
    LIMITED_FREE = "LIMITED_FREE"
    MEMBER_FREE = "MEMBER_FREE"
    VIP_REQUIRED = "VIP_REQUIRED"


class TicketType(StrEnum):
    RECOMMEND = "RECOMMEND"
    MONTHLY = "MONTHLY"


class TicketRiskStatus(StrEnum):
    NORMAL = "NORMAL"
    FROZEN = "FROZEN"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True, slots=True)
class ChapterPolicy:
    price_coin: int
    access_mode: AccessMode = AccessMode.VIP_REQUIRED


@dataclass(frozen=True, slots=True)
class MembershipPlan:
    plan_code: str
    name: str
    version: int
    duration_days: int
    price_cents: int
    daily_recommend_tickets: int
    monthly_chapter_tickets: int
    status: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class MembershipOrder:
    id: str
    payment_no: str
    account_id: str
    plan_code: str
    plan_version: int
    channel: str
    price_cents: int
    status: str
    provider: str | None = None
    checkout_url: str | None = None


@dataclass(frozen=True, slots=True)
class TicketBalance:
    account_id: str
    recommend: int = 0
    monthly: int = 0

    def for_type(self, ticket_type: TicketType) -> int:
        return self.recommend if ticket_type is TicketType.RECOMMEND else self.monthly


@dataclass(frozen=True, slots=True)
class BookTicketVote:
    id: str
    account_id: str
    book_id: str
    ticket_type: TicketType
    quantity: int
    risk_status: TicketRiskStatus
    idempotency_key: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class GiftDefinition:
    gift_code: str
    name: str
    price_coin: int
    fan_value: int
    spend_mode: str = "GIFT_AND_RECHARGE"


@dataclass(frozen=True, slots=True)
class GiftOrder:
    id: str
    account_id: str
    book_id: str
    author_id: str
    gift_code: str
    quantity: int
    total_coin: int
    income_base_coin: int
    fan_value: int
    status: str
    idempotency_key: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class FanProfile:
    account_id: str
    book_id: str
    value: int
    level: int


@dataclass(frozen=True, slots=True)
class UserGrowthProfile:
    account_id: str
    points: int
    level: int


class MembershipService:
    def __init__(self) -> None:
        self._expires_at: dict[str, datetime] = {}
        self._library_books: set[str] = set()

    def activate(self, account_id: str, expires_at: datetime) -> None:
        self._expires_at[account_id] = expires_at

    def add_library_book(self, book_id: str) -> None:
        self._library_books.add(book_id)

    def is_active(self, account_id: str, now: datetime | None = None) -> bool:
        expires_at = self._expires_at.get(account_id)
        return expires_at is not None and expires_at > (now or datetime.now(UTC))

    def access(
        self,
        account_id: str,
        chapter_id: str,
        policy: ChapterPolicy,
        purchased: bool,
        now: datetime | None = None,
        book_id: str | None = None,
    ) -> AccessMode:
        del chapter_id
        if purchased:
            return AccessMode.PURCHASED
        if policy.access_mode is AccessMode.FREE:
            return AccessMode.FREE
        if policy.access_mode is AccessMode.LIMITED_FREE:
            return AccessMode.LIMITED_FREE
        if book_id and book_id in self._library_books and self.is_active(account_id, now):
            return AccessMode.MEMBER_FREE
        return AccessMode.VIP_REQUIRED
