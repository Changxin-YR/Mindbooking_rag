from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class AccessMode(StrEnum):
    FREE = "FREE"
    PURCHASED = "PURCHASED"
    LIMITED_FREE = "LIMITED_FREE"
    MEMBER_FREE = "MEMBER_FREE"
    VIP_REQUIRED = "VIP_REQUIRED"


@dataclass(frozen=True, slots=True)
class ChapterPolicy:
    price_coin: int
    access_mode: AccessMode = AccessMode.VIP_REQUIRED


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
