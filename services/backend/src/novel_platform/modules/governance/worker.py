"""At-least-once DB outbox delivery through the application port."""

from collections.abc import Callable, Mapping
from datetime import datetime

from novel_platform.modules.governance.application import GovernanceService
from novel_platform.modules.governance.domain import OutboxEvent
from novel_platform.modules.search.domain import BookSearchFact
from novel_platform.modules.search.repository import SearchProjectionPort

OutboxHandler = Callable[[OutboxEvent], object]


def _strings(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key, ())
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _updated_at(value: object) -> datetime | int:
    if isinstance(value, datetime):
        return value
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("BOOK_INDEX_UPDATED_AT_INVALID") from exc
    return 0


def _integer(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key, 0)
    if isinstance(value, bool):
        raise TypeError(f"BOOK_INDEX_{key.upper()}_INVALID")
    if isinstance(value, (int, float)):
        return int(value)
    return 0


class SearchProjectionHandler:
    """Translate content outbox events into idempotent search projection calls."""

    def __init__(self, projection: SearchProjectionPort) -> None:
        self.projection = projection

    def __call__(self, event: OutboxEvent) -> None:
        if event.event_type == "BOOK_INDEX":
            self.projection.apply_book_index(event.id, self._fact(event))
            return
        if event.event_type == "BOOK_TAKEN_DOWN":
            if not event.aggregate_id.strip():
                raise ValueError("BOOK_TAKEN_DOWN_BOOK_ID_REQUIRED")
            self.projection.apply_book_taken_down(event.id, event.aggregate_id)
            return
        raise ValueError(f"SEARCH_PROJECTION_EVENT_UNSUPPORTED:{event.event_type}")

    handle = __call__

    def _fact(self, event: OutboxEvent) -> BookSearchFact:
        if not event.aggregate_id.strip() or not isinstance(event.payload, Mapping):
            raise ValueError("BOOK_INDEX_PAYLOAD_INVALID")
        payload = event.payload
        payload_book_id = payload.get("book_id")
        if payload_book_id is not None and payload_book_id != event.aggregate_id:
            raise ValueError("BOOK_INDEX_BOOK_ID_MISMATCH")
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("BOOK_INDEX_TITLE_REQUIRED")
        visibility = str(payload.get("visibility", "PUBLIC")).upper()
        is_public = payload.get("is_public", visibility in {"PUBLIC", "ONLINE"}) is True
        return BookSearchFact(
            book_id=event.aggregate_id,
            title=title,
            synopsis=str(payload.get("synopsis", "")),
            author_name=str(payload.get("author_name", "")),
            title_history=_strings(payload, "title_history"),
            author_name_history=_strings(payload, "author_name_history"),
            character_names=_strings(payload, "character_names"),
            tags=_strings(payload, "tags"),
            category=str(payload.get("category", "")),
            channel=str(payload.get("channel", "")),
            status=str(payload.get("status", "")),
            word_count=_integer(payload, "word_count"),
            popularity=_integer(payload, "popularity"),
            updated_at=_updated_at(payload.get("updated_at", 0)),
            is_public=is_public,
        )


class OutboxWorker:
    """Route claimed events and let the outbox port own retry state."""

    def __init__(
        self,
        governance: GovernanceService,
        handlers: Mapping[str, OutboxHandler],
        *,
        worker_id: str,
    ) -> None:
        self.governance = governance
        self.handlers = handlers
        self.worker_id = worker_id

    def run_once(
        self,
        *,
        limit: int = 10,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> tuple[OutboxEvent, ...]:
        def dispatch(event: OutboxEvent) -> object:
            handler = self.handlers.get(event.event_type)
            if handler is None:
                raise ValueError(f"OUTBOX_HANDLER_NOT_FOUND:{event.event_type}")
            return handler(event)

        return self.governance.dispatch_outbox(
            self.worker_id,
            dispatch,
            limit=limit,
            lease_seconds=lease_seconds,
            now=now,
        )
