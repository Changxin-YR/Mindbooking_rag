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
