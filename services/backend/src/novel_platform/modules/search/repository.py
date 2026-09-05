import json
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from threading import RLock
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from novel_platform.modules.search.domain import (
    BookSearchFact,
    SearchQuery,
    SearchResult,
    SearchResultPage,
    SearchSort,
)
from novel_platform.modules.search.port import SearchPort


def _normalized(value: str) -> str:
    return "".join(value.split()).casefold()


def _sortable_time(value: datetime | int) -> float | int:
    return value.timestamp() if isinstance(value, datetime) else value


class SearchProjectionPort(Protocol):
    """Application port for applying public content events to a search projection."""

    def apply_book_index(self, event_id: str, fact: BookSearchFact) -> None: ...

    def apply_book_taken_down(self, event_id: str, book_id: str) -> None: ...


class InMemorySearchFactSource:
    """In-memory stand-in for the public content fact source."""

    def __init__(self, facts: Iterable[BookSearchFact] = ()) -> None:
        self._lock = RLock()
        self._facts: dict[str, BookSearchFact] = {}
        for fact in facts:
            self.upsert(fact)

    def upsert(self, fact: BookSearchFact) -> None:
        if not fact.book_id:
            raise ValueError("book_id is required")
        with self._lock:
            self._facts[fact.book_id] = fact

    add = upsert

    def get(self, book_id: str) -> BookSearchFact | None:
        with self._lock:
            return self._facts.get(book_id)

    def all(self) -> tuple[BookSearchFact, ...]:
        with self._lock:
            return tuple(self._facts.values())


class InMemorySearchProjectionStore(InMemorySearchFactSource):
    """Small projection store with event-level idempotency for local workers."""

    def __init__(self, facts: Iterable[BookSearchFact] = ()) -> None:
        super().__init__(facts)
        self._processed_events: set[str] = set()

    def remove(self, book_id: str) -> None:
        with self._lock:
            self._facts.pop(book_id, None)

    def apply_book_index(self, event_id: str, fact: BookSearchFact) -> None:
        self._apply_once(event_id, lambda: self._index(fact))

    def apply_book_taken_down(self, event_id: str, book_id: str) -> None:
        self._apply_once(event_id, lambda: self.remove(book_id))

    def _index(self, fact: BookSearchFact) -> None:
        if fact.is_public:
            self.upsert(fact)
        else:
            self.remove(fact.book_id)

    def _apply_once(self, event_id: str, operation: Callable[[], None]) -> None:
        if not event_id.strip():
            raise ValueError("SEARCH_PROJECTION_EVENT_ID_REQUIRED")
        with self._lock:
            if event_id in self._processed_events:
                return
            operation()
            self._processed_events.add(event_id)


class InMemorySearchAdapter(SearchPort):
    def __init__(
        self,
        source: InMemorySearchFactSource,
        *,
        corrections: Mapping[str, str] | None = None,
        synonyms: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        self.source = source
        self.corrections = {
            _normalized(key): _normalized(value) for key, value in (corrections or {}).items()
        }
        self.synonyms = {
            _normalized(key): tuple(_normalized(value) for value in values)
            for key, values in (synonyms or {}).items()
        }

    def search(self, query: SearchQuery) -> SearchResultPage:
        terms = self._terms(query.query)
        matches = [
            fact
            for fact in self.source.all()
            if fact.is_public and self._matches(fact, query, terms)
        ]
        matches.sort(key=lambda fact: self._sort_key(fact, query, terms))
        start = (query.page - 1) * query.page_size
        return SearchResultPage(
            tuple(
                SearchResult.from_fact(fact) for fact in matches[start : start + query.page_size]
            ),
            len(matches),
            query.page,
            query.page_size,
        )

    def _terms(self, value: str) -> tuple[str, ...]:
        term = _normalized(value)
        if not term:
            return ()
        corrected = self.corrections.get(term, term)
        return tuple(dict.fromkeys((term, corrected, *self.synonyms.get(corrected, ()))))

    def _matches(self, fact: BookSearchFact, query: SearchQuery, terms: tuple[str, ...]) -> bool:
        if query.channel is not None and _normalized(fact.channel) != _normalized(query.channel):
            return False
        if query.category is not None and _normalized(fact.category) != _normalized(query.category):
            return False
        if query.status is not None and _normalized(fact.status) != _normalized(query.status):
            return False
        if query.tag is not None and not any(
            _normalized(query.tag) == _normalized(tag) for tag in fact.tags
        ):
            return False
        if query.min_word_count is not None and fact.word_count < query.min_word_count:
            return False
        if query.max_word_count is not None and fact.word_count > query.max_word_count:
            return False
        if not terms:
            return True
        return any(term in field for term in terms for field in self._search_fields(fact))

    def _search_fields(self, fact: BookSearchFact) -> tuple[str, ...]:
        return tuple(
            _normalized(value)
            for value in (
                fact.title,
                *fact.title_history,
                fact.author_name,
                *fact.author_name_history,
                *fact.character_names,
                *fact.tags,
                fact.category,
                fact.synopsis,
            )
        )

    def _sort_key(
        self, fact: BookSearchFact, query: SearchQuery, terms: tuple[str, ...]
    ) -> tuple[object, ...]:
        if query.sort is SearchSort.RELEVANCE:
            return (-self._relevance(fact, terms), fact.book_id)
        if query.sort is SearchSort.UPDATED_AT:
            return (-_sortable_time(fact.updated_at), fact.book_id)
        if query.sort is SearchSort.POPULARITY:
            return (-fact.popularity, fact.book_id)
        if query.sort is SearchSort.WORD_COUNT:
            return (-fact.word_count, fact.book_id)
        return (_normalized(fact.title), fact.book_id)

    def _relevance(self, fact: BookSearchFact, terms: tuple[str, ...]) -> int:
        if not terms:
            return 0
        fields = (
            ((fact.title,), 8),
            (fact.title_history, 7),
            ((fact.author_name,), 6),
            (fact.author_name_history, 5),
            (fact.character_names, 4),
            (fact.tags, 3),
            ((fact.category,), 2),
            ((fact.synopsis,), 1),
        )
        return max(
            (
                weight * (2 if _normalized(value) == term else 1)
                for values, weight in fields
                for value in values
                for term in terms
                if term in _normalized(value)
            ),
            default=0,
        )


class RefreshingSearchAdapter(SearchPort):
    """Rebuild the search projection from the current domain facts per query."""

    def __init__(self, facts: Callable[[], Iterable[BookSearchFact]]) -> None:
        self._facts = facts

    def search(self, query: SearchQuery) -> SearchResultPage:
        return InMemorySearchAdapter(InMemorySearchFactSource(self._facts())).search(query)


class OpenSearchSearchAdapter(SearchPort):
    """OpenSearch projection with the in-memory adapter as the failure fallback."""

    _SEARCH_FIELDS = (
        "title",
        "title_history",
        "author_name",
        "author_name_history",
        "character_names",
        "tags",
        "category",
        "synopsis",
    )

    def __init__(
        self,
        facts: Callable[[], Iterable[BookSearchFact]],
        base_url: str,
        *,
        index: str = "novel-books",
        timeout: float = 2.0,
    ) -> None:
        self._facts = facts
        self._base_url = base_url.rstrip("/")
        self._index = index
        self._timeout = timeout
        self._index_ready = False

    def search(self, query: SearchQuery) -> SearchResultPage:
        facts = tuple(fact for fact in self._facts() if fact.is_public)
        # ponytail: rebuild the small projection per request; replace with outbox-driven indexing at scale.
        self._ensure_index()
        self._replace_projection(facts)
        filters: list[dict[str, object]] = []
        for field, value in (
            ("channel", query.channel),
            ("category", query.category),
            ("status", query.status),
        ):
            if value is not None:
                filters.append({"term": {f"{field}.keyword": value}})
        if query.tag is not None:
            filters.append({"term": {"tags.keyword": query.tag}})
        if query.min_word_count is not None or query.max_word_count is not None:
            range_query: dict[str, int] = {}
            if query.min_word_count is not None:
                range_query["gte"] = query.min_word_count
            if query.max_word_count is not None:
                range_query["lte"] = query.max_word_count
            filters.append({"range": {"word_count": range_query}})

        must: list[dict[str, object]] = []
        if query.query.strip():
            must.append(
                {
                    "multi_match": {
                        "query": query.query,
                        "fields": list(self._SEARCH_FIELDS),
                        "type": "best_fields",
                    }
                }
            )
        else:
            must.append({"match_all": {}})
        sort = self._sort(query)
        payload = {
            "from": (query.page - 1) * query.page_size,
            "size": query.page_size,
            "track_total_hits": True,
            "query": {"bool": {"must": must, "filter": filters}},
            "sort": sort,
        }
        response = self._request("POST", f"/{self._index}/_search", payload)
        hits_value = response.get("hits", {})
        if not isinstance(hits_value, Mapping):
            raise TypeError("OpenSearch returned invalid hits")
        hits = hits_value
        total_value = hits.get("total", 0)
        if isinstance(total_value, Mapping):
            total_value = total_value.get("value", 0)
        total = int(total_value) if isinstance(total_value, (int, float)) else 0
        raw_hits = hits.get("hits", [])
        if not isinstance(raw_hits, list):
            raise TypeError("OpenSearch returned invalid hit list")
        items = tuple(
            self._result(source)
            for hit in raw_hits
            if isinstance(hit, Mapping)
            for source in [hit.get("_source", {})]
            if isinstance(source, Mapping)
        )
        return SearchResultPage(items, total, query.page, query.page_size)

    def _sort(self, query: SearchQuery) -> list[dict[str, object]]:
        if query.sort is SearchSort.UPDATED_AT:
            return [{"updated_at_sort": "desc"}, {"book_id": "asc"}]
        if query.sort is SearchSort.POPULARITY:
            return [{"popularity": "desc"}, {"book_id": "asc"}]
        if query.sort is SearchSort.WORD_COUNT:
            return [{"word_count": "desc"}, {"book_id": "asc"}]
        if query.sort is SearchSort.TITLE:
            return [{"title.keyword": "asc"}, {"book_id": "asc"}]
        return [{"_score": "desc"}, {"book_id": "asc"}]

    def _ensure_index(self) -> None:
        if self._index_ready:
            return
        try:
            self._request(
                "PUT",
                f"/{self._index}",
                {
                    "mappings": {
                        "properties": {
                            "book_id": {"type": "keyword"},
                            "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                            "title_history": {"type": "text"},
                            "author_name": {
                                "type": "text",
                                "fields": {"keyword": {"type": "keyword"}},
                            },
                            "author_name_history": {"type": "text"},
                            "character_names": {"type": "text"},
                            "tags": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                            "category": {
                                "type": "text",
                                "fields": {"keyword": {"type": "keyword"}},
                            },
                            "channel": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                            "status": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                            "synopsis": {"type": "text"},
                            "word_count": {"type": "integer"},
                            "popularity": {"type": "integer"},
                            "updated_at_sort": {"type": "double"},
                            "updated_at": {"type": "double"},
                        }
                    }
                },
            )
            self._index_ready = True
        except RuntimeError as exc:
            if "resource_already_exists_exception" in str(exc):
                self._index_ready = True
                return
            raise

    def _replace_projection(self, facts: tuple[BookSearchFact, ...]) -> None:
        self._request(
            "POST",
            f"/{self._index}/_delete_by_query?refresh=true",
            {"query": {"match_all": {}}},
        )
        lines: list[str] = []
        for fact in facts:
            lines.append(json.dumps({"index": {"_index": self._index, "_id": fact.book_id}}))
            lines.append(json.dumps(self._document(fact)))
        if lines:
            self._request(
                "POST",
                "/_bulk?refresh=wait_for",
                "\n".join(lines) + "\n",
                content_type="application/x-ndjson",
            )

    def _document(self, fact: BookSearchFact) -> dict[str, object]:
        updated_at = _sortable_time(fact.updated_at)
        return {
            "book_id": fact.book_id,
            "title": fact.title,
            "synopsis": fact.synopsis,
            "author_name": fact.author_name,
            "title_history": list(fact.title_history),
            "author_name_history": list(fact.author_name_history),
            "character_names": list(fact.character_names),
            "tags": list(fact.tags),
            "category": fact.category,
            "channel": fact.channel,
            "status": fact.status,
            "word_count": fact.word_count,
            "popularity": fact.popularity,
            "updated_at_sort": float(updated_at),
            "updated_at": float(updated_at),
        }

    def _result(self, source: Mapping[str, object]) -> SearchResult:
        updated_at_value = source.get("updated_at", 0)
        updated_at: datetime | int = (
            int(updated_at_value) if isinstance(updated_at_value, (int, float)) else 0
        )
        tags_value = source.get("tags", [])
        tags = (
            tuple(tag for tag in tags_value if isinstance(tag, str))
            if isinstance(tags_value, list)
            else ()
        )
        word_count_value = source.get("word_count", 0)
        popularity_value = source.get("popularity", 0)
        return SearchResult(
            book_id=str(source.get("book_id", "")),
            title=str(source.get("title", "")),
            synopsis=str(source.get("synopsis", "")),
            author_name=str(source.get("author_name", "")),
            category=str(source.get("category", "")),
            channel=str(source.get("channel", "")),
            status=str(source.get("status", "")),
            tags=tags,
            word_count=int(word_count_value) if isinstance(word_count_value, (int, float)) else 0,
            popularity=int(popularity_value) if isinstance(popularity_value, (int, float)) else 0,
            updated_at=updated_at,
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | str,
        *,
        content_type: str = "application/json",
    ) -> dict[str, object]:
        body = payload if isinstance(payload, str) else json.dumps(payload)
        request = Request(
            f"{self._base_url}{path}",
            data=body.encode("utf-8"),
            headers={"Content-Type": content_type},
            method=method,
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            try:
                error_body = json.loads(exc.read().decode("utf-8"))
            except OSError, json.JSONDecodeError:
                error_body = str(exc)
            raise RuntimeError(str(error_body)) from exc
        except (OSError, URLError) as exc:
            raise RuntimeError(f"OpenSearch unavailable: {exc}") from exc
        try:
            decoded = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenSearch returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise TypeError("OpenSearch returned an invalid response")
        if decoded.get("errors") is True or decoded.get("error"):
            raise RuntimeError(str(decoded.get("error", "OpenSearch request failed")))
        return decoded
