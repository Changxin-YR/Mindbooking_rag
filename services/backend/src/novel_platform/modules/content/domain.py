from dataclasses import dataclass, field
from enum import StrEnum


class BookLifecycle(StrEnum):
    DRAFT = "DRAFT"
    SERIALIZING = "SERIALIZING"
    PAUSED = "PAUSED"
    COMPLETION_PENDING = "COMPLETION_PENDING"
    COMPLETED = "COMPLETED"


class BookVisibility(StrEnum):
    PRIVATE = "PRIVATE"
    PENDING_FIRST_REVIEW = "PENDING_FIRST_REVIEW"
    PUBLIC = "PUBLIC"
    TEMP_OFFLINE = "TEMP_OFFLINE"
    PERMANENT_OFFLINE = "PERMANENT_OFFLINE"


class PublishState(StrEnum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"


class VisibilityState(StrEnum):
    PRIVATE = "PRIVATE"
    PUBLIC = "PUBLIC"
    TEMP_OFFLINE = "TEMP_OFFLINE"
    PERMANENT_OFFLINE = "PERMANENT_OFFLINE"


class CommercialPolicy(StrEnum):
    FREE = "FREE"
    VIP = "VIP"


@dataclass(frozen=True, slots=True)
class BookMetadataVersion:
    id: str
    book_id: str
    version: int
    title: str
    synopsis: str
    is_public: bool = False
    channel: str = "UNSPECIFIED"
    category: str = ""
    tags: tuple[str, ...] = ()


@dataclass(slots=True)
class Book:
    id: str
    author_id: str
    lifecycle: BookLifecycle = BookLifecycle.DRAFT
    visibility: BookVisibility = BookVisibility.PRIVATE
    public_metadata_version_id: str | None = None
    metadata_version_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Volume:
    id: str
    book_id: str
    number: int
    title: str


@dataclass(slots=True)
class Chapter:
    id: str
    volume_id: str
    number: int
    title: str
    commercial_policy: CommercialPolicy
    publish_state: PublishState = PublishState.DRAFT
    visibility_state: VisibilityState = VisibilityState.PRIVATE
    draft_revision: int = 0
    snapshot_ids: list[str] = field(default_factory=list)
    version_ids: list[str] = field(default_factory=list)
    published_version_id: str | None = None


def is_readable_chapter(chapter: Chapter) -> bool:
    return chapter.published_version_id is not None and chapter.title != "作品简介与来源"


@dataclass(frozen=True, slots=True)
class DraftSnapshot:
    id: str
    chapter_id: str
    revision: int
    content: str
    save_mode: str


@dataclass(frozen=True, slots=True)
class ChapterVersion:
    id: str
    chapter_id: str
    version: int
    snapshot_id: str
    content: str
    word_count: int
