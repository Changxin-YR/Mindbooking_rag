"""SQLAlchemy adapter for durable reader progress."""

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from novel_platform.modules.reading.application import ReadingService
from novel_platform.modules.reading.domain import ProgressConflict, ReadingProgress


class SqlReadingService(ReadingService):
    """Persist the existing reading progress contract."""

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        metadata = sa.MetaData()
        self._progress_table = sa.Table("book_reading_progress", metadata, autoload_with=engine)

    def get_progress(self, account_id: str, book_id: str) -> ReadingProgress:
        with self.engine.begin() as connection:
            row = self._row(connection, account_id, book_id)
            return (
                self._progress_from_row(row)
                if row is not None
                else ReadingProgress(account_id, book_id)
            )

    def start_session(self, account_id: str, book_id: str, session_id: str) -> ReadingProgress:
        with self.engine.begin() as connection:
            progress, exists = self._locked_progress(connection, account_id, book_id)
            service = ReadingService()
            service._progress[(account_id, book_id)] = progress
            progress = service.start_session(account_id, book_id, session_id)
            self._save(connection, progress, exists, progress.revision)
            return progress

    def update_progress(
        self,
        account_id: str,
        book_id: str,
        *,
        chapter_id: str,
        chapter_number: int,
        position: int,
        expected_revision: int,
        session_id: str,
    ) -> ReadingProgress:
        with self.engine.begin() as connection:
            progress, exists = self._locked_progress(connection, account_id, book_id)
            service = ReadingService()
            service._progress[(account_id, book_id)] = progress
            progress = service.update_progress(
                account_id,
                book_id,
                chapter_id=chapter_id,
                chapter_number=chapter_number,
                position=position,
                expected_revision=expected_revision,
                session_id=session_id,
            )
            self._save(connection, progress, exists, expected_revision)
            return progress

    def _locked_progress(
        self, connection: Connection, account_id: str, book_id: str
    ) -> tuple[ReadingProgress, bool]:
        row = (
            connection.execute(
                sa.select(self._progress_table)
                .where(
                    self._progress_table.c.account_id == account_id,
                    self._progress_table.c.book_id == book_id,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        return (
            (self._progress_from_row(row), True)
            if row is not None
            else (ReadingProgress(account_id, book_id), False)
        )

    def _row(self, connection: Connection, account_id: str, book_id: str) -> sa.RowMapping | None:
        return (
            connection.execute(
                sa.select(self._progress_table).where(
                    self._progress_table.c.account_id == account_id,
                    self._progress_table.c.book_id == book_id,
                )
            )
            .mappings()
            .one_or_none()
        )

    def _save(
        self,
        connection: Connection,
        progress: ReadingProgress,
        exists: bool,
        expected_revision: int,
    ) -> None:
        values: dict[str, Any] = {
            "account_id": progress.account_id,
            "book_id": progress.book_id,
            "last_chapter_id": progress.last_chapter_id,
            "last_chapter_number": progress.last_chapter_number,
            "last_position": progress.last_position,
            "furthest_chapter_id": progress.furthest_chapter_id,
            "furthest_chapter_number": progress.furthest_chapter_number,
            "furthest_position": progress.furthest_position,
            "revision": progress.revision,
            "current_session_id": progress.current_session_id,
        }
        if not exists:
            values["created_at"] = datetime.now(UTC)
            connection.execute(self._progress_table.insert().values(**values))
            return

        updated = connection.execute(
            self._progress_table.update()
            .where(
                self._progress_table.c.account_id == progress.account_id,
                self._progress_table.c.book_id == progress.book_id,
                self._progress_table.c.revision == expected_revision,
            )
            .values(**values)
        )
        if updated.rowcount != 1:
            current = self._row(connection, progress.account_id, progress.book_id)
            if current is not None:
                raise ProgressConflict(self._progress_from_row(current))

    @staticmethod
    def _progress_from_row(row: sa.RowMapping) -> ReadingProgress:
        return ReadingProgress(
            account_id=str(row["account_id"]),
            book_id=str(row["book_id"]),
            last_chapter_id=row["last_chapter_id"],
            last_chapter_number=int(row["last_chapter_number"]),
            last_position=int(row["last_position"]),
            furthest_chapter_id=row["furthest_chapter_id"],
            furthest_chapter_number=int(row["furthest_chapter_number"]),
            furthest_position=int(row["furthest_position"]),
            revision=int(row["revision"]),
            current_session_id=row["current_session_id"],
        )


# Keep the initial all-caps spelling available to callers created during the
# first SQL adapter draft.
SQLReadingService = SqlReadingService
