"""SQLAlchemy adapter for durable RiskService facts.

The current RiskService contract uses ``FROZEN`` for enforcement.  The
broader policy lifecycle may later add an ``ENFORCE`` phase, but the existing
schema has no such transition or audit actor fields; this adapter preserves
the statuses and release evidence that the schema can represent instead of
claiming a fuller audit trail.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from novel_platform.modules.risk.application import RiskService
from novel_platform.modules.risk.domain import (
    LoginRiskSignal,
    OrderFact,
    RiskSignal,
    RiskSignalStatus,
    WatchlistEntry,
)


class SqlRiskService(RiskService):
    """Persist every fact represented by the existing ``RiskService`` API."""

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        metadata = sa.MetaData()
        self._orders: Any = sa.Table("risk_order_facts", metadata, autoload_with=engine)
        self._signals: Any = sa.Table("risk_signals", metadata, autoload_with=engine)
        self._logins: Any = sa.Table("login_risk_signals", metadata, autoload_with=engine)
        self._watchlist: Any = sa.Table("risk_watchlist_entries", metadata, autoload_with=engine)

    def record_order(self, order_id: str, account_id: str, amount_coin: int) -> OrderFact:
        if amount_coin < 0:
            raise ValueError("amount_coin must be non-negative")
        with self.engine.begin() as connection:
            row = self._order_row(connection, order_id, lock=True)
            if row is not None:
                return self._order_from_row(row)
            order = OrderFact(order_id, account_id, amount_coin)
            connection.execute(
                self._orders.insert().values(
                    id=order.id,
                    account_id=order.account_id,
                    amount_coin=order.amount_coin,
                    created_at=datetime.now(UTC),
                )
            )
            return order

    def get_order(self, order_id: str) -> OrderFact:
        with self.engine.begin() as connection:
            row = self._order_row(connection, order_id)
            if row is None:
                raise KeyError(order_id)
            return self._order_from_row(row)

    def observe(self, account_id: str, signal_type: str, order_id: str) -> RiskSignal:
        with self.engine.begin() as connection:
            if self._order_row(connection, order_id) is None:
                raise KeyError(f"order {order_id} not found")
            signal = RiskSignal(
                id=f"RSK_{uuid4().hex}",
                account_id=account_id,
                signal_type=signal_type,
                order_id=order_id,
            )
            connection.execute(
                self._signals.insert().values(
                    id=signal.id,
                    account_id=signal.account_id,
                    signal_type=signal.signal_type,
                    order_id=signal.order_id,
                    status=signal.status.value,
                    created_at=datetime.now(UTC),
                )
            )
            return signal

    def get_signal(self, signal_id: str) -> RiskSignal:
        with self.engine.begin() as connection:
            row = self._signal_row(connection, signal_id)
            if row is None:
                raise KeyError(signal_id)
            return self._signal_from_row(row)

    def freeze(self, signal_id: str) -> RiskSignal:
        with self.engine.begin() as connection:
            row = self._signal_row(connection, signal_id, lock=True)
            if row is None:
                raise KeyError(signal_id)
            connection.execute(
                self._signals.update()
                .where(self._signals.c.id == signal_id)
                .values(status=RiskSignalStatus.FROZEN.value)
            )
            signal = self._signal_from_row(row)
            signal.status = RiskSignalStatus.FROZEN
            return signal

    def record_login(
        self,
        account_id: str,
        device_id: str,
        browser: str,
        operating_system: str,
        ip: str,
        region: str,
        user_agent: str,
    ) -> LoginRiskSignal:
        values = (account_id, device_id, browser, operating_system, ip, region, user_agent)
        if any(not value.strip() for value in values):
            raise ValueError("LOGIN_SIGNAL_INVALID")
        signal = LoginRiskSignal(
            id=f"LOGIN_{uuid4().hex}",
            account_id=account_id,
            device_id=device_id,
            browser=browser,
            operating_system=operating_system,
            ip=ip,
            region=region,
            user_agent=user_agent,
        )
        with self.engine.begin() as connection:
            connection.execute(
                self._logins.insert().values(
                    id=signal.id,
                    account_id=signal.account_id,
                    device_id=signal.device_id,
                    browser=signal.browser,
                    operating_system=signal.operating_system,
                    ip=signal.ip,
                    region=signal.region,
                    user_agent=signal.user_agent,
                    status=signal.status.value,
                    created_at=datetime.now(UTC),
                )
            )
        return signal

    def get_login_signal(self, signal_id: str) -> LoginRiskSignal:
        with self.engine.begin() as connection:
            row = (
                connection.execute(sa.select(self._logins).where(self._logins.c.id == signal_id))
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(signal_id)
            return self._login_from_row(row)

    def add_watchlist(
        self, target_type: str, target_value: str, reason: str, case_id: str
    ) -> WatchlistEntry:
        if target_type not in {
            "ACCOUNT",
            "DEVICE",
            "IP",
            "PAYMENT_TOOL",
            "REAL_NAME",
            "PAYOUT_ACCOUNT",
        }:
            raise ValueError("WATCHLIST_TARGET_INVALID")
        if not target_value.strip() or not reason.strip() or not case_id.strip():
            raise ValueError("WATCHLIST_INVALID")
        entry = WatchlistEntry(f"WATCH_{uuid4().hex}", target_type, target_value, reason, case_id)
        with self.engine.begin() as connection:
            connection.execute(
                self._watchlist.insert().values(
                    id=entry.id,
                    target_type=entry.target_type,
                    target_value=entry.target_value,
                    reason=entry.reason,
                    case_id=entry.case_id,
                    status=entry.status,
                    release_reason=entry.release_reason,
                    evidence_id=entry.evidence_id,
                    created_at=datetime.now(UTC),
                )
            )
        return entry

    def is_watchlisted(self, target_type: str, target_value: str) -> bool:
        with self.engine.begin() as connection:
            return (
                connection.execute(
                    sa.select(self._watchlist.c.id)
                    .where(
                        self._watchlist.c.target_type == target_type,
                        self._watchlist.c.target_value == target_value,
                        self._watchlist.c.status == "ACTIVE",
                    )
                    .limit(1)
                ).scalar_one_or_none()
                is not None
            )

    def release_watchlist(
        self, entry_id: str, reason: str, evidence_id: str, case_id: str
    ) -> WatchlistEntry:
        with self.engine.begin() as connection:
            row = self._watchlist_row(connection, entry_id, lock=True)
            if row is None:
                raise KeyError(entry_id)
            if row["case_id"] != case_id or not reason.strip() or not evidence_id.strip():
                raise ValueError("WATCHLIST_RELEASE_INVALID")
            connection.execute(
                self._watchlist.update()
                .where(self._watchlist.c.id == entry_id)
                .values(status="RELEASED", release_reason=reason.strip(), evidence_id=evidence_id)
            )
            return WatchlistEntry(
                id=str(row["id"]),
                target_type=str(row["target_type"]),
                target_value=str(row["target_value"]),
                reason=str(row["reason"]),
                case_id=str(row["case_id"]),
                status="RELEASED",
                release_reason=reason.strip(),
                evidence_id=evidence_id,
            )

    def watchlist(self, entry_id: str) -> WatchlistEntry:
        with self.engine.begin() as connection:
            row = self._watchlist_row(connection, entry_id)
            if row is None:
                raise KeyError(entry_id)
            return self._watchlist_from_row(row)

    def _order_row(
        self, connection: Connection, order_id: str, *, lock: bool = False
    ) -> sa.RowMapping | None:
        query = sa.select(self._orders).where(self._orders.c.id == order_id)
        if lock:
            query = query.with_for_update()
        return connection.execute(query).mappings().one_or_none()

    def _signal_row(
        self, connection: Connection, signal_id: str, *, lock: bool = False
    ) -> sa.RowMapping | None:
        query = sa.select(self._signals).where(self._signals.c.id == signal_id)
        if lock:
            query = query.with_for_update()
        return connection.execute(query).mappings().one_or_none()

    def _watchlist_row(
        self, connection: Connection, entry_id: str, *, lock: bool = False
    ) -> sa.RowMapping | None:
        query = sa.select(self._watchlist).where(self._watchlist.c.id == entry_id)
        if lock:
            query = query.with_for_update()
        return connection.execute(query).mappings().one_or_none()

    @staticmethod
    def _order_from_row(row: sa.RowMapping) -> OrderFact:
        return OrderFact(str(row["id"]), str(row["account_id"]), int(row["amount_coin"]))

    @staticmethod
    def _signal_from_row(row: sa.RowMapping) -> RiskSignal:
        return RiskSignal(
            id=str(row["id"]),
            account_id=str(row["account_id"]),
            signal_type=str(row["signal_type"]),
            order_id=str(row["order_id"]),
            status=RiskSignalStatus(str(row["status"])),
        )

    @staticmethod
    def _login_from_row(row: sa.RowMapping) -> LoginRiskSignal:
        return LoginRiskSignal(
            id=str(row["id"]),
            account_id=str(row["account_id"]),
            device_id=str(row["device_id"]),
            browser=str(row["browser"]),
            operating_system=str(row["operating_system"]),
            ip=str(row["ip"]),
            region=str(row["region"]),
            user_agent=str(row["user_agent"]),
            status=RiskSignalStatus(str(row["status"])),
        )

    @staticmethod
    def _watchlist_from_row(row: sa.RowMapping) -> WatchlistEntry:
        return WatchlistEntry(
            id=str(row["id"]),
            target_type=str(row["target_type"]),
            target_value=str(row["target_value"]),
            reason=str(row["reason"]),
            case_id=str(row["case_id"]),
            status=str(row["status"]),
            release_reason=(
                str(row["release_reason"]) if row["release_reason"] is not None else None
            ),
            evidence_id=str(row["evidence_id"]) if row["evidence_id"] is not None else None,
        )
