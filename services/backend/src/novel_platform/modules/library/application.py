from novel_platform.modules.library.domain import BookshelfEntry, ChapterEntitlement


class EntitlementService:
    def __init__(self) -> None:
        self._entitlements: dict[tuple[str, str], ChapterEntitlement] = {}

    def grant(self, account_id: str, chapter_id: str) -> ChapterEntitlement:
        key = (account_id, chapter_id)
        if key not in self._entitlements:
            self._entitlements[key] = ChapterEntitlement(account_id, chapter_id)
        return self._entitlements[key]

    def has(self, account_id: str, chapter_id: str) -> bool:
        return (account_id, chapter_id) in self._entitlements


class LibraryService:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], BookshelfEntry] = {}

    def add(self, account_id: str, book_id: str, group_name: str = "default") -> BookshelfEntry:
        key = (account_id, book_id)
        self._entries[key] = BookshelfEntry(account_id, book_id, group_name)
        return self._entries[key]

    def remove(self, account_id: str, book_id: str) -> None:
        self._entries.pop((account_id, book_id), None)

    def list(self, account_id: str) -> list[BookshelfEntry]:
        return [
            entry
            for (entry_account_id, _), entry in self._entries.items()
            if entry_account_id == account_id
        ]
