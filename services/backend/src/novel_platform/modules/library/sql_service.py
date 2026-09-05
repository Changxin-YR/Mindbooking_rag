"""SQLAlchemy adapter for durable bookshelf entries."""

from datetime import UTC

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from novel_platform.modules.library.application import LibraryService
from novel_platform.modules.library.domain import BookshelfEntry


class SqlLibraryService(LibraryService):
    """Persist the existing bookshelf contract."""

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        metadata = sa.MetaData()
        self._entries_table = sa.Table("bookshelf_entries", metadata, autoload_with=engine)

    def add(self, account_id: str, book_id: str, group_name: str = "default") -> BookshelfEntry:
        with self.engine.begin() as connection:
            row = self._row(connection, account_id, book_id, lock=True)
            if row is not None:
                connection.execute(
                    self._entries_table.update()
                    .where(
                        self._entries_table.c.account_id == account_id,
                        self._entries_table.c.book_id == book_id,
                    )
                    .values(group_name=group_name)
                )
                updated = self._row(connection, account_id, book_id)
                if updated is None:
                    raise RuntimeError("bookshelf entry disappeared during update")
                return self._entry_from_row(updated)

            entry = BookshelfEntry(account_id, book_id, group_name)
            connection.execute(
                self._entries_table.insert().values(
                    account_id=entry.account_id,
                    book_id=entry.book_id,
                    group_name=entry.group_name,
                    created_at=entry.added_at,
                )
            )
            return entry

    def remove(self, account_id: str, book_id: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                self._entries_table.delete().where(
                    self._entries_table.c.account_id == account_id,
                    self._entries_table.c.book_id == book_id,
                )
            )

    def list(self, account_id: str) -> list[BookshelfEntry]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(self._entries_table)
                .where(self._entries_table.c.account_id == account_id)
                .order_by(self._entries_table.c.created_at, self._entries_table.c.book_id)
            ).mappings()
            return [self._entry_from_row(row) for row in rows]

    def _row(
        self, connection: Connection, account_id: str, book_id: str, *, lock: bool = False
    ) -> sa.RowMapping | None:
        query = sa.select(self._entries_table).where(
            self._entries_table.c.account_id == account_id,
            self._entries_table.c.book_id == book_id,
        )
        if lock:
            query = query.with_for_update()
        return connection.execute(query).mappings().one_or_none()

    @staticmethod
    def _entry_from_row(row: sa.RowMapping) -> BookshelfEntry:
        added_at = row["created_at"]
        if added_at.tzinfo is None:
            added_at = added_at.replace(tzinfo=UTC)
        return BookshelfEntry(
            account_id=str(row["account_id"]),
            book_id=str(row["book_id"]),
            group_name=str(row["group_name"]),
            added_at=added_at,
        )


# Keep the initial all-caps spelling available to callers created during the
# first SQL adapter draft.
SQLLibraryService = SqlLibraryService
