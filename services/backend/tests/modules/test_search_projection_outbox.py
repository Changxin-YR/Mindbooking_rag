from novel_platform.modules.governance.application import GovernanceService
from novel_platform.modules.governance.worker import OutboxWorker, SearchProjectionHandler
from novel_platform.modules.search.domain import SearchQuery
from novel_platform.modules.search.repository import (
    InMemorySearchAdapter,
    InMemorySearchProjectionStore,
)


def test_outbox_search_projection_indexes_and_takes_down_idempotently() -> None:
    governance = GovernanceService()
    projection = InMemorySearchProjectionStore()
    handler = SearchProjectionHandler(projection)
    worker = OutboxWorker(
        governance,
        {
            "BOOK_INDEX": handler,
            "BOOK_TAKEN_DOWN": handler,
        },
        worker_id="search-projection",
    )

    indexed = governance.enqueue_outbox(
        "BOOK_INDEX",
        "book-1",
        {
            "title": "墨页",
            "synopsis": "公开作品",
            "is_public": True,
            "updated_at": 10,
        },
    )
    assert worker.run_once() == (governance.outbox_event(indexed.id),)
    assert worker.run_once() == ()

    result = InMemorySearchAdapter(projection).search(SearchQuery(query="墨页"))
    assert [item.book_id for item in result.items] == ["book-1"]

    taken_down = governance.enqueue_outbox("BOOK_TAKEN_DOWN", "book-1", {})
    assert worker.run_once() == (governance.outbox_event(taken_down.id),)
    assert handler(taken_down) is None
    assert InMemorySearchAdapter(projection).search(SearchQuery(query="墨页")).items == ()
