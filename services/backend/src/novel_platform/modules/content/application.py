from uuid import uuid4

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


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class ContentService:
    """In-memory content application port used until the persistence adapter is wired."""

    def __init__(self) -> None:
        self._books: dict[str, Book] = {}
        self._metadata: dict[str, BookMetadataVersion] = {}
        self._volumes: dict[str, Volume] = {}
        self._chapters: dict[str, Chapter] = {}
        self._snapshots: dict[str, DraftSnapshot] = {}
        self._versions: dict[str, ChapterVersion] = {}

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
        book.metadata_version_ids.append(metadata.id)
        self._books[book.id] = book
        self._metadata[metadata.id] = metadata
        return book

    def get_book(self, book_id: str) -> Book:
        try:
            return self._books[book_id]
        except KeyError as exc:
            raise KeyError(f"book {book_id} not found") from exc

    def get_book_metadata(self, book_id: str, public_only: bool = False) -> BookMetadataVersion:
        book = self.get_book(book_id)
        if public_only and book.public_metadata_version_id is None:
            raise KeyError(f"book {book_id} has no public metadata")
        metadata_id = book.public_metadata_version_id or book.metadata_version_ids[-1]
        return self._metadata[metadata_id]

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
        result: list[tuple[Book, BookMetadataVersion]] = []
        normalized_keyword = keyword.strip().casefold() if keyword else None
        for book in self._books.values():
            if book.visibility is not BookVisibility.PUBLIC:
                continue
            metadata = self.get_book_metadata(book.id, public_only=True)
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
                for chapter in self.list_chapters(book.id)
            ):
                continue
            result.append((book, metadata))
        return result

    def set_book_lifecycle(self, book_id: str, lifecycle: BookLifecycle) -> Book:
        book = self.get_book(book_id)
        book.lifecycle = lifecycle
        return book

    def set_book_visibility(self, book_id: str, visibility: BookVisibility) -> Book:
        book = self.get_book(book_id)
        book.visibility = visibility
        return book

    def create_metadata_version(
        self, book_id: str, title: str, synopsis: str = ""
    ) -> BookMetadataVersion:
        book = self.get_book(book_id)
        version = len(book.metadata_version_ids) + 1
        metadata = BookMetadataVersion(
            id=_id("BM"), book_id=book.id, version=version, title=title, synopsis=synopsis
        )
        book.metadata_version_ids.append(metadata.id)
        self._metadata[metadata.id] = metadata
        return metadata

    def publish_metadata_version(self, book_id: str, metadata_id: str) -> Book:
        book = self.get_book(book_id)
        metadata = self._metadata[metadata_id]
        if metadata.book_id != book.id:
            raise ValueError("metadata version does not belong to book")
        self._metadata[metadata_id] = BookMetadataVersion(
            id=metadata.id,
            book_id=metadata.book_id,
            version=metadata.version,
            title=metadata.title,
            synopsis=metadata.synopsis,
            is_public=True,
            channel=metadata.channel,
            category=metadata.category,
            tags=metadata.tags,
        )
        book.public_metadata_version_id = metadata_id
        return book

    def create_volume(self, book_id: str, title: str, number: int) -> Volume:
        self.get_book(book_id)
        if number < 1:
            raise ValueError("volume number must be positive")
        if any(
            volume.book_id == book_id and volume.number == number
            for volume in self._volumes.values()
        ):
            raise ValueError("volume number already exists")
        volume = Volume(id=_id("VOL"), book_id=book_id, number=number, title=title)
        self._volumes[volume.id] = volume
        return volume

    def get_volume(self, volume_id: str) -> Volume:
        try:
            return self._volumes[volume_id]
        except KeyError as exc:
            raise KeyError(f"volume {volume_id} not found") from exc

    def create_chapter(
        self,
        volume_id: str,
        title: str,
        commercial_policy: CommercialPolicy,
        number: int | None = None,
    ) -> Chapter:
        volume = self.get_volume(volume_id)
        if number is None:
            number = (
                sum(1 for chapter in self._chapters.values() if chapter.volume_id == volume_id) + 1
            )
        if number < 1:
            raise ValueError("chapter number must be positive")
        if any(
            chapter.volume_id == volume_id and chapter.number == number
            for chapter in self._chapters.values()
        ):
            raise ValueError("chapter number already exists")
        chapter = Chapter(
            id=_id("CH"),
            volume_id=volume.id,
            number=number,
            title=title,
            commercial_policy=commercial_policy,
        )
        self._chapters[chapter.id] = chapter
        return chapter

    def get_chapter(self, chapter_id: str) -> Chapter:
        try:
            return self._chapters[chapter_id]
        except KeyError as exc:
            raise KeyError(f"chapter {chapter_id} not found") from exc

    def save_draft(
        self,
        chapter_id: str,
        content: str,
        save_mode: str = "AUTO",
        expected_revision: int | None = None,
    ) -> DraftSnapshot:
        chapter = self.get_chapter(chapter_id)
        if expected_revision is not None and expected_revision != chapter.draft_revision:
            raise ValueError("draft revision conflict")
        chapter.draft_revision += 1
        snapshot = DraftSnapshot(
            id=_id("DS"),
            chapter_id=chapter.id,
            revision=chapter.draft_revision,
            content=content,
            save_mode=save_mode,
        )
        chapter.snapshot_ids.append(snapshot.id)
        self._snapshots[snapshot.id] = snapshot
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> DraftSnapshot:
        return self._snapshots[snapshot_id]

    def create_chapter_version(
        self, chapter_id: str, snapshot_id: str | None = None
    ) -> ChapterVersion:
        chapter = self.get_chapter(chapter_id)
        if snapshot_id is None:
            if not chapter.snapshot_ids:
                raise ValueError("chapter has no draft snapshot")
            snapshot_id = chapter.snapshot_ids[-1]
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot.chapter_id != chapter.id:
            raise ValueError("snapshot does not belong to chapter")
        version = ChapterVersion(
            id=_id("CV"),
            chapter_id=chapter.id,
            version=len(chapter.version_ids) + 1,
            snapshot_id=snapshot.id,
            content=snapshot.content,
            word_count=len(snapshot.content),
        )
        chapter.version_ids.append(version.id)
        self._versions[version.id] = version
        return version

    def get_chapter_version(self, version_id: str) -> ChapterVersion:
        return self._versions[version_id]

    def update_published_version(self, version_id: str, content: str) -> None:
        if version_id not in self._versions:
            raise KeyError(version_id)
        raise ValueError("published chapter version is immutable")

    def publish_chapter_version(self, chapter_id: str, version_id: str) -> Chapter:
        chapter = self.get_chapter(chapter_id)
        version = self.get_chapter_version(version_id)
        if version.chapter_id != chapter.id:
            raise ValueError("chapter version does not belong to chapter")
        chapter.published_version_id = version.id
        chapter.publish_state = PublishState.PUBLISHED
        chapter.visibility_state = VisibilityState.PUBLIC
        return chapter

    def publish_fixed_versions(
        self, book_id: str, version_ids: list[str] | tuple[str, ...]
    ) -> None:
        book = self.get_book(book_id)
        chapters: list[str] = []
        for version_id in version_ids:
            version = self.get_chapter_version(version_id)
            chapter = self.get_chapter(version.chapter_id)
            volume = self.get_volume(chapter.volume_id)
            if volume.book_id != book.id:
                raise ValueError("fixed chapter version does not belong to book")
            chapters.append(chapter.id)
        for chapter_id, version_id in zip(chapters, version_ids):
            self.publish_chapter_version(chapter_id, version_id)
        if book.public_metadata_version_id is None:
            self.publish_metadata_version(book.id, book.metadata_version_ids[0])
        book.lifecycle = BookLifecycle.SERIALIZING
        book.visibility = BookVisibility.PUBLIC

    def list_chapters(self, book_id: str) -> list[Chapter]:
        volume_ids = {volume.id for volume in self._volumes.values() if volume.book_id == book_id}
        return sorted(
            (chapter for chapter in self._chapters.values() if chapter.volume_id in volume_ids),
            key=lambda chapter: (self._volumes[chapter.volume_id].number, chapter.number),
        )

    def get_public_free_chapter(self, book_id: str, chapter_id: str) -> ChapterVersion:
        book = self.get_book(book_id)
        chapter = self.get_chapter(chapter_id)
        volume = self.get_volume(chapter.volume_id)
        if volume.book_id != book.id:
            raise KeyError(chapter_id)
        if book.visibility is not BookVisibility.PUBLIC:
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
        return self.get_chapter_version(chapter.published_version_id)

    def get_chapter_for_book(self, book_id: str, chapter_id: str) -> Chapter:
        chapter = self.get_chapter(chapter_id)
        volume = self.get_volume(chapter.volume_id)
        if volume.book_id != book_id:
            raise KeyError(chapter_id)
        return chapter
