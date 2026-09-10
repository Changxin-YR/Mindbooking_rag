from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.governance.domain import ReconciliationDifference
from novel_platform.modules.governance.sql_service import SqlGovernanceService


def _engine() -> sa.Engine:
    metadata = sa.MetaData()
    sa.Table(
        "privacy_requests",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "agreement_acceptances",
        metadata,
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("agreement_code", sa.String(64), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "parameter_versions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("parameter_key", sa.String(128), nullable=False),
        sa.Column("value_text", sa.Text, nullable=False),
        sa.Column("maker_id", sa.String(64), nullable=False),
        sa.Column("checker_id", sa.String(64)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("effective_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "payment_credit_pending",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("payment_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, default=0),
        sa.Column("last_error", sa.Text),
        sa.Column("last_attempted_at", sa.DateTime),
        sa.Column("resolved_at", sa.DateTime),
        sa.Column("repair_actor_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "reconciliation_batches",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("business_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "reconciliation_items",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("batch_id", sa.String(64), nullable=False),
        sa.Column("reference", sa.String(128), nullable=False),
        sa.Column("difference", sa.String(32), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "platform_emergencies",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("features_json", sa.Text, nullable=False),
        sa.Column("operator_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "outbox_events",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "invoice_requests",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("tax_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("document_id", sa.String(128)),
        sa.Column("reversal_document_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    return engine


def test_sql_governance_reloads_idempotent_parameter_outbox_and_invoice_facts() -> None:
    engine = _engine()
    service = SqlGovernanceService(engine)
    privacy = service.open_privacy_request("acct-1", "EXPORT")
    assert service.open_privacy_request("acct-1", "EXPORT").id == privacy.id
    parameter = service.draft_parameter("vip.price", "199", "maker-1")
    service.approve_parameter(parameter.id, "checker-1")
    service.activate_parameter(parameter.id, "2026-09-04T00:00:00+00:00")
    event = service.enqueue_outbox("BOOK_TAKEN_DOWN", "book-1", {"visibility": "OFFLINE"})
    batch = service.open_reconciliation("2026-09-04")
    service.add_reconciliation_item(batch.id, "pay-1", ReconciliationDifference.DUPLICATE, 10)
    invoice = service.request_invoice("acct-1", 1990, "墨页科技", "91310000TEST")

    rebuilt = SqlGovernanceService(engine)

    assert rebuilt.outbox_event(event.id).payload == {"visibility": "OFFLINE"}
    assert rebuilt.reconciliation_batch(batch.id).items[0].amount_cents == 10
    assert rebuilt._parameters[parameter.id].status.value == "ACTIVE"
    assert rebuilt._invoices[invoice.id].status == "APPLIED"


def test_sql_reconciliation_batch_lifecycle_is_persisted_and_idempotent() -> None:
    engine = _engine()
    service = SqlGovernanceService(engine)
    batch = service.open_reconciliation("2026-09-05")
    assert service.mark_reconciliation_repaired(batch.id, "finance-1").status.value == "REPAIRED"
    assert service.close_reconciliation(batch.id, "finance-2").status.value == "CLOSED"
    rebuilt = SqlGovernanceService(engine)
    assert rebuilt.close_reconciliation(batch.id, "finance-3").status.value == "CLOSED"
    assert rebuilt.list_reconciliation_batches()[0].id == batch.id


def test_sql_credit_pending_repair_persists_success_and_failure_states() -> None:
    engine = _engine()
    service = SqlGovernanceService(engine)
    first = service.record_payment_credit_failure("pay-ok", "acct-1", 1000)
    calls: list[str] = []
    service.repair_payment_credit = lambda payment_id: calls.append(payment_id) or True

    repaired = service.retry_payment_credit(first.payment_id, "staff-1")
    assert repaired.status == "RESOLVED"
    assert repaired.attempts == 1
    assert calls == ["pay-ok"]
    assert SqlGovernanceService(engine).list_payment_credit_pending("RESOLVED")[0].resolved_at

    failed = service.record_payment_credit_failure("pay-fail", "acct-1", 1000)
    service.repair_payment_credit = lambda _: (_ for _ in ()).throw(RuntimeError("wallet down"))
    failed = service.retry_payment_credit(failed.payment_id, "staff-2")
    assert failed.status == "REPAIR_REQUIRED"
    assert failed.last_error == "wallet down"
    assert service.list_payment_credit_pending()[0].payment_id == "pay-fail"


def test_sql_credit_pending_stale_repairing_record_can_be_reclaimed() -> None:
    engine = _engine()
    service = SqlGovernanceService(engine)
    pending = service.record_payment_credit_failure("pay-stale", "acct-1", 1000)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE payment_credit_pending SET status='REPAIRING', "
                "last_attempted_at=:at WHERE payment_id=:payment_id"
            ),
            {"at": datetime.now(UTC) - timedelta(minutes=10), "payment_id": pending.payment_id},
        )
    service.repair_payment_credit = lambda _: True

    repaired = service.retry_payment_credit(pending.payment_id, "staff-reclaim")
    assert repaired.status == "RESOLVED"
    assert repaired.attempts == 1
