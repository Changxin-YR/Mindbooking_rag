import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.commerce.refund import RefundSourceSnapshot
from novel_platform.modules.commerce.sql_refund import SqlRefundService


def _engine() -> sa.Engine:
    metadata = sa.MetaData()
    snapshots = sa.Table(
        "refund_calculation_snapshots",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("refund_reference", sa.String(128), nullable=False, unique=True),
        sa.Column("payment_no", sa.String(64), nullable=False),
        sa.Column("recharge_no", sa.String(64), nullable=False),
        sa.Column("original_paid_cents", sa.BigInteger, nullable=False),
        sa.Column("consumed_recharge_coin", sa.BigInteger, nullable=False),
        sa.Column("consumed_promo_gift_coin", sa.BigInteger, nullable=False),
        sa.Column("naturally_expired_promo_gift_coin", sa.BigInteger, nullable=False),
        sa.Column("prior_refunded_cents", sa.BigInteger, nullable=False),
        sa.Column("refundable_cents", sa.BigInteger, nullable=False),
        sa.Column("recoverable_recharge_coin", sa.BigInteger, nullable=False),
        sa.Column("recoverable_promo_gift_coin", sa.BigInteger, nullable=False),
        sa.Column("executed", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "refund_requests",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("refund_no", sa.String(64), nullable=False, unique=True),
        sa.Column("refund_reference", sa.String(128), nullable=False, unique=True),
        sa.Column("payment_no", sa.String(64), nullable=False),
        sa.Column("recharge_no", sa.String(64), nullable=False),
        sa.Column("snapshot_id", sa.Integer, sa.ForeignKey(snapshots.c.id), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "refund_source_locks",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("payment_no", sa.String(64), nullable=False),
        sa.Column("recharge_no", sa.String(64), nullable=False),
        sa.Column("refund_reference", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("payment_no", "recharge_no"),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    return engine


def _source() -> RefundSourceSnapshot:
    return RefundSourceSnapshot("PAY-1", "RECH-1", 10_000, 0, 500, 0, 0, 10_000, 500)


def test_sql_refund_is_durable_idempotent_and_accumulates_prior_refunds() -> None:
    engine = _engine()
    recovered: list[int] = []
    service = SqlRefundService(
        engine,
        lambda payment_no, recharge_no: _source(),
        lambda snapshot: recovered.append(snapshot.refundable_cents),
        lambda payment_no, recharge_no: "account-1",
    )

    first = service.refund("PAY-1", "RECH-1", "REF-1")
    rebuilt = SqlRefundService(
        engine,
        lambda payment_no, recharge_no: _source(),
        lambda snapshot: recovered.append(snapshot.refundable_cents),
        lambda payment_no, recharge_no: "account-1",
    )
    assert rebuilt.refund("PAY-1", "RECH-1", "REF-1") == first
    second = rebuilt.refund("PAY-1", "RECH-1", "REF-2")

    assert first.refundable_cents == 9_500
    assert second.prior_refunded_cents == 9_500
    assert second.refundable_cents == 0
    assert recovered == [9_500]
    with engine.begin() as connection:
        assert (
            connection.execute(
                sa.text("SELECT COUNT(*) FROM refund_calculation_snapshots")
            ).scalar_one()
            == 2
        )
        assert connection.execute(sa.text("SELECT COUNT(*) FROM refund_requests")).scalar_one() == 2


def test_sql_refund_rolls_back_snapshot_when_asset_recovery_fails() -> None:
    engine = _engine()

    def fail(snapshot: object) -> None:
        raise RuntimeError("wallet unavailable")

    service = SqlRefundService(engine, lambda payment_no, recharge_no: _source(), fail)
    with pytest.raises(RuntimeError, match="wallet unavailable"):
        service.refund("PAY-1", "RECH-1", "REF-1")
    with engine.begin() as connection:
        assert (
            connection.execute(
                sa.text("SELECT COUNT(*) FROM refund_calculation_snapshots")
            ).scalar_one()
            == 0
        )
        assert connection.execute(sa.text("SELECT COUNT(*) FROM refund_requests")).scalar_one() == 0
