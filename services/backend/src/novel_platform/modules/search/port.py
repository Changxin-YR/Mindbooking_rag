from typing import Protocol

from novel_platform.modules.search.domain import SearchQuery, SearchResultPage


class SearchPort(Protocol):
    def search(self, query: SearchQuery) -> SearchResultPage: ...
