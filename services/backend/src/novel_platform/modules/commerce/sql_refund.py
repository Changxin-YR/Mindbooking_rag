"""Durable refund calculation and execution boundary."""

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from novel_platform.modules.commerce.refund import (
    AssetRecovery,
    RefundCalculationSnapshot,
    RefundService,
    SourceLookup,
    calculate_refund,
)


class SqlRefundService(RefundService):
    def __init__(
        self,
        engine: Engine,
        source_lookup: SourceLookup,
        recover_assets: AssetRecovery,
        account_lookup: Any | None = None,
        recover_assets_in_connection: Any | None = None,
        source_lookup_in_connection: Any | None = None,
    ) -> None:
        super().__init__(source_lookup, recover_assets, account_lookup)
        self.engine = engine
        self._recover_assets_in_connection = recover_assets_in_connection
        self._source_lookup_in_connection = source_lookup_in_connection
        metadata = sa.MetaData()
        self._snapshots: Any = sa.Table(
            "refund_calculation_snapshots", metadata, autoload_with=engine
        )
        self._requests: Any = sa.Table("refund_requests", metadata, autoload_with=engine)
        self._source_locks: Any = sa.Table("refund_source_locks", metadata, autoload_with=engine)

    def refund(
        self, payment_no: str, recharge_no: str, refund_reference: str
    ) -> RefundCalculationSnapshot:
        for value, name in (
            (payment_no, "payment_no"),
            (recharge_no, "recharge_no"),
            (refund_reference, "refund_reference"),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} is required")

        with self._lock, self.engine.begin() as connection:
            existing = (
                connection.execute(
                    sa.select(self._snapshots)
                    .where(self._snapshots.c.refund_reference == refund_reference)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if (existing["payment_no"], existing["recharge_no"]) != (
                    payment_no,
                    recharge_no,
                ):
                    raise ValueError("REFUND_REFERENCE_CONFLICT")
                return self._snapshot_from_row(existing)

            self._lock_source(connection, payment_no, recharge_no, refund_reference)
            source = (
                self._source_lookup_in_connection(connection, payment_no, recharge_no)
                if self._source_lookup_in_connection is not None
                else self._source_lookup(payment_no, recharge_no)
            )
            if (source.payment_no, source.recharge_no) != (payment_no, recharge_no):
                raise ValueError("REFUND_SOURCE_MISMATCH")
            prior = connection.execute(
                sa.select(
                    sa.func.coalesce(sa.func.sum(self._snapshots.c.refundable_cents), 0)
                ).where(
                    self._snapshots.c.payment_no == payment_no,
                    self._snapshots.c.recharge_no == recharge_no,
                )
            ).scalar_one()
            source = replace(source, prior_refunded_cents=source.prior_refunded_cents + int(prior))
            calculation = calculate_refund(source, refund_reference)
            if calculation.refundable_cents > 0:
                calculation = replace(calculation, executed=True)
            result = connection.execute(
                self._snapshots.insert().values(
                    refund_reference=calculation.refund_reference,
                    payment_no=calculation.payment_no,
                    recharge_no=calculation.recharge_no,
                    original_paid_cents=calculation.original_paid_cents,
                    consumed_recharge_coin=calculation.consumed_recharge_coin,
                    consumed_promo_gift_coin=calculation.consumed_promo_gift_coin,
                    naturally_expired_promo_gift_coin=calculation.naturally_expired_promo_gift_coin,
                    prior_refunded_cents=calculation.prior_refunded_cents,
                    refundable_cents=calculation.refundable_cents,
                    recoverable_recharge_coin=calculation.recoverable_recharge_coin,
                    recoverable_promo_gift_coin=calculation.recoverable_promo_gift_coin,
                    executed=calculation.executed,
                    created_at=datetime.now(UTC),
                )
            )
            inserted_primary_key = result.inserted_primary_key
            if inserted_primary_key is None:
                raise RuntimeError("refund snapshot primary key was not created")
            snapshot_id = inserted_primary_key[0]
            if calculation.executed:
                if self._recover_assets_in_connection is not None:
                    self._recover_assets_in_connection(connection, calculation)
                else:
                    self._recover_assets(calculation)
            connection.execute(
                self._requests.insert().values(
                    refund_no=self._refund_no(refund_reference),
                    refund_reference=refund_reference,
                    payment_no=payment_no,
                    recharge_no=recharge_no,
                    snapshot_id=snapshot_id,
                    status="EXECUTED" if calculation.executed else "NO_REFUND",
                    created_at=datetime.now(UTC),
                )
            )
            connection.execute(
                self._source_locks.update()
                .where(
                    self._source_locks.c.payment_no == payment_no,
                    self._source_locks.c.recharge_no == recharge_no,
                )
                .values(status="COMPLETED")
            )
            return calculation

    def _lock_source(
        self, connection: Connection, payment_no: str, recharge_no: str, refund_reference: str
    ) -> None:
        row = (
            connection.execute(
                sa.select(self._source_locks)
                .where(
                    self._source_locks.c.payment_no == payment_no,
                    self._source_locks.c.recharge_no == recharge_no,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is not None:
            return
        try:
            with connection.begin_nested():
                connection.execute(
                    self._source_locks.insert().values(
                        payment_no=payment_no,
                        recharge_no=recharge_no,
                        refund_reference=refund_reference,
                        status="PROCESSING",
                        created_at=datetime.now(UTC),
                    )
                )
        except IntegrityError:
            pass
        if (
            connection.execute(
                sa.select(self._source_locks.c.id).where(
                    self._source_locks.c.payment_no == payment_no,
                    self._source_locks.c.recharge_no == recharge_no,
                )
            ).scalar_one_or_none()
            is None
        ):
            raise RuntimeError("refund source lock was not created")

    @staticmethod
    def _refund_no(refund_reference: str) -> str:
        return f"REF-{sha256(refund_reference.encode('utf-8')).hexdigest()[:56]}"

    @staticmethod
    def _snapshot_from_row(row: sa.RowMapping) -> RefundCalculationSnapshot:
        return RefundCalculationSnapshot(
            payment_no=str(row["payment_no"]),
            recharge_no=str(row["recharge_no"]),
            refund_reference=str(row["refund_reference"]),
            original_paid_cents=int(row["original_paid_cents"]),
            consumed_recharge_coin=int(row["consumed_recharge_coin"]),
            consumed_promo_gift_coin=int(row["consumed_promo_gift_coin"]),
            naturally_expired_promo_gift_coin=int(row["naturally_expired_promo_gift_coin"]),
            prior_refunded_cents=int(row["prior_refunded_cents"]),
            refundable_cents=int(row["refundable_cents"]),
            recoverable_recharge_coin=int(row["recoverable_recharge_coin"]),
            recoverable_promo_gift_coin=int(row["recoverable_promo_gift_coin"]),
            executed=bool(row["executed"]),
        )
