from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SearchSort(StrEnum):
    RELEVANCE = "relevance"
    UPDATED_AT = "updated_at"
    POPULARITY = "popularity"
    WORD_COUNT = "word_count"
    TITLE = "title"


@dataclass(frozen=True, slots=True)
class BookSearchFact:
    book_id: str
    title: str
    synopsis: str = ""
    author_name: str = ""
    title_history: tuple[str, ...] = ()
    author_name_history: tuple[str, ...] = ()
    character_names: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    category: str = ""
    channel: str = ""
    status: str = ""
    word_count: int = 0
    popularity: int = 0
    updated_at: datetime | int = 0
    is_public: bool = True


@dataclass(frozen=True, slots=True)
class SearchQuery:
    query: str = ""
    channel: str | None = None
    category: str | None = None
    status: str | None = None
    tag: str | None = None
    min_word_count: int | None = None
    max_word_count: int | None = None
    sort: SearchSort = SearchSort.RELEVANCE
    page: int = 1
    page_size: int = 20

    def __post_init__(self) -> None:
        if self.page < 1 or self.page_size < 1:
            raise ValueError("page and page_size must be positive")
        if self.min_word_count is not None and self.min_word_count < 0:
            raise ValueError("min_word_count must be non-negative")
        if self.max_word_count is not None and self.max_word_count < 0:
            raise ValueError("max_word_count must be non-negative")
        if (
            self.min_word_count is not None
            and self.max_word_count is not None
            and self.min_word_count > self.max_word_count
        ):
            raise ValueError("min_word_count cannot exceed max_word_count")
        object.__setattr__(self, "sort", SearchSort(self.sort))


@dataclass(frozen=True, slots=True)
class SearchResult:
    book_id: str
    title: str
    synopsis: str
    author_name: str
    category: str
    channel: str
    status: str
    tags: tuple[str, ...]
    word_count: int
    popularity: int
    updated_at: datetime | int

    @classmethod
    def from_fact(cls, fact: BookSearchFact) -> SearchResult:
        return cls(
            book_id=fact.book_id,
            title=fact.title,
            synopsis=fact.synopsis,
            author_name=fact.author_name,
            category=fact.category,
            channel=fact.channel,
            status=fact.status,
            tags=fact.tags,
            word_count=fact.word_count,
            popularity=fact.popularity,
            updated_at=fact.updated_at,
        )


@dataclass(frozen=True, slots=True)
class SearchResultPage:
    items: tuple[SearchResult, ...]
    total: int
    page: int
    page_size: int
    degraded: bool = False

    @classmethod
    def empty(cls, query: SearchQuery, *, degraded: bool = False) -> SearchResultPage:
        return cls((), 0, query.page, query.page_size, degraded)
