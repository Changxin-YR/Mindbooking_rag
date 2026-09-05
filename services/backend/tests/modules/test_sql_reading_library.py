import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.library.sql_service import SqlLibraryService
from novel_platform.modules.reading.domain import ProgressConflict
from novel_platform.modules.reading.sql_service import SqlReadingService


def _engine() -> sa.Engine:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE book_reading_progress ("
            "account_id VARCHAR(64) NOT NULL, book_id VARCHAR(64) NOT NULL, "
            "last_chapter_id VARCHAR(64), last_chapter_number INTEGER NOT NULL, "
            "last_position INTEGER NOT NULL, furthest_chapter_id VARCHAR(64), "
            "furthest_chapter_number INTEGER NOT NULL, furthest_position INTEGER NOT NULL, "
            "revision INTEGER NOT NULL, current_session_id VARCHAR(128), created_at DATETIME NOT NULL, "
            "PRIMARY KEY (account_id, book_id))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE bookshelf_entries ("
            "account_id VARCHAR(64) NOT NULL, book_id VARCHAR(64) NOT NULL, "
            "group_name VARCHAR(64) NOT NULL, created_at DATETIME NOT NULL, "
            "PRIMARY KEY (account_id, book_id))"
        )
    return engine


def test_sql_reading_persists_progress_and_revision_conflict() -> None:
    engine = _engine()
    service = SqlReadingService(engine)

    progress = service.update_progress(
        "account-1",
        "book-1",
        chapter_id="chapter-10",
        chapter_number=10,
        position=20,
        expected_revision=0,
        session_id="tab-1",
    )
    service.update_progress(
        "account-1",
        "book-1",
        chapter_id="chapter-2",
        chapter_number=2,
        position=30,
        expected_revision=progress.revision,
        session_id="tab-1",
    )

    rebuilt = SqlReadingService(engine)
    persisted = rebuilt.get_progress("account-1", "book-1")
    assert persisted.last_chapter_id == "chapter-2"
    assert persisted.furthest_chapter_id == "chapter-10"
    with pytest.raises(ProgressConflict):
        rebuilt.update_progress(
            "account-1",
            "book-1",
            chapter_id="chapter-1",
            chapter_number=1,
            position=1,
            expected_revision=0,
            session_id="tab-1",
        )


def test_sql_library_persists_group_and_removal() -> None:
    engine = _engine()
    service = SqlLibraryService(engine)

    created = service.add("account-1", "book-1", "favorites")
    assert created.group_name == "favorites"
    assert SqlLibraryService(engine).list("account-1") == [created]

    updated = service.add("account-1", "book-1", "later")
    assert updated.group_name == "later"
    assert updated.added_at == created.added_at
    service.remove("account-1", "book-1")
    assert SqlLibraryService(engine).list("account-1") == []
