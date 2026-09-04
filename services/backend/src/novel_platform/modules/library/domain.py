from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class BookshelfEntry:
    account_id: str
    book_id: str
    group_name: str = "default"
    added_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ChapterEntitlement:
    account_id: str
    chapter_id: str
    granted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
