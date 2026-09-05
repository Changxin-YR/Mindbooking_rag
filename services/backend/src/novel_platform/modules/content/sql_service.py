"""SQLAlchemy content adapter for the existing content and review schema."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from novel_platform.modules.content.application import ContentService, _id
from novel_platform.modules.content.domain import (
    Book,
    BookLifecycle,
    BookMetadataVersion,
    BookVisibility,
    Chapter,
    ChapterVersion,
    CommercialPolicy,
    DraftSnapshot,
    PublishState,
    VisibilityState,
    Volume,
)


class SqlContentService(ContentService):
    """Persist the ContentService contract without changing its domain objects."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        metadata = sa.MetaData()
        self._books: Any = sa.Table("books", metadata, autoload_with=engine)
        self._metadata: Any = sa.Table("book_metadata_versions", metadata, autoload_with=engine)
        self._volumes: Any = sa.Table("volumes", metadata, autoload_with=engine)
        self._chapters: Any = sa.Table("chapters", metadata, autoload_with=engine)
        self._draft_heads = sa.Table("chapter_draft_heads", metadata, autoload_with=engine)
        self._snapshots: Any = sa.Table("chapter_draft_snapshots", metadata, autoload_with=engine)
        self._versions: Any = sa.Table("chapter_versions", metadata, autoload_with=engine)

    def create_book(
        self,
        author_id: str,
        title: str,
        synopsis: str = "",
        channel: str = "UNSPECIFIED",
        category: str = "",
        tags: tuple[str, ...] = (),
    ) -> Book:
        book = Book(id=_id("BK"), author_id=author_id)
        metadata = BookMetadataVersion(
            id=_id("BM"),
            book_id=book.id,
            version=1,
            title=title,
            synopsis=synopsis,
            channel=channel,
            category=category,
            tags=tags,
        )
        with self.engine.begin() as connection:
            connection.execute(
                self._books.insert().values(
                    id=book.id,
                    author_id=book.author_id,
                    lifecycle=book.lifecycle.value,
                    visibility=book.visibility.value,
                    public_metadata_version_id=None,
                )
            )
            values: dict[str, Any] = {
                "id": metadata.id,
                "book_id": metadata.book_id,
                "version": metadata.version,
                "title": metadata.title,
                "synopsis": metadata.synopsis,
                "is_public": metadata.is_public,
            }
            if "channel" in self._metadata.c:
                values["channel"] = metadata.channel
            if "category" in self._metadata.c:
                values["category"] = metadata.category
            if "tags_json" in self._metadata.c:
                values["tags_json"] = json.dumps(metadata.tags)
            connection.execute(self._metadata.insert().values(**values))
        book.metadata_version_ids.append(metadata.id)
        return book

    def get_book(self, book_id: str) -> Book:
        with self.engine.begin() as connection:
            return self._book_for_connection(connection, book_id)

    def get_book_metadata(self, book_id: str, public_only: bool = False) -> BookMetadataVersion:
        with self.engine.begin() as connection:
            book = self._book_row(connection, book_id)
            if book is None:
                raise KeyError(f"book {book_id} not found")
            if public_only and book["public_metadata_version_id"] is None:
                raise KeyError(f"book {book_id} has no public metadata")
            metadata_id = book["public_metadata_version_id"]
            if metadata_id is None:
                metadata_id = connection.execute(
                    sa.select(self._metadata.c.id)
                    .where(self._metadata.c.book_id == book_id)
                    .order_by(self._metadata.c.version.desc())
                    .limit(1)
                ).scalar_one()
            return self._metadata_for_connection(connection, str(metadata_id))

    def list_public_books(
        self,
        *,
        channel: str | None = None,
        category: str | None = None,
        tag: str | None = None,
        lifecycle: BookLifecycle | None = None,
        commercial_policy: CommercialPolicy | None = None,
        keyword: str | None = None,
    ) -> list[tuple[Book, BookMetadataVersion]]:
        normalized_keyword = keyword.strip().casefold() if keyword else None
        result: list[tuple[Book, BookMetadataVersion]] = []
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(self._books).where(
                    self._books.c.visibility == BookVisibility.PUBLIC.value
                )
            ).mappings()
            for row in rows:
                book = self._book_from_row(connection, row)
                metadata = self._metadata_for_connection(
                    connection, str(row["public_metadata_version_id"])
                )
                if channel and metadata.channel != channel:
                    continue
                if category and metadata.category != category:
                    continue
                if tag and tag not in metadata.tags:
                    continue
                if lifecycle and book.lifecycle is not lifecycle:
                    continue
                if normalized_keyword and not any(
                    normalized_keyword in value.casefold()
                    for value in (metadata.title, metadata.synopsis)
                ):
                    continue
                if commercial_policy and not any(
                    chapter.commercial_policy is commercial_policy
                    and chapter.publish_state is PublishState.PUBLISHED
                    and chapter.visibility_state is VisibilityState.PUBLIC
                    for chapter in self._chapters_for_book(connection, book.id)
                ):
                    continue
                result.append((book, metadata))
        return result

    def set_book_lifecycle(self, book_id: str, lifecycle: BookLifecycle) -> Book:
        with self.engine.begin() as connection:
            self._require_book_row(connection, book_id)
            connection.execute(
                self._books.update()
                .where(self._books.c.id == book_id)
                .values(lifecycle=lifecycle.value)
            )
            return self._book_for_connection(connection, book_id)

    def set_book_visibility(self, book_id: str, visibility: BookVisibility) -> Book:
        with self.engine.begin() as connection:
            self._require_book_row(connection, book_id)
            connection.execute(
                self._books.update()
                .where(self._books.c.id == book_id)
                .values(visibility=visibility.value)
            )
            return self._book_for_connection(connection, book_id)

    def create_metadata_version(
        self, book_id: str, title: str, synopsis: str = ""
    ) -> BookMetadataVersion:
        with self.engine.begin() as connection:
            self._require_book_row(connection, book_id)
            current = connection.execute(
                sa.select(sa.func.max(self._metadata.c.version)).where(
                    self._metadata.c.book_id == book_id
                )
            ).scalar()
            metadata = BookMetadataVersion(
                id=_id("BM"),
                book_id=book_id,
                version=int(current or 0) + 1,
                title=title,
                synopsis=synopsis,
            )
            values: dict[str, Any] = {
                "id": metadata.id,
                "book_id": metadata.book_id,
                "version": metadata.version,
                "title": metadata.title,
                "synopsis": metadata.synopsis,
                "is_public": False,
            }
            if "channel" in self._metadata.c:
                values["channel"] = metadata.channel
            if "category" in self._metadata.c:
                values["category"] = metadata.category
            if "tags_json" in self._metadata.c:
                values["tags_json"] = "[]"
            connection.execute(self._metadata.insert().values(**values))
            return metadata

    def publish_metadata_version(self, book_id: str, metadata_id: str) -> Book:
        with self.engine.begin() as connection:
            self._require_book_row(connection, book_id)
            metadata = self._metadata_row(connection, metadata_id)
            if metadata is None:
                raise KeyError(metadata_id)
            if metadata["book_id"] != book_id:
                raise ValueError("metadata version does not belong to book")
            connection.execute(
                self._metadata.update()
                .where(self._metadata.c.id == metadata_id)
                .values(is_public=True)
            )
            connection.execute(
                self._books.update()
                .where(self._books.c.id == book_id)
                .values(public_metadata_version_id=metadata_id)
            )
            return self._book_for_connection(connection, book_id)

    def create_volume(self, book_id: str, title: str, number: int) -> Volume:
        if number < 1:
            raise ValueError("volume number must be positive")
        volume = Volume(id=_id("VOL"), book_id=book_id, number=number, title=title)
        try:
            with self.engine.begin() as connection:
                self._require_book_row(connection, book_id)
                connection.execute(
                    self._volumes.insert().values(
                        id=volume.id,
                        book_id=volume.book_id,
                        number=volume.number,
                        title=volume.title,
                    )
                )
        except IntegrityError as exc:
            raise ValueError("volume number already exists") from exc
        return volume

    def get_volume(self, volume_id: str) -> Volume:
        with self.engine.begin() as connection:
            row = (
                connection.execute(sa.select(self._volumes).where(self._volumes.c.id == volume_id))
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(f"volume {volume_id} not found")
            return Volume(
                id=str(row["id"]),
                book_id=str(row["book_id"]),
                number=int(row["number"]),
                title=str(row["title"]),
            )

    def create_chapter(
        self,
        volume_id: str,
        title: str,
        commercial_policy: CommercialPolicy,
        number: int | None = None,
    ) -> Chapter:
        try:
            with self.engine.begin() as connection:
                self._require_volume_row(connection, volume_id)
                if number is None:
                    current = connection.execute(
                        sa.select(sa.func.max(self._chapters.c.number)).where(
                            self._chapters.c.volume_id == volume_id
                        )
                    ).scalar()
                    number = int(current or 0) + 1
                if number < 1:
                    raise ValueError("chapter number must be positive")
                chapter = Chapter(
                    id=_id("CH"),
                    volume_id=volume_id,
                    number=number,
                    title=title,
                    commercial_policy=commercial_policy,
                )
                connection.execute(
                    self._chapters.insert().values(
                        id=chapter.id,
                        volume_id=chapter.volume_id,
                        number=chapter.number,
                        title=chapter.title,
                        commercial_policy=chapter.commercial_policy.value,
                        publish_state=chapter.publish_state.value,
                        visibility_state=chapter.visibility_state.value,
                        published_version_id=None,
                    )
                )
                connection.execute(
                    self._draft_heads.insert().values(
                        chapter_id=chapter.id,
                        current_revision=0,
                        current_snapshot_id=None,
                    )
                )
                return chapter
        except IntegrityError as exc:
            raise ValueError("chapter number already exists") from exc

    def get_chapter(self, chapter_id: str) -> Chapter:
        with self.engine.begin() as connection:
            return self._chapter_for_connection(connection, chapter_id)

    def set_chapter_commercial_policy(
        self, chapter_id: str, commercial_policy: CommercialPolicy
    ) -> Chapter:
        with self.engine.begin() as connection:
            self._require_chapter_row(connection, chapter_id)
            connection.execute(
                self._chapters.update()
                .where(self._chapters.c.id == chapter_id)
                .values(commercial_policy=commercial_policy.value)
            )
            return self._chapter_for_connection(connection, chapter_id)

    def save_draft(
        self,
        chapter_id: str,
        content: str,
        save_mode: str = "AUTO",
        expected_revision: int | None = None,
    ) -> DraftSnapshot:
        with self.engine.begin() as connection:
            self._require_chapter_row(connection, chapter_id)
            head = (
                connection.execute(
                    sa.select(
                        self._draft_heads.c.current_revision,
                    )
                    .where(self._draft_heads.c.chapter_id == chapter_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if head is None:
                raise KeyError(chapter_id)
            current_revision = int(head["current_revision"])
            if expected_revision is not None and expected_revision != current_revision:
                raise ValueError("draft revision conflict")
            snapshot = DraftSnapshot(
                id=_id("DS"),
                chapter_id=chapter_id,
                revision=current_revision + 1,
                content=content,
                save_mode=save_mode,
            )
            connection.execute(
                self._snapshots.insert().values(
                    id=snapshot.id,
                    chapter_id=snapshot.chapter_id,
                    revision=snapshot.revision,
                    content=snapshot.content,
                    save_mode=snapshot.save_mode,
                )
            )
            updated = connection.execute(
                self._draft_heads.update()
                .where(
                    self._draft_heads.c.chapter_id == chapter_id,
                    self._draft_heads.c.current_revision == current_revision,
                )
                .values(
                    current_revision=snapshot.revision,
                    current_snapshot_id=snapshot.id,
                )
            )
            if updated.rowcount != 1:
                raise ValueError("draft revision conflict")
            return snapshot

    def get_snapshot(self, snapshot_id: str) -> DraftSnapshot:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._snapshots).where(self._snapshots.c.id == snapshot_id)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(snapshot_id)
            return DraftSnapshot(
                id=str(row["id"]),
                chapter_id=str(row["chapter_id"]),
                revision=int(row["revision"]),
                content=str(row["content"]),
                save_mode=str(row["save_mode"]),
            )

    def create_chapter_version(
        self, chapter_id: str, snapshot_id: str | None = None
    ) -> ChapterVersion:
        with self.engine.begin() as connection:
            self._require_chapter_row(connection, chapter_id)
            if snapshot_id is None:
                snapshot_id = connection.execute(
                    sa.select(self._snapshots.c.id)
                    .where(self._snapshots.c.chapter_id == chapter_id)
                    .order_by(self._snapshots.c.revision.desc())
                    .limit(1)
                ).scalar_one_or_none()
                if snapshot_id is None:
                    raise ValueError("chapter has no draft snapshot")
            snapshot = self._snapshot_row(connection, snapshot_id)
            if snapshot is None:
                raise KeyError(snapshot_id)
            if snapshot["chapter_id"] != chapter_id:
                raise ValueError("snapshot does not belong to chapter")
            current = connection.execute(
                sa.select(sa.func.max(self._versions.c.version)).where(
                    self._versions.c.chapter_id == chapter_id
                )
            ).scalar()
            version = ChapterVersion(
                id=_id("CV"),
                chapter_id=chapter_id,
                version=int(current or 0) + 1,
                snapshot_id=str(snapshot["id"]),
                content=str(snapshot["content"]),
                word_count=len(str(snapshot["content"])),
            )
            connection.execute(
                self._versions.insert().values(
                    id=version.id,
                    chapter_id=version.chapter_id,
                    version=version.version,
                    snapshot_id=version.snapshot_id,
                    content=version.content,
                    word_count=version.word_count,
                )
            )
            return version

    def get_chapter_version(self, version_id: str) -> ChapterVersion:
        with self.engine.begin() as connection:
            return self._version_for_connection(connection, version_id)

    def update_published_version(self, version_id: str, content: str) -> None:
        del content
        with self.engine.begin() as connection:
            if self._version_row(connection, version_id) is None:
                raise KeyError(version_id)
        raise ValueError("published chapter version is immutable")

    def publish_chapter_version(self, chapter_id: str, version_id: str) -> Chapter:
        with self.engine.begin() as connection:
            self._require_chapter_row(connection, chapter_id)
            version = self._version_row(connection, version_id)
            if version is None:
                raise KeyError(version_id)
            if version["chapter_id"] != chapter_id:
                raise ValueError("chapter version does not belong to chapter")
            connection.execute(
                self._chapters.update()
                .where(self._chapters.c.id == chapter_id)
                .values(
                    published_version_id=version_id,
                    publish_state=PublishState.PUBLISHED.value,
                    visibility_state=VisibilityState.PUBLIC.value,
                )
            )
            return self._chapter_for_connection(connection, chapter_id)

    def publish_fixed_versions(
        self, book_id: str, version_ids: list[str] | tuple[str, ...]
    ) -> None:
        with self.engine.begin() as connection:
            book = self._require_book_row(connection, book_id)
            chapter_ids: list[str] = []
            for version_id in version_ids:
                version = self._version_row(connection, version_id)
                if version is None:
                    raise KeyError(version_id)
                chapter = self._require_chapter_row(connection, str(version["chapter_id"]))
                volume = self._require_volume_row(connection, str(chapter["volume_id"]))
                if volume["book_id"] != book_id:
                    raise ValueError("fixed chapter version does not belong to book")
                chapter_ids.append(str(chapter["id"]))
            for chapter_id, version_id in zip(chapter_ids, version_ids):
                connection.execute(
                    self._chapters.update()
                    .where(self._chapters.c.id == chapter_id)
                    .values(
                        published_version_id=version_id,
                        publish_state=PublishState.PUBLISHED.value,
                        visibility_state=VisibilityState.PUBLIC.value,
                    )
                )
            if book["public_metadata_version_id"] is None:
                metadata_id = connection.execute(
                    sa.select(self._metadata.c.id)
                    .where(self._metadata.c.book_id == book_id)
                    .order_by(self._metadata.c.version)
                    .limit(1)
                ).scalar_one()
                connection.execute(
                    self._metadata.update()
                    .where(self._metadata.c.id == metadata_id)
                    .values(is_public=True)
                )
                connection.execute(
                    self._books.update()
                    .where(self._books.c.id == book_id)
                    .values(public_metadata_version_id=metadata_id)
                )
            connection.execute(
                self._books.update()
                .where(self._books.c.id == book_id)
                .values(
                    lifecycle=BookLifecycle.SERIALIZING.value,
                    visibility=BookVisibility.PUBLIC.value,
                )
            )

    def list_chapters(self, book_id: str) -> list[Chapter]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(self._chapters)
                .join(self._volumes, self._volumes.c.id == self._chapters.c.volume_id)
                .where(self._volumes.c.book_id == book_id)
                .order_by(self._volumes.c.number, self._chapters.c.number)
            ).mappings()
            return [self._chapter_from_row(connection, row) for row in rows]

    def get_public_free_chapter(self, book_id: str, chapter_id: str) -> ChapterVersion:
        with self.engine.begin() as connection:
            book = self._require_book_row(connection, book_id)
            chapter = self._chapter_for_connection(connection, chapter_id)
            volume = self._require_volume_row(connection, chapter.volume_id)
            if volume["book_id"] != book_id:
                raise KeyError(chapter_id)
            if book["visibility"] != BookVisibility.PUBLIC.value:
                raise KeyError(book_id)
            if (
                chapter.publish_state is not PublishState.PUBLISHED
                or chapter.visibility_state is not VisibilityState.PUBLIC
            ):
                raise KeyError(chapter_id)
            if chapter.commercial_policy is not CommercialPolicy.FREE:
                raise ValueError("chapter requires VIP access")
            if chapter.published_version_id is None:
                raise KeyError(chapter_id)
            return self._version_for_connection(connection, chapter.published_version_id)

    def get_chapter_for_book(self, book_id: str, chapter_id: str) -> Chapter:
        with self.engine.begin() as connection:
            chapter = self._chapter_for_connection(connection, chapter_id)
            volume = self._require_volume_row(connection, chapter.volume_id)
            if volume["book_id"] != book_id:
                raise KeyError(chapter_id)
            return chapter

    def _book_for_connection(self, connection: Connection, book_id: str) -> Book:
        row = self._require_book_row(connection, book_id)
        return self._book_from_row(connection, row)

    def _book_from_row(self, connection: Connection, row: sa.RowMapping) -> Book:
        metadata_ids = [
            str(value)
            for value in connection.execute(
                sa.select(self._metadata.c.id)
                .where(self._metadata.c.book_id == row["id"])
                .order_by(self._metadata.c.version)
            ).scalars()
        ]
        return Book(
            id=str(row["id"]),
            author_id=str(row["author_id"]),
            lifecycle=BookLifecycle(str(row["lifecycle"])),
            visibility=BookVisibility(str(row["visibility"])),
            public_metadata_version_id=(
                str(row["public_metadata_version_id"])
                if row["public_metadata_version_id"] is not None
                else None
            ),
            metadata_version_ids=metadata_ids,
        )

    def _chapter_for_connection(self, connection: Connection, chapter_id: str) -> Chapter:
        row = self._require_chapter_row(connection, chapter_id)
        return self._chapter_from_row(connection, row)

    def _chapter_from_row(self, connection: Connection, row: sa.RowMapping) -> Chapter:
        snapshots = connection.execute(
            sa.select(self._snapshots.c.id)
            .where(self._snapshots.c.chapter_id == row["id"])
            .order_by(self._snapshots.c.revision)
        ).scalars()
        versions = connection.execute(
            sa.select(self._versions.c.id)
            .where(self._versions.c.chapter_id == row["id"])
            .order_by(self._versions.c.version)
        ).scalars()
        head_revision = connection.execute(
            sa.select(self._draft_heads.c.current_revision).where(
                self._draft_heads.c.chapter_id == row["id"]
            )
        ).scalar_one_or_none()
        return Chapter(
            id=str(row["id"]),
            volume_id=str(row["volume_id"]),
            number=int(row["number"]),
            title=str(row["title"]),
            commercial_policy=CommercialPolicy(str(row["commercial_policy"])),
            publish_state=PublishState(str(row["publish_state"])),
            visibility_state=VisibilityState(str(row["visibility_state"])),
            draft_revision=int(head_revision or 0),
            snapshot_ids=[str(value) for value in snapshots],
            version_ids=[str(value) for value in versions],
            published_version_id=(
                str(row["published_version_id"])
                if row["published_version_id"] is not None
                else None
            ),
        )

    def _chapters_for_book(self, connection: Connection, book_id: str) -> list[Chapter]:
        rows = connection.execute(
            sa.select(self._chapters)
            .join(self._volumes, self._volumes.c.id == self._chapters.c.volume_id)
            .where(self._volumes.c.book_id == book_id)
            .order_by(self._volumes.c.number, self._chapters.c.number)
        ).mappings()
        return [self._chapter_from_row(connection, row) for row in rows]

    def _metadata_for_connection(
        self, connection: Connection, metadata_id: str
    ) -> BookMetadataVersion:
        row = self._metadata_row(connection, metadata_id)
        if row is None:
            raise KeyError(metadata_id)
        tags = tuple(json.loads(str(row["tags_json"] or "[]")))
        return BookMetadataVersion(
            id=str(row["id"]),
            book_id=str(row["book_id"]),
            version=int(row["version"]),
            title=str(row["title"]),
            synopsis=str(row["synopsis"]),
            is_public=bool(row["is_public"]),
            channel=str(row["channel"]),
            category=str(row["category"]),
            tags=tags,
        )

    def _version_for_connection(self, connection: Connection, version_id: str) -> ChapterVersion:
        row = self._version_row(connection, version_id)
        if row is None:
            raise KeyError(version_id)
        return ChapterVersion(
            id=str(row["id"]),
            chapter_id=str(row["chapter_id"]),
            version=int(row["version"]),
            snapshot_id=str(row["snapshot_id"]),
            content=str(row["content"]),
            word_count=int(row["word_count"]),
        )

    def _book_row(self, connection: Connection, book_id: str) -> sa.RowMapping | None:
        return (
            connection.execute(sa.select(self._books).where(self._books.c.id == book_id))
            .mappings()
            .one_or_none()
        )

    def _metadata_row(self, connection: Connection, metadata_id: str) -> sa.RowMapping | None:
        columns: list[Any] = [
            self._metadata.c.id,
            self._metadata.c.book_id,
            self._metadata.c.version,
            self._metadata.c.title,
            self._metadata.c.synopsis,
            self._metadata.c.is_public,
        ]
        columns.extend(
            getattr(self._metadata.c, name)
            if name in self._metadata.c
            else sa.literal(default).label(name)
            for name, default in (
                ("channel", "UNSPECIFIED"),
                ("category", ""),
                ("tags_json", "[]"),
            )
        )
        return (
            connection.execute(sa.select(*columns).where(self._metadata.c.id == metadata_id))
            .mappings()
            .one_or_none()
        )

    def _snapshot_row(self, connection: Connection, snapshot_id: str) -> sa.RowMapping | None:
        return (
            connection.execute(
                sa.select(self._snapshots).where(self._snapshots.c.id == snapshot_id)
            )
            .mappings()
            .one_or_none()
        )

    def _version_row(self, connection: Connection, version_id: str) -> sa.RowMapping | None:
        return (
            connection.execute(sa.select(self._versions).where(self._versions.c.id == version_id))
            .mappings()
            .one_or_none()
        )

    def _require_book_row(self, connection: Connection, book_id: str) -> sa.RowMapping:
        row = self._book_row(connection, book_id)
        if row is None:
            raise KeyError(f"book {book_id} not found")
        return row

    def _require_volume_row(self, connection: Connection, volume_id: str) -> sa.RowMapping:
        row = (
            connection.execute(sa.select(self._volumes).where(self._volumes.c.id == volume_id))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError(f"volume {volume_id} not found")
        return row

    def _require_chapter_row(self, connection: Connection, chapter_id: str) -> sa.RowMapping:
        row = (
            connection.execute(sa.select(self._chapters).where(self._chapters.c.id == chapter_id))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError(f"chapter {chapter_id} not found")
        return row
