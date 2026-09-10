import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.content.domain import (
    BookLifecycle,
    BookVisibility,
    CommercialPolicy,
    PublishState,
    VisibilityState,
)
from novel_platform.modules.content.sql_service import SqlContentService


def _schema() -> sa.MetaData:
    metadata = sa.MetaData()
    books = sa.Table(
        "books",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("lifecycle", sa.String(32), nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False),
        sa.Column("public_metadata_version_id", sa.String(64)),
    )
    sa.Table(
        "book_metadata_versions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), sa.ForeignKey(books.c.id), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("synopsis", sa.Text, nullable=False),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("channel", sa.String(16), nullable=False, server_default="UNSPECIFIED"),
        sa.Column("category", sa.String(64), nullable=False, server_default=""),
        sa.Column("tags_json", sa.Text, nullable=False, server_default="[]"),
        sa.UniqueConstraint("book_id", "version"),
    )
    volumes = sa.Table(
        "volumes",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), sa.ForeignKey(books.c.id), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.UniqueConstraint("book_id", "number"),
    )
    chapters = sa.Table(
        "chapters",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("volume_id", sa.String(64), sa.ForeignKey(volumes.c.id), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("commercial_policy", sa.String(16), nullable=False),
        sa.Column("publish_state", sa.String(16), nullable=False),
        sa.Column("visibility_state", sa.String(32), nullable=False),
        sa.Column("published_version_id", sa.String(64)),
        sa.UniqueConstraint("volume_id", "number"),
    )
    sa.Table(
        "chapter_draft_heads",
        metadata,
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey(chapters.c.id), primary_key=True),
        sa.Column("current_revision", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_snapshot_id", sa.String(64)),
    )
    snapshots = sa.Table(
        "chapter_draft_snapshots",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey(chapters.c.id), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("save_mode", sa.String(16), nullable=False),
        sa.UniqueConstraint("chapter_id", "revision"),
    )
    sa.Table(
        "chapter_versions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey(chapters.c.id), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("snapshot_id", sa.String(64), sa.ForeignKey(snapshots.c.id), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("word_count", sa.Integer, nullable=False),
        sa.UniqueConstraint("chapter_id", "version"),
    )
    return metadata


def _service() -> tuple[SqlContentService, sa.Engine]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _schema().create_all(engine)
    return SqlContentService(engine), engine


def test_sql_content_survives_service_rebuild() -> None:
    service, _ = _service()
    book = service.create_book(
        "author-1",
        "Book",
        "Synopsis",
        channel="MALE",
        category="Fantasy",
        tags=("system", "upgrade"),
    )
    volume = service.create_volume(book.id, "Volume 1", 1)
    chapter = service.create_chapter(volume.id, "Chapter 1", CommercialPolicy.FREE)
    snapshot = service.save_draft(chapter.id, "fixed content", save_mode="MANUAL")
    version = service.create_chapter_version(chapter.id, snapshot.id)

    rebuilt = SqlContentService(service.engine)
    assert rebuilt.get_book(book.id) == book
    assert rebuilt.get_book_metadata(book.id).tags == ("system", "upgrade")
    assert rebuilt.get_volume(volume.id) == volume
    persisted_chapter = rebuilt.get_chapter(chapter.id)
    assert persisted_chapter.draft_revision == 1
    assert persisted_chapter.snapshot_ids == [snapshot.id]
    assert persisted_chapter.version_ids == [version.id]
    assert rebuilt.get_snapshot(snapshot.id) == snapshot
    assert rebuilt.get_chapter_version(version.id) == version
    assert rebuilt.list_chapters(book.id) == [persisted_chapter]


def test_sql_content_publishes_the_fixed_version_and_keeps_it_immutable() -> None:
    service, _ = _service()
    book = service.create_book("author-1", "Book")
    volume = service.create_volume(book.id, "Volume 1", 1)
    chapter = service.create_chapter(volume.id, "Chapter 1", CommercialPolicy.FREE)
    version = service.create_chapter_version(chapter.id, service.save_draft(chapter.id, "v1").id)

    service.publish_fixed_versions(book.id, [version.id])
    rebuilt = SqlContentService(service.engine)

    persisted_book = rebuilt.get_book(book.id)
    persisted_chapter = rebuilt.get_chapter(chapter.id)
    assert persisted_book.lifecycle is BookLifecycle.SERIALIZING
    assert persisted_book.visibility is BookVisibility.PUBLIC
    assert persisted_chapter.publish_state is PublishState.PUBLISHED
    assert persisted_chapter.visibility_state is VisibilityState.PUBLIC
    assert persisted_chapter.published_version_id == version.id
    assert rebuilt.get_book_metadata(book.id, public_only=True).is_public
    assert rebuilt.get_chapter_version(version.id).content == "v1"


def test_sql_list_books_for_author_includes_private_and_public_only_for_owner() -> None:
    service, _ = _service()
    private = service.create_book("author-1", "Private")
    public = service.create_book("author-1", "Public")
    service.set_book_visibility(public.id, BookVisibility.PUBLIC)
    service.publish_metadata_version(public.id, service.get_book(public.id).metadata_version_ids[0])
    service.create_book("author-2", "Other")

    books = service.list_books_for_author("author-1")

    assert [(book.id, metadata.title, book.visibility) for book, metadata in books] == sorted(
        [
            (private.id, "Private", BookVisibility.PRIVATE),
            (public.id, "Public", BookVisibility.PUBLIC),
        ],
        key=lambda item: item[0],
    )


def test_sql_content_platform_can_change_chapter_commercial_policy() -> None:
    service, _ = _service()
    book = service.create_book("author-1", "Book")
    volume = service.create_volume(book.id, "Volume 1", 1)
    chapter = service.create_chapter(volume.id, "Chapter 1", CommercialPolicy.FREE)

    updated = service.set_chapter_commercial_policy(chapter.id, CommercialPolicy.VIP)

    assert updated.commercial_policy is CommercialPolicy.VIP
    assert (
        SqlContentService(service.engine).get_chapter(chapter.id).commercial_policy
        is CommercialPolicy.VIP
    )
