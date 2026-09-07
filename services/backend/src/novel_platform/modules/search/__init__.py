from novel_platform.modules.search.application import SearchService
from novel_platform.modules.search.domain import (
    BookSearchFact,
    SearchQuery,
    SearchResult,
    SearchResultPage,
    SearchSort,
)
from novel_platform.modules.search.port import SearchPort
from novel_platform.modules.search.repository import (
    InMemorySearchAdapter,
    InMemorySearchFactSource,
    InMemorySearchProjectionStore,
    OpenSearchSearchAdapter,
    RefreshingSearchAdapter,
    SearchProjectionPort,
)

__all__ = [
    "BookSearchFact",
    "InMemorySearchAdapter",
    "InMemorySearchFactSource",
    "InMemorySearchProjectionStore",
    "OpenSearchSearchAdapter",
    "RefreshingSearchAdapter",
    "SearchPort",
    "SearchProjectionPort",
    "SearchQuery",
    "SearchResult",
    "SearchResultPage",
    "SearchService",
    "SearchSort",
]
