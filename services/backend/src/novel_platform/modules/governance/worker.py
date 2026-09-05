"""At-least-once DB outbox delivery through the application port."""

from collections.abc import Callable, Mapping
from datetime import datetime

from novel_platform.modules.governance.application import GovernanceService
from novel_platform.modules.governance.domain import OutboxEvent

OutboxHandler = Callable[[OutboxEvent], object]


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
