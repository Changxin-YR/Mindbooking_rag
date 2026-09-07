import json
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel_platform.modules.search.api import build_search_router
from novel_platform.modules.search.application import SearchService
from novel_platform.modules.search.domain import (
    BookSearchFact,
    SearchQuery,
    SearchResultPage,
    SearchSort,
)
from novel_platform.modules.search.repository import (
    InMemorySearchAdapter,
    InMemorySearchFactSource,
    OpenSearchSearchAdapter,
)


class _OpenSearchHandler(BaseHTTPRequestHandler):
    def _json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self) -> None:
        self.server.calls.append(self.path)  # type: ignore[attr-defined]
        self._json({})

    def do_POST(self) -> None:
        self.server.calls.append(self.path)  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if self.path.endswith("/_search"):
            self._json(
                {
                    "hits": {
                        "total": {"value": 1, "relation": "eq"},
                        "hits": [
                            {
                                "_source": {
                                    "book_id": "book-1",
                                    "title": "星河剑歌",
                                    "synopsis": "东方玄幻",
                                    "author_name": "云中客",
                                    "category": "东方玄幻",
                                    "channel": "MALE",
                                    "status": "SERIALIZING",
                                    "tags": ["玄幻"],
                                    "word_count": 1200,
                                    "popularity": 90,
                                    "updated_at": 30,
                                }
                            }
                        ],
                    }
                }
            )
            return
        self._json({"errors": False})

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def _facts() -> InMemorySearchFactSource:
    source = InMemorySearchFactSource()
    source.upsert(
        BookSearchFact(
            book_id="book-1",
            title="星河剑歌",
            synopsis="少年在东方玄幻世界中修行成长。",
            author_name="云中客",
            author_name_history=("旧云客",),
            character_names=("沈舟",),
            tags=("玄幻", "升级"),
            category="东方玄幻",
            channel="MALE",
            status="SERIALIZING",
            word_count=1_200_000,
            popularity=90,
            updated_at=30,
        )
    )
    source.upsert(
        BookSearchFact(
            book_id="book-2",
            title="星河旧梦",
            synopsis="一段关于星河的温柔故事。",
            author_name="青灯",
            tags=("言情",),
            category="现代言情",
            channel="FEMALE",
            status="COMPLETED",
            word_count=800_000,
            popularity=100,
            updated_at=20,
        )
    )
    book = source.get("book-1")
    assert book is not None
    source.upsert(replace(book, book_id="offline-book", title="不可见作品", is_public=False))
    return source


def test_search_matches_public_fact_fields_and_applies_filters_and_sort() -> None:
    service = SearchService(InMemorySearchAdapter(_facts()))

    result = service.search(
        SearchQuery(
            query="旧云客",
            channel="MALE",
            category="东方玄幻",
            status="SERIALIZING",
            tag="升级",
            sort=SearchSort.POPULARITY,
        )
    )

    assert result.total == 1
    assert [item.book_id for item in result.items] == ["book-1"]
    assert result.items[0].author_name == "云中客"


def test_search_sorts_and_paginates_without_exposing_private_facts() -> None:
    service = SearchService(InMemorySearchAdapter(_facts()))

    result = service.search(SearchQuery(query="星河", sort=SearchSort.UPDATED_AT, page_size=1))

    assert result.total == 2
    assert result.page == 1
    assert result.items[0].book_id == "book-1"
    assert all(item.book_id != "offline-book" for item in result.items)


def test_search_returns_safe_empty_page_when_nothing_matches() -> None:
    service = SearchService(InMemorySearchAdapter(_facts()))

    result = service.search(SearchQuery(query="不存在的词"))

    assert result.items == ()
    assert result.total == 0
    assert result.degraded is False


def test_search_applies_configured_typo_correction_and_synonym() -> None:
    adapter = InMemorySearchAdapter(
        _facts(),
        corrections={"星河劍歌": "星河剑歌"},
        synonyms={"仙侠": ("玄幻",)},
    )

    assert adapter.search(SearchQuery(query="星河劍歌")).total == 1
    assert adapter.search(SearchQuery(query="仙侠")).total == 1


def test_search_degrades_to_fact_source_when_search_port_is_unavailable() -> None:
    source = _facts()

    class UnavailableSearchPort:
        def search(self, query: SearchQuery) -> SearchResultPage:
            raise RuntimeError("search backend unavailable")

    service = SearchService(UnavailableSearchPort(), fallback=InMemorySearchAdapter(source))

    result = service.search(SearchQuery(query="星河"))

    assert result.degraded is True
    assert result.total == 2


def test_search_keeps_a_successful_empty_primary_result_non_degraded() -> None:
    source = InMemorySearchFactSource(())

    class EmptySearchPort:
        def search(self, query: SearchQuery) -> SearchResultPage:
            return SearchResultPage.empty(query)

    result = SearchService(EmptySearchPort(), fallback=InMemorySearchAdapter(source)).search()

    assert result.total == 0
    assert result.degraded is False


def test_opensearch_adapter_refreshes_projection_and_maps_hits() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OpenSearchHandler)
    server.calls = []
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        fact = _facts().get("book-1")
        assert fact is not None
        adapter = OpenSearchSearchAdapter(lambda: (fact,), f"http://127.0.0.1:{server.server_port}")
        result = adapter.search(SearchQuery(query="星河"))
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert result.total == 1
    assert result.items[0].book_id == "book-1"
    assert server.calls == [
        "/novel-books",
        "/novel-books/_delete_by_query?refresh=true",
        "/_bulk?refresh=wait_for",
        "/novel-books/_search",
    ]


def test_opensearch_adapter_does_not_rebuild_unchanged_projection() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OpenSearchHandler)
    server.calls = []
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        fact = _facts().get("book-1")
        assert fact is not None
        adapter = OpenSearchSearchAdapter(lambda: (fact,), f"http://127.0.0.1:{server.server_port}")
        adapter.search(SearchQuery(query="星河"))
        adapter.search(SearchQuery(query="剑歌"))
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert server.calls.count("/novel-books/_delete_by_query?refresh=true") == 1
    assert server.calls.count("/_bulk?refresh=wait_for") == 1
    assert server.calls.count("/novel-books/_search") == 2


def test_search_api_exposes_explicit_response_and_safe_empty_result() -> None:
    app = FastAPI()
    app.include_router(build_search_router(SearchService(InMemorySearchAdapter(_facts()))))
    client = TestClient(app)

    response = client.get(
        "/api/v1/search",
        params={"q": "星河", "channel": "FEMALE", "sort": "popularity"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "book_id": "book-2",
                "title": "星河旧梦",
                "synopsis": "一段关于星河的温柔故事。",
                "author_name": "青灯",
                "category": "现代言情",
                "channel": "FEMALE",
                "status": "COMPLETED",
                "tags": ["言情"],
                "word_count": 800000,
                "popularity": 100,
                "updated_at": 20,
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 20,
        "degraded": False,
    }

    empty = client.get("/api/v1/search", params={"q": "没有这本书"})
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert empty.json()["total"] == 0

    invalid_range = client.get(
        "/api/v1/search", params={"min_word_count": 100, "max_word_count": 10}
    )
    assert invalid_range.status_code == 422
    assert invalid_range.json()["detail"]["code"] == "INVALID_WORD_COUNT_RANGE"
