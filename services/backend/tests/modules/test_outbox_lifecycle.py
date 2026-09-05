from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from test_sql_governance import _engine as governance_engine

from novel_platform.modules.governance.application import GovernanceService
from novel_platform.modules.governance.sql_service import SqlGovernanceService
from novel_platform.modules.governance.worker import OutboxWorker


def test_in_memory_outbox_claim_ack_and_retry_uses_a_lease() -> None:
    service = GovernanceService()
    event = service.enqueue_outbox("BOOK_INDEX", "book-1", {"title": "墨页"})
    now = datetime(2026, 9, 5, tzinfo=UTC)

    claimed = service.claim_outbox("worker-a", now=now)
    assert [item.id for item in claimed] == [event.id]
    assert service.claim_outbox("worker-b", now=now) == ()

    reclaimed = service.claim_outbox("worker-b", now=now + timedelta(seconds=61))
    assert reclaimed[0].id == event.id

    stale_event = service.enqueue_outbox("BOOK_INDEX", "book-2", {"title": "旧租约"})
    service.claim_outbox("worker-a", now=now)
    with pytest.raises(ValueError, match="OUTBOX_CLAIM_REQUIRED"):
        service.ack_outbox(stale_event.id, "worker-a", now=now + timedelta(seconds=61))

    failed = service.fail_outbox(event.id, "worker-b", "broker unavailable", now=now)
    assert failed.status == "FAILED"
    assert failed.attempts == 1
    assert service.claim_outbox("worker-b", now=now) == ()

    retried = service.claim_outbox("worker-b", now=now + timedelta(seconds=31), lease_seconds=60)
    assert retried[0].id == event.id
    published = service.ack_outbox(event.id, "worker-b", now=now + timedelta(seconds=32))
    assert published.status == "PUBLISHED"
    assert [
        item.id for item in service.claim_outbox("worker-c", now=now + timedelta(seconds=60))
    ] == [stale_event.id]

    dispatched = service.enqueue_outbox("BOOK_INDEX", "book-3", {"title": "投递"})
    seen: list[str] = []
    result = service.dispatch_outbox(
        "worker-d", lambda item: seen.append(item.id), limit=1, now=now
    )
    assert [item.id for item in result] == [dispatched.id]
    assert seen == [dispatched.id]
    assert service.outbox_event(dispatched.id).status == "PUBLISHED"


def test_sql_outbox_lifecycle_survives_service_reload() -> None:
    engine = governance_engine()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "ALTER TABLE outbox_events ADD COLUMN status VARCHAR(24) NOT NULL DEFAULT 'PENDING'"
            )
        )
        connection.execute(sa.text("ALTER TABLE outbox_events ADD COLUMN available_at DATETIME"))
        connection.execute(sa.text("ALTER TABLE outbox_events ADD COLUMN locked_by VARCHAR(128)"))
        connection.execute(sa.text("ALTER TABLE outbox_events ADD COLUMN locked_at DATETIME"))
        connection.execute(sa.text("ALTER TABLE outbox_events ADD COLUMN last_error TEXT"))
        connection.execute(sa.text("ALTER TABLE outbox_events ADD COLUMN processed_at DATETIME"))
    service = SqlGovernanceService(engine)
    event = service.enqueue_outbox("BOOK_INDEX", "book-1", {"title": "墨页"})

    assert service.claim_outbox("worker-a", now=datetime.now(UTC))[0].id == event.id
    service.ack_outbox(event.id, "worker-a")

    rebuilt = SqlGovernanceService(engine)
    assert rebuilt.outbox_event(event.id).status == "PUBLISHED"


def test_outbox_worker_retries_failed_handler_and_acknowledges_success() -> None:
    service = GovernanceService()
    event = service.enqueue_outbox("BOOK_INDEX", "book-1", {"title": "墨页"})
    now = datetime(2026, 9, 5, tzinfo=UTC)
    calls = 0

    def handle(item) -> None:
        nonlocal calls
        assert item.id == event.id
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary projection outage")

    worker = OutboxWorker(service, {"BOOK_INDEX": handle}, worker_id="projection-1")

    assert worker.run_once(now=now) == ()
    assert service.outbox_event(event.id).status.value == "FAILED"
    assert worker.run_once(now=now + timedelta(seconds=31)) == (service.outbox_event(event.id),)
    assert service.outbox_event(event.id).status.value == "PUBLISHED"
    assert calls == 2
