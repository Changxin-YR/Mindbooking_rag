from novel_platform.modules.search.domain import SearchQuery, SearchResultPage
from novel_platform.modules.search.port import SearchPort


class SearchService:
    def __init__(self, search_port: SearchPort, *, fallback: SearchPort | None = None) -> None:
        self.search_port = search_port
        self.fallback = fallback

    def search(self, query: SearchQuery | None = None) -> SearchResultPage:
        query = query or SearchQuery()
        try:
            result = self.search_port.search(query)
        except RuntimeError:
            return self._fallback(query)
        if result.total:
            return result
        return self._fallback(query, primary=result)

    def _fallback(
        self, query: SearchQuery, *, primary: SearchResultPage | None = None
    ) -> SearchResultPage:
        if self.fallback is None:
            return primary or SearchResultPage.empty(query, degraded=True)
        try:
            result = self.fallback.search(query)
        except RuntimeError:
            return primary or SearchResultPage.empty(query, degraded=True)
        if primary is not None and not result.items:
            return primary
        return SearchResultPage(
            result.items,
            result.total,
            result.page,
            result.page_size,
            degraded=True,
        )
