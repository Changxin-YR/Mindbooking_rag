"""SQLAlchemy adapter for the current author-finance contract."""

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from novel_platform.modules.author_finance.application import AuthorFinanceService
from novel_platform.modules.author_finance.domain import (
    Chargeback,
    Contract,
    ContractStatus,
    ContractVersion,
    PayoutOrder,
    PayoutStatus,
    RevenueEntry,
    RevenueStatus,
    Settlement,
    SettlementStatus,
    Withdrawal,
    WithdrawalStatus,
)
from novel_platform.modules.payment import PayoutProvider, ProviderEvent


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class SqlAuthorFinanceService(AuthorFinanceService):
    def __init__(
        self,
        engine: Engine,
        payout_provider: PayoutProvider | None = None,
        payout_provider_secret: str = "",
    ) -> None:
        super().__init__(payout_provider, payout_provider_secret)
        self.engine = engine
        metadata = sa.MetaData()
        self._contracts: Any = sa.Table("contracts", metadata, autoload_with=engine)
        self._contract_versions: Any = sa.Table("contract_versions", metadata, autoload_with=engine)
        self._revenue: Any = sa.Table("author_revenue_entries", metadata, autoload_with=engine)
        self._settlements: Any = sa.Table("author_settlements", metadata, autoload_with=engine)
        self._withdrawals: Any = sa.Table("withdrawal_requests", metadata, autoload_with=engine)
        self._chargebacks: Any = sa.Table("chargebacks", metadata, autoload_with=engine)
        self._claims: Any = sa.Table("financial_recovery_claims", metadata, autoload_with=engine)
        try:
            self._payout_orders: Any = sa.Table("payout_orders", metadata, autoload_with=engine)
        except sa.exc.NoSuchTableError:
            self._payout_orders = None
        try:
            self._outbox: Any = sa.Table("outbox_events", metadata, autoload_with=engine)
        except sa.exc.NoSuchTableError:
            self._outbox = None

    def create_contract(self, author_id: str, book_id: str, share_bps: int = 7000) -> Contract:
        if not 0 < share_bps <= 10000:
            raise ValueError("INVALID_REVENUE_SHARE_BPS")
        contract = Contract(_id("CTR"), author_id, book_id)
        version = ContractVersion(_id("CTV"), contract.id, 1, share_bps)
        contract.version_ids.append(version.id)
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            connection.execute(
                self._contracts.insert().values(
                    id=contract.id,
                    author_id=contract.author_id,
                    book_id=contract.book_id,
                    status=contract.status.value,
                    created_at=now,
                )
            )
            connection.execute(
                self._contract_versions.insert().values(
                    id=version.id,
                    contract_id=version.contract_id,
                    version=version.version,
                    revenue_share_bps=version.revenue_share_bps,
                    created_at=now,
                )
            )
            self._append_outbox(
                connection,
                "ContractCreated",
                contract.id,
                {"author_id": author_id, "book_id": book_id, "version_id": version.id},
            )
        return contract

    def get_contract(self, contract_id: str) -> Contract:
        with self.engine.begin() as connection:
            return self._contract_from_connection(connection, contract_id)

    def approve_contract(self, contract_id: str, approver_id: str) -> Contract:
        with self.engine.begin() as connection:
            contract = self._contract_from_connection(connection, contract_id, lock=True)
            if contract.author_id == approver_id:
                raise ValueError("MAKER_CHECKER_REQUIRED")
            if contract.status is not ContractStatus.DRAFT:
                raise ValueError("CONTRACT_NOT_DRAFT")
            connection.execute(
                self._contracts.update()
                .where(self._contracts.c.id == contract_id)
                .values(status=ContractStatus.APPROVED.value)
            )
            contract.status = ContractStatus.APPROVED
            return contract

    def activate_contract(self, contract_id: str) -> Contract:
        with self.engine.begin() as connection:
            contract = self._contract_from_connection(connection, contract_id, lock=True)
            if contract.status is not ContractStatus.APPROVED:
                raise ValueError("CONTRACT_NOT_APPROVED")
            connection.execute(
                self._contracts.update()
                .where(self._contracts.c.id == contract_id)
                .values(status=ContractStatus.ACTIVE.value)
            )
            self._append_outbox(
                connection,
                "ContractActivated",
                contract_id,
                {"author_id": contract.author_id, "book_id": contract.book_id},
            )
            contract.status = ContractStatus.ACTIVE
            return contract

    def record_revenue(
        self,
        author_id: str,
        source: str,
        source_ref: str,
        gross_cents: int,
        share_bps: int,
    ) -> RevenueEntry:
        if gross_cents <= 0 or not 0 <= share_bps <= 10000:
            raise ValueError("INVALID_REVENUE_AMOUNT")
        with self.engine.begin() as connection:
            existing = (
                connection.execute(
                    sa.select(self._revenue)
                    .where(self._revenue.c.source_ref == source_ref)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return self._revenue_from_row(existing)
            entry = RevenueEntry(
                _id("REV"),
                author_id,
                source,
                source_ref,
                gross_cents,
                gross_cents * share_bps // 10000,
            )
            connection.execute(
                self._revenue.insert().values(
                    id=entry.id,
                    author_id=entry.author_id,
                    source=entry.source,
                    source_ref=entry.source_ref,
                    gross_cents=entry.gross_cents,
                    author_cents=entry.author_cents,
                    status=entry.status.value,
                    settlement_id=entry.settlement_id,
                    created_at=datetime.now(UTC),
                )
            )
            self._append_outbox(
                connection,
                "RevenueCreated",
                entry.id,
                {"author_id": author_id, "source": source, "source_ref": source_ref},
            )
            return entry

    def record_revenue_in_transaction(
        self,
        connection: Connection,
        author_id: str,
        book_id: str,
        source: str,
        source_ref: str,
        gross_cents: int,
    ) -> RevenueEntry:
        """Record chapter revenue on the caller's transaction connection."""
        if (
            gross_cents <= 0
            or not author_id.strip()
            or not book_id.strip()
            or not source_ref.strip()
        ):
            raise ValueError("INVALID_REVENUE_AMOUNT")
        existing = (
            connection.execute(
                sa.select(self._revenue)
                .where(self._revenue.c.source_ref == source_ref)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            return self._revenue_from_row(existing)
        contract_row = connection.execute(
            sa.select(self._contracts.c.id)
            .where(
                self._contracts.c.author_id == author_id,
                self._contracts.c.book_id == book_id,
                self._contracts.c.status == ContractStatus.ACTIVE.value,
            )
            .limit(1)
        ).scalar_one_or_none()
        if contract_row is None:
            raise ValueError("CONTRACT_NOT_ACTIVE")
        share_bps = connection.execute(
            sa.select(self._contract_versions.c.revenue_share_bps)
            .where(self._contract_versions.c.contract_id == contract_row)
            .order_by(self._contract_versions.c.version.desc())
            .limit(1)
        ).scalar_one()
        entry = RevenueEntry(
            _id("REV"),
            author_id,
            source,
            source_ref,
            gross_cents,
            gross_cents * int(share_bps) // 10000,
        )
        connection.execute(
            self._revenue.insert().values(
                id=entry.id,
                author_id=entry.author_id,
                source=entry.source,
                source_ref=entry.source_ref,
                gross_cents=entry.gross_cents,
                author_cents=entry.author_cents,
                status=entry.status.value,
                settlement_id=None,
                created_at=datetime.now(UTC),
            )
        )
        self._append_outbox(
            connection,
            "RevenueCreated",
            entry.id,
            {"author_id": author_id, "source": source, "source_ref": source_ref},
        )
        return entry

    def confirm_revenue(self, revenue_id: str) -> RevenueEntry:
        with self.engine.begin() as connection:
            row = self._revenue_row(connection, revenue_id, lock=True)
            entry = self._revenue_from_row(row)
            if entry.status is not RevenueStatus.RISK_PENDING:
                raise ValueError("REVENUE_NOT_PENDING")
            connection.execute(
                self._revenue.update()
                .where(self._revenue.c.id == revenue_id)
                .values(status=RevenueStatus.CONFIRMED.value)
            )
            entry.status = RevenueStatus.CONFIRMED
            return entry

    def settle(self, author_id: str, period: str) -> Settlement:
        with self.engine.begin() as connection:
            existing = (
                connection.execute(
                    sa.select(self._settlements)
                    .where(
                        self._settlements.c.author_id == author_id,
                        self._settlements.c.period == period,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return self._settlement_from_row(existing)
            eligible = list(
                connection.execute(
                    sa.select(self._revenue)
                    .where(
                        self._revenue.c.author_id == author_id,
                        self._revenue.c.status == RevenueStatus.CONFIRMED.value,
                    )
                    .with_for_update()
                ).mappings()
            )
            settlement = Settlement(
                _id("SET"),
                author_id,
                period,
                sum(int(row["author_cents"]) for row in eligible),
                status=SettlementStatus.WITHDRAWABLE,
            )
            connection.execute(
                self._settlements.insert().values(
                    id=settlement.id,
                    author_id=settlement.author_id,
                    period=settlement.period,
                    amount_cents=settlement.amount_cents,
                    withdrawn_cents=settlement.withdrawn_cents,
                    status=settlement.status.value,
                    created_at=datetime.now(UTC),
                )
            )
            for row in eligible:
                connection.execute(
                    self._revenue.update()
                    .where(self._revenue.c.id == row["id"])
                    .values(status=RevenueStatus.SETTLED.value, settlement_id=settlement.id)
                )
            self._append_outbox(
                connection,
                "SettlementCreated",
                settlement.id,
                {"author_id": author_id, "period": period, "amount_cents": settlement.amount_cents},
            )
            return settlement

    def withdraw(
        self,
        settlement_id: str,
        author_id: str,
        amount_cents: int,
        payout_method: str,
        holder_matches_real_name: bool,
    ) -> Withdrawal:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._settlements)
                    .where(self._settlements.c.id == settlement_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(settlement_id)
            settlement = self._settlement_from_row(row)
            if (
                settlement.author_id != author_id
                or settlement.status is not SettlementStatus.WITHDRAWABLE
            ):
                raise ValueError("SETTLEMENT_NOT_WITHDRAWABLE")
            if (
                amount_cents < 1000
                or amount_cents > settlement.amount_cents - settlement.withdrawn_cents
            ):
                raise ValueError("INVALID_WITHDRAWAL_AMOUNT")
            if not holder_matches_real_name:
                raise ValueError("PAYOUT_HOLDER_MISMATCH")
            withdrawal = Withdrawal(
                _id("WD"), settlement_id, author_id, amount_cents, payout_method
            )
            connection.execute(
                self._withdrawals.insert().values(
                    id=withdrawal.id,
                    settlement_id=withdrawal.settlement_id,
                    author_id=withdrawal.author_id,
                    amount_cents=withdrawal.amount_cents,
                    payout_method=withdrawal.payout_method,
                    status=withdrawal.status.value,
                    created_at=datetime.now(UTC),
                    **self._withdrawal_review_values(
                        risk_status="PENDING",
                        finance_status="PENDING",
                        second_factor_verified=holder_matches_real_name,
                        payout_destination=payout_method,
                    ),
                )
            )
            connection.execute(
                self._settlements.update()
                .where(self._settlements.c.id == settlement_id)
                .values(withdrawn_cents=settlement.withdrawn_cents + amount_cents)
            )
            self._append_outbox(
                connection,
                "WithdrawalRequested",
                withdrawal.id,
                {"author_id": author_id, "amount_cents": amount_cents},
            )
            return withdrawal

    def approve_withdrawal_risk(self, withdrawal_id: str, reviewer_id: str) -> Withdrawal:
        del reviewer_id
        with self.engine.begin() as connection:
            row = self._withdrawal_row(connection, withdrawal_id, lock=True)
            if "risk_status" not in self._withdrawals.c:
                raise ValueError("PAYOUT_REVIEW_NOT_CONFIGURED")
            if row["status"] != WithdrawalStatus.PENDING.value:
                raise ValueError("WITHDRAWAL_NOT_REVIEWABLE")
            if row["risk_status"] not in ("PENDING", "APPROVED"):
                raise ValueError("WITHDRAWAL_NOT_REVIEWABLE")
            connection.execute(
                self._withdrawals.update()
                .where(self._withdrawals.c.id == withdrawal_id)
                .values(risk_status="APPROVED")
            )
            return self._withdrawal_from_row({**dict(row), "risk_status": "APPROVED"})

    def approve_withdrawal_finance(self, withdrawal_id: str, reviewer_id: str) -> PayoutOrder:
        del reviewer_id
        if self._payout_orders is None:
            raise ValueError("PAYOUT_NOT_CONFIGURED")
        with self.engine.begin() as connection:
            row = self._withdrawal_row(connection, withdrawal_id, lock=True)
            existing = self._payout_row_for_withdrawal(connection, withdrawal_id, lock=True)
            if existing is not None:
                return self._payout_from_row(existing)
            if "risk_status" not in self._withdrawals.c:
                raise ValueError("PAYOUT_REVIEW_NOT_CONFIGURED")
            if row["risk_status"] != "APPROVED":
                raise ValueError("PAYOUT_REVIEW_REQUIRED")
            if row["status"] != WithdrawalStatus.PENDING.value:
                raise ValueError("WITHDRAWAL_NOT_REVIEWABLE")
            if self.payout_provider is None or not self.payout_provider_secret:
                raise ValueError("PAYOUT_PROVIDER_NOT_CONFIGURED")
            connection.execute(
                self._withdrawals.update()
                .where(self._withdrawals.c.id == withdrawal_id)
                .values(finance_status="APPROVED")
            )
            return self._create_payout_order_in_connection(connection, row)

    def create_payout_order(self, withdrawal_id: str, reviewer_id: str) -> PayoutOrder:
        """Create a provider order only after both review facts are present."""
        del reviewer_id
        if self._payout_orders is None:
            raise ValueError("PAYOUT_NOT_CONFIGURED")
        with self.engine.begin() as connection:
            row = self._withdrawal_row(connection, withdrawal_id, lock=True)
            existing = self._payout_row_for_withdrawal(connection, withdrawal_id, lock=True)
            if existing is not None:
                return self._payout_from_row(existing)
            if (
                "risk_status" not in self._withdrawals.c
                or row["risk_status"] != "APPROVED"
                or row["finance_status"] != "APPROVED"
            ):
                raise ValueError("PAYOUT_REVIEW_REQUIRED")
            if self.payout_provider is None or not self.payout_provider_secret:
                raise ValueError("PAYOUT_PROVIDER_NOT_CONFIGURED")
            return self._create_payout_order_in_connection(connection, row)

    def handle_payout_provider_event(
        self, event: ProviderEvent, *, now: datetime | None = None
    ) -> PayoutOrder:
        if self._payout_orders is None:
            raise ValueError("PAYOUT_NOT_CONFIGURED")
        if self.payout_provider is None or not self.payout_provider_secret:
            raise ValueError("PAYOUT_PROVIDER_NOT_CONFIGURED")
        if event.event_type != "PAYOUT":
            raise ValueError("PAYOUT_EVENT_TYPE_INVALID")
        provider_name = getattr(self.payout_provider, "provider_name", event.provider)
        if event.provider != provider_name:
            raise ValueError("PAYOUT_PROVIDER_MISMATCH")
        if not event.verify_signature(self.payout_provider_secret):
            raise ValueError("PAYOUT_SIGNATURE_INVALID")
        if event.available_at > (now or datetime.now(UTC)):
            raise ValueError("PAYOUT_EVENT_NOT_AVAILABLE")
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._payout_orders)
                    .where(self._payout_orders.c.payout_no == event.reference_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise ValueError("PAYOUT_NOT_FOUND")
            payout = self._payout_from_row(row)
            if payout.amount_cents != event.amount_cents or payout.currency != event.currency:
                raise ValueError("PAYOUT_AMOUNT_MISMATCH")
            if payout.provider_event_id == event.event_id:
                return payout
            if payout.status is PayoutStatus.SUCCESS:
                raise ValueError("PAYOUT_STATE_CONFLICT")
            updated_status = PayoutStatus(event.status.value)
            updated_at = datetime.now(UTC)
            connection.execute(
                self._payout_orders.update()
                .where(self._payout_orders.c.id == payout.id)
                .values(
                    status=updated_status.value,
                    provider_event_id=event.event_id,
                    updated_at=updated_at,
                )
            )
            if updated_status is PayoutStatus.SUCCESS:
                withdrawal_status = WithdrawalStatus.PAID.value
            elif updated_status in (
                PayoutStatus.FAILED,
                PayoutStatus.REJECTED,
                PayoutStatus.TIMEOUT,
            ):
                withdrawal_status = WithdrawalStatus.FAILED.value
            else:
                withdrawal_status = WithdrawalStatus.PENDING.value
            connection.execute(
                self._withdrawals.update()
                .where(self._withdrawals.c.id == payout.withdrawal_id)
                .values(status=withdrawal_status)
            )
            self._append_outbox(
                connection,
                "PayoutSucceeded"
                if updated_status is PayoutStatus.SUCCESS
                else "PayoutStatusChanged",
                payout.payout_no,
                {"withdrawal_id": payout.withdrawal_id, "status": updated_status.value},
            )
            return PayoutOrder(
                payout.id,
                payout.withdrawal_id,
                payout.payout_no,
                payout.provider,
                payout.amount_cents,
                payout.currency,
                payout.destination,
                updated_status,
                event.event_id,
            )

    def _create_payout_order_in_connection(
        self, connection: Connection, withdrawal_row: sa.RowMapping
    ) -> PayoutOrder:
        if self._payout_orders is None or self.payout_provider is None:
            raise ValueError("PAYOUT_PROVIDER_NOT_CONFIGURED")
        destination = str(
            withdrawal_row.get("payout_destination") or withdrawal_row["payout_method"]
        )
        payout_no = f"PO-{uuid4().hex}"
        payout = self.payout_provider.create_payout(
            payout_no,
            int(withdrawal_row["amount_cents"]),
            "CNY",
            destination,
        )
        now = datetime.now(UTC)
        result = PayoutOrder(
            id=_id("PAYOUT"),
            withdrawal_id=str(withdrawal_row["id"]),
            payout_no=payout.payout_no,
            provider=payout.provider,
            amount_cents=payout.amount_cents,
            currency=payout.currency,
            destination=payout.destination,
        )
        connection.execute(
            self._payout_orders.insert().values(
                id=result.id,
                withdrawal_id=result.withdrawal_id,
                payout_no=result.payout_no,
                provider=result.provider,
                amount_cents=result.amount_cents,
                currency=result.currency,
                destination=result.destination,
                status=result.status.value,
                provider_event_id=None,
                created_at=now,
                updated_at=now,
            )
        )
        self._append_outbox(
            connection,
            "PayoutOrderCreated",
            result.payout_no,
            {"withdrawal_id": result.withdrawal_id, "amount_cents": result.amount_cents},
        )
        return result

    def _withdrawal_row(
        self, connection: Connection, withdrawal_id: str, *, lock: bool = False
    ) -> sa.RowMapping:
        query = sa.select(self._withdrawals).where(self._withdrawals.c.id == withdrawal_id)
        if lock:
            query = query.with_for_update()
        row = connection.execute(query).mappings().one_or_none()
        if row is None:
            raise KeyError(withdrawal_id)
        return row

    def _payout_row_for_withdrawal(
        self, connection: Connection, withdrawal_id: str, *, lock: bool = False
    ) -> sa.RowMapping | None:
        if self._payout_orders is None:
            return None
        query = sa.select(self._payout_orders).where(
            self._payout_orders.c.withdrawal_id == withdrawal_id
        )
        if lock:
            query = query.with_for_update()
        return connection.execute(query).mappings().one_or_none()

    @staticmethod
    def _payout_from_row(row: sa.RowMapping) -> PayoutOrder:
        return PayoutOrder(
            id=str(row["id"]),
            withdrawal_id=str(row["withdrawal_id"]),
            payout_no=str(row["payout_no"]),
            provider=str(row["provider"]),
            amount_cents=int(row["amount_cents"]),
            currency=str(row["currency"]),
            destination=str(row["destination"]),
            status=PayoutStatus(str(row["status"])),
            provider_event_id=(
                str(row["provider_event_id"]) if row["provider_event_id"] is not None else None
            ),
        )

    @staticmethod
    def _withdrawal_from_row(row: Mapping[str, Any]) -> Withdrawal:
        return Withdrawal(
            id=str(row["id"]),
            settlement_id=str(row["settlement_id"]),
            author_id=str(row["author_id"]),
            amount_cents=int(row["amount_cents"]),
            payout_method=str(row["payout_method"]),
            status=WithdrawalStatus(str(row["status"])),
        )

    def _withdrawal_review_values(self, **values: object) -> dict[str, object]:
        return {name: value for name, value in values.items() if name in self._withdrawals.c}

    def _append_outbox(
        self,
        connection: Connection,
        event_type: str,
        aggregate_id: str,
        payload: dict[str, object],
    ) -> None:
        if self._outbox is None:
            return
        now = datetime.now(UTC)
        values: dict[str, object] = {
            "id": f"OUTBOX_{uuid4().hex}",
            "event_type": event_type,
            "aggregate_id": aggregate_id,
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            "attempts": 0,
            "created_at": now,
        }
        optional = {
            "status": "NEW",
            "available_at": None,
            "locked_by": None,
            "locked_at": None,
            "last_error": None,
            "processed_at": None,
        }
        values.update({name: value for name, value in optional.items() if name in self._outbox.c})
        connection.execute(self._outbox.insert().values(**values))

    def chargeback(self, source_ref: str, amount_cents: int) -> Chargeback:
        if amount_cents <= 0:
            raise ValueError("INVALID_CHARGEBACK_AMOUNT")
        with self.engine.begin() as connection:
            revenue_row = (
                connection.execute(
                    sa.select(self._revenue)
                    .where(self._revenue.c.source_ref == source_ref)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if revenue_row is None:
                raise KeyError(source_ref)
            already_recovered = connection.execute(
                sa.select(
                    sa.func.coalesce(sa.func.sum(self._chargebacks.c.recovered_cents), 0)
                ).where(self._chargebacks.c.source_ref == source_ref)
            ).scalar_one()
            recovered = min(
                max(0, int(revenue_row["author_cents"]) - int(already_recovered)), amount_cents
            )
            chargeback = Chargeback(_id("CB"), source_ref, amount_cents, recovered)
            connection.execute(
                self._chargebacks.insert().values(
                    id=chargeback.id,
                    source_ref=chargeback.source_ref,
                    amount_cents=chargeback.amount_cents,
                    recovered_cents=chargeback.recovered_cents,
                    created_at=datetime.now(UTC),
                )
            )
            if recovered < amount_cents:
                connection.execute(
                    self._claims.insert().values(
                        id=_id("CLM"),
                        author_id=str(revenue_row["author_id"]),
                        chargeback_id=chargeback.id,
                        amount_cents=amount_cents - recovered,
                        status="OPEN",
                        created_at=datetime.now(UTC),
                    )
                )
            return chargeback

    def _contract_from_connection(
        self, connection: Connection, contract_id: str, *, lock: bool = False
    ) -> Contract:
        query = sa.select(self._contracts).where(self._contracts.c.id == contract_id)
        if lock:
            query = query.with_for_update()
        row = connection.execute(query).mappings().one_or_none()
        if row is None:
            raise KeyError(contract_id)
        versions = connection.execute(
            sa.select(self._contract_versions.c.id)
            .where(self._contract_versions.c.contract_id == contract_id)
            .order_by(self._contract_versions.c.version)
        ).scalars()
        return Contract(
            id=str(row["id"]),
            author_id=str(row["author_id"]),
            book_id=str(row["book_id"]),
            status=ContractStatus(str(row["status"])),
            version_ids=[str(version_id) for version_id in versions],
        )

    def _revenue_row(
        self, connection: Connection, revenue_id: str, *, lock: bool = False
    ) -> sa.RowMapping:
        query = sa.select(self._revenue).where(self._revenue.c.id == revenue_id)
        if lock:
            query = query.with_for_update()
        row = connection.execute(query).mappings().one_or_none()
        if row is None:
            raise KeyError(revenue_id)
        return row

    @staticmethod
    def _revenue_from_row(row: sa.RowMapping) -> RevenueEntry:
        return RevenueEntry(
            id=str(row["id"]),
            author_id=str(row["author_id"]),
            source=str(row["source"]),
            source_ref=str(row["source_ref"]),
            gross_cents=int(row["gross_cents"]),
            author_cents=int(row["author_cents"]),
            status=RevenueStatus(str(row["status"])),
            settlement_id=str(row["settlement_id"]) if row["settlement_id"] else None,
        )

    @staticmethod
    def _settlement_from_row(row: sa.RowMapping) -> Settlement:
        return Settlement(
            id=str(row["id"]),
            author_id=str(row["author_id"]),
            period=str(row["period"]),
            amount_cents=int(row["amount_cents"]),
            status=SettlementStatus(str(row["status"])),
            withdrawn_cents=int(row["withdrawn_cents"]),
        )
