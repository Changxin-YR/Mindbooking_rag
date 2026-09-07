"""SQLAlchemy wallet adapter for the MySQL wallet tables."""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from novel_platform.modules.wallet.application import InsufficientFunds
from novel_platform.modules.wallet.domain import (
    AssetType,
    LotAllocation,
    WalletAssetLot,
    WalletBalance,
    WalletEntry,
    WalletSourceSnapshot,
    require_positive_int,
)

wallet_accounts = sa.table(
    "wallet_accounts",
    sa.column("id", sa.BigInteger),
    sa.column("account_id", sa.String),
    sa.column("recharge_coin", sa.BigInteger),
    sa.column("gift_coin", sa.BigInteger),
    sa.column("created_at", sa.DateTime),
)
wallet_journals = sa.table(
    "wallet_journals",
    sa.column("id", sa.BigInteger),
    sa.column("account_id", sa.String),
    sa.column("journal_type", sa.String),
    sa.column("idempotency_key", sa.String),
    sa.column("created_at", sa.DateTime),
)
wallet_entries = sa.table(
    "wallet_entries",
    sa.column("id", sa.BigInteger),
    sa.column("journal_id", sa.BigInteger),
    sa.column("account_id", sa.String),
    sa.column("asset_type", sa.String),
    sa.column("amount", sa.BigInteger),
    sa.column("reason", sa.String),
    sa.column("created_at", sa.DateTime),
)
wallet_asset_lots = sa.table(
    "wallet_asset_lots",
    sa.column("id", sa.BigInteger),
    sa.column("lot_id", sa.String),
    sa.column("account_id", sa.String),
    sa.column("asset_type", sa.String),
    sa.column("origin", sa.String),
    sa.column("available_amount", sa.BigInteger),
    sa.column("issued_at", sa.DateTime),
    sa.column("expires_at", sa.DateTime),
    sa.column("source_ref", sa.String),
    sa.column("issued_amount", sa.BigInteger),
)
wallet_lot_allocations = sa.table(
    "wallet_lot_allocations",
    sa.column("id", sa.BigInteger),
    sa.column("lot_id", sa.String),
    sa.column("journal_id", sa.BigInteger),
    sa.column("allocation_type", sa.String),
    sa.column("amount", sa.BigInteger),
)


class SqlWalletService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def lock_account_in_transaction(self, connection: Connection, account_id: str) -> None:
        """Serialize account-scoped business transactions before asset mutation."""
        self._ensure_wallet(connection, account_id, lock=True)

    def balance(self, account_id: str, now: datetime | None = None) -> WalletBalance:
        at = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            wallet = connection.execute(
                sa.select(wallet_accounts.c.recharge_coin).where(
                    wallet_accounts.c.account_id == account_id
                )
            ).scalar_one_or_none()
            gift = connection.execute(
                sa.select(
                    sa.func.coalesce(sa.func.sum(wallet_asset_lots.c.available_amount), 0)
                ).where(
                    wallet_asset_lots.c.account_id == account_id,
                    wallet_asset_lots.c.asset_type == AssetType.GIFT.value,
                    sa.or_(
                        wallet_asset_lots.c.expires_at.is_(None),
                        wallet_asset_lots.c.expires_at > at,
                    ),
                )
            ).scalar_one()
        return WalletBalance(int(wallet or 0), int(gift))

    def entries(self, account_id: str) -> tuple[WalletEntry, ...]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(
                    wallet_entries.c.id,
                    wallet_entries.c.account_id,
                    wallet_entries.c.asset_type,
                    wallet_entries.c.amount,
                    wallet_entries.c.reason,
                )
                .where(wallet_entries.c.account_id == account_id)
                .order_by(wallet_entries.c.id)
            ).mappings()
            return tuple(
                WalletEntry(
                    str(row["id"]),
                    row["account_id"],
                    AssetType(row["asset_type"]),
                    int(row["amount"]),
                    row["reason"],
                )
                for row in rows
            )

    def grant_recharge_coin(
        self, account_id: str, amount: int, reason: str = "RECHARGE", source_ref: str | None = None
    ) -> WalletAssetLot:
        return self._grant(
            account_id, AssetType.RECHARGE, amount, "RECHARGE", None, reason, source_ref
        )

    def grant_recharge_coin_in_transaction(
        self,
        connection: Connection,
        account_id: str,
        amount: int,
        reason: str = "RECHARGE",
        source_ref: str | None = None,
    ) -> WalletAssetLot:
        return self._grant_in_connection(
            connection, account_id, AssetType.RECHARGE, amount, "RECHARGE", None, reason, source_ref
        )

    def grant_gift_coin(
        self,
        account_id: str,
        amount: int,
        origin: str,
        expires_at: datetime | None,
        issued_at: datetime | None = None,
        source_ref: str | None = None,
    ) -> WalletAssetLot:
        return self._grant(
            account_id,
            AssetType.GIFT,
            amount,
            origin,
            expires_at,
            "GIFT_GRANT",
            source_ref,
            issued_at,
        )

    def grant_gift_coin_in_transaction(
        self,
        connection: Connection,
        account_id: str,
        amount: int,
        origin: str,
        expires_at: datetime | None,
        issued_at: datetime | None = None,
        source_ref: str | None = None,
    ) -> WalletAssetLot:
        return self._grant_in_connection(
            connection,
            account_id,
            AssetType.GIFT,
            amount,
            origin,
            expires_at,
            "GIFT_GRANT",
            source_ref,
            issued_at,
        )

    def source_snapshot(
        self, account_id: str, source_ref: str, now: datetime | None = None
    ) -> WalletSourceSnapshot:
        with self.engine.begin() as connection:
            return self.source_snapshot_in_transaction(connection, account_id, source_ref, now)

    def source_snapshot_in_transaction(
        self,
        connection: Connection,
        account_id: str,
        source_ref: str,
        now: datetime | None = None,
    ) -> WalletSourceSnapshot:
        at = now or datetime.now(UTC)
        rows = (
            connection.execute(
                sa.select(
                    wallet_asset_lots.c.asset_type,
                    wallet_asset_lots.c.origin,
                    wallet_asset_lots.c.available_amount,
                    wallet_asset_lots.c.issued_amount,
                    wallet_asset_lots.c.expires_at,
                )
                .where(
                    wallet_asset_lots.c.account_id == account_id,
                    wallet_asset_lots.c.source_ref == source_ref,
                )
                .with_for_update()
            )
            .mappings()
            .all()
        )
        consumed_recharge = consumed_gift = expired_gift = remaining_recharge = active_gift = 0
        for row in rows:
            issued = int(row["issued_amount"] or row["available_amount"])
            available = int(row["available_amount"])
            if row["asset_type"] == AssetType.RECHARGE.value:
                consumed_recharge += issued - available
                remaining_recharge += available
            elif row["origin"] == "PROMO":
                consumed_gift += issued - available
                expires_at = row["expires_at"]
                if expires_at is not None and expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                if expires_at is not None and expires_at <= at:
                    expired_gift += available
                else:
                    active_gift += available
        return WalletSourceSnapshot(
            consumed_recharge, consumed_gift, expired_gift, remaining_recharge, active_gift
        )

    def recover_source_assets(
        self, account_id: str, source_ref: str, now: datetime | None = None
    ) -> None:
        with self.engine.begin() as connection:
            self.recover_source_assets_in_transaction(connection, account_id, source_ref, now)

    def recover_source_assets_in_transaction(
        self, connection: Connection, account_id: str, source_ref: str, now: datetime | None = None
    ) -> None:
        at = now or datetime.now(UTC)
        self._ensure_wallet(connection, account_id, lock=True)
        rows = (
            connection.execute(
                sa.select(
                    wallet_asset_lots.c.lot_id,
                    wallet_asset_lots.c.asset_type,
                    wallet_asset_lots.c.available_amount,
                )
                .where(
                    wallet_asset_lots.c.account_id == account_id,
                    wallet_asset_lots.c.source_ref == source_ref,
                    wallet_asset_lots.c.available_amount > 0,
                    sa.or_(
                        wallet_asset_lots.c.asset_type == AssetType.RECHARGE.value,
                        sa.and_(
                            wallet_asset_lots.c.asset_type == AssetType.GIFT.value,
                            wallet_asset_lots.c.origin == "PROMO",
                            sa.or_(
                                wallet_asset_lots.c.expires_at.is_(None),
                                wallet_asset_lots.c.expires_at > at,
                            ),
                        ),
                    ),
                )
                .with_for_update()
            )
            .mappings()
            .all()
        )
        if not rows:
            return
        journal_id = self._journal(connection, account_id, "REFUND_RECOVERY")
        deltas = {AssetType.RECHARGE.value: 0, AssetType.GIFT.value: 0}
        for row in rows:
            amount = int(row["available_amount"])
            connection.execute(
                wallet_asset_lots.update()
                .where(wallet_asset_lots.c.lot_id == row["lot_id"])
                .values(available_amount=0)
            )
            deltas[row["asset_type"]] += amount
            self._entry(
                connection,
                journal_id,
                account_id,
                row["asset_type"],
                -amount,
                "REFUND_RECOVERY",
            )
        self._change_balance(
            connection,
            account_id,
            -deltas[AssetType.RECHARGE.value],
            -deltas[AssetType.GIFT.value],
        )

    def spend(
        self, account_id: str, amount: int, now: datetime | None = None, reason: str = "PURCHASE"
    ) -> tuple[LotAllocation, ...]:
        require_positive_int(amount, "amount")
        at = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            self._ensure_wallet(connection, account_id, lock=True)
            rows = (
                connection.execute(
                    sa.select(
                        wallet_asset_lots.c.lot_id,
                        wallet_asset_lots.c.asset_type,
                        wallet_asset_lots.c.available_amount,
                        wallet_asset_lots.c.expires_at,
                        wallet_asset_lots.c.issued_at,
                    )
                    .where(
                        wallet_asset_lots.c.account_id == account_id,
                        wallet_asset_lots.c.available_amount > 0,
                        sa.or_(
                            wallet_asset_lots.c.asset_type == AssetType.RECHARGE.value,
                            sa.and_(
                                wallet_asset_lots.c.asset_type == AssetType.GIFT.value,
                                sa.or_(
                                    wallet_asset_lots.c.expires_at.is_(None),
                                    wallet_asset_lots.c.expires_at > at,
                                ),
                            ),
                        ),
                    )
                    .with_for_update()
                )
                .mappings()
                .all()
            )
            rows = sorted(
                rows,
                key=lambda row: (
                    row["asset_type"] != AssetType.GIFT.value,
                    row["expires_at"] is None,
                    row["expires_at"],
                    row["issued_at"],
                    row["lot_id"],
                ),
            )
            if sum(int(row["available_amount"]) for row in rows) < amount:
                raise InsufficientFunds("INSUFFICIENT_FUNDS")
            journal_id = self._journal(connection, account_id, "SPEND")
            remaining = amount
            allocations: list[LotAllocation] = []
            deltas = {AssetType.RECHARGE.value: 0, AssetType.GIFT.value: 0}
            for row in rows:
                if not remaining:
                    break
                consumed = min(remaining, int(row["available_amount"]))
                remaining -= consumed
                allocations.append(
                    LotAllocation(row["lot_id"], AssetType(row["asset_type"]), consumed)
                )
                deltas[row["asset_type"]] += consumed
                connection.execute(
                    wallet_asset_lots.update()
                    .where(wallet_asset_lots.c.lot_id == row["lot_id"])
                    .values(available_amount=wallet_asset_lots.c.available_amount - consumed)
                )
                self._entry(
                    connection, journal_id, account_id, row["asset_type"], -consumed, reason
                )
                connection.execute(
                    wallet_lot_allocations.insert().values(
                        lot_id=row["lot_id"],
                        journal_id=journal_id,
                        allocation_type="SPEND",
                        amount=consumed,
                    )
                )
            self._change_balance(
                connection,
                account_id,
                -deltas[AssetType.RECHARGE.value],
                -deltas[AssetType.GIFT.value],
            )
            return tuple(allocations)

    def spend_in_transaction(
        self,
        connection: Connection,
        account_id: str,
        amount: int,
        now: datetime | None = None,
        reason: str = "PURCHASE",
        spend_mode: str = "GIFT_AND_RECHARGE",
    ) -> tuple[LotAllocation, ...]:
        require_positive_int(amount, "amount")
        if spend_mode not in ("GIFT_AND_RECHARGE", "RECHARGE_ONLY"):
            raise ValueError("INVALID_SPEND_MODE")
        at = now or datetime.now(UTC)
        spendable_assets = (
            wallet_asset_lots.c.asset_type == AssetType.RECHARGE.value
            if spend_mode == "RECHARGE_ONLY"
            else sa.or_(
                wallet_asset_lots.c.asset_type == AssetType.RECHARGE.value,
                sa.and_(
                    wallet_asset_lots.c.asset_type == AssetType.GIFT.value,
                    sa.or_(
                        wallet_asset_lots.c.expires_at.is_(None),
                        wallet_asset_lots.c.expires_at > at,
                    ),
                ),
            )
        )
        self._ensure_wallet(connection, account_id, lock=True)
        rows = (
            connection.execute(
                sa.select(
                    wallet_asset_lots.c.lot_id,
                    wallet_asset_lots.c.asset_type,
                    wallet_asset_lots.c.available_amount,
                    wallet_asset_lots.c.expires_at,
                    wallet_asset_lots.c.issued_at,
                )
                .where(
                    wallet_asset_lots.c.account_id == account_id,
                    wallet_asset_lots.c.available_amount > 0,
                    spendable_assets,
                )
                .with_for_update()
            )
            .mappings()
            .all()
        )
        rows = sorted(
            rows,
            key=lambda row: (
                row["asset_type"] != AssetType.GIFT.value,
                row["expires_at"] is None,
                row["expires_at"],
                row["issued_at"],
                row["lot_id"],
            ),
        )
        if sum(int(row["available_amount"]) for row in rows) < amount:
            raise InsufficientFunds("INSUFFICIENT_FUNDS")
        journal_id = self._journal(connection, account_id, "SPEND")
        remaining = amount
        allocations: list[LotAllocation] = []
        deltas = {AssetType.RECHARGE.value: 0, AssetType.GIFT.value: 0}
        for row in rows:
            if not remaining:
                break
            consumed = min(remaining, int(row["available_amount"]))
            remaining -= consumed
            allocations.append(LotAllocation(row["lot_id"], AssetType(row["asset_type"]), consumed))
            deltas[row["asset_type"]] += consumed
            connection.execute(
                wallet_asset_lots.update()
                .where(wallet_asset_lots.c.lot_id == row["lot_id"])
                .values(available_amount=wallet_asset_lots.c.available_amount - consumed)
            )
            self._entry(connection, journal_id, account_id, row["asset_type"], -consumed, reason)
            connection.execute(
                wallet_lot_allocations.insert().values(
                    lot_id=row["lot_id"],
                    journal_id=journal_id,
                    allocation_type="SPEND",
                    amount=consumed,
                )
            )
        self._change_balance(
            connection,
            account_id,
            -deltas[AssetType.RECHARGE.value],
            -deltas[AssetType.GIFT.value],
        )
        return tuple(allocations)

    def _grant(
        self,
        account_id: str,
        asset_type: AssetType,
        amount: int,
        origin: str,
        expires_at: datetime | None,
        reason: str,
        source_ref: str | None = None,
        issued_at: datetime | None = None,
    ) -> WalletAssetLot:
        require_positive_int(amount, "amount")
        at = issued_at or datetime.now(UTC)
        lot_id = f"lot-{uuid4().hex}"
        with self.engine.begin() as connection:
            self._grant_in_connection(
                connection,
                account_id,
                asset_type,
                amount,
                origin,
                expires_at,
                reason,
                source_ref,
                issued_at,
                lot_id=lot_id,
                at=at,
            )
        return WalletAssetLot(
            lot_id, account_id, asset_type, origin, amount, at, expires_at, source_ref, amount
        )

    def _grant_in_connection(
        self,
        connection: Connection,
        account_id: str,
        asset_type: AssetType,
        amount: int,
        origin: str,
        expires_at: datetime | None,
        reason: str,
        source_ref: str | None = None,
        issued_at: datetime | None = None,
        *,
        lot_id: str | None = None,
        at: datetime | None = None,
    ) -> WalletAssetLot:
        require_positive_int(amount, "amount")
        issued = at or issued_at or datetime.now(UTC)
        actual_lot_id = lot_id or f"lot-{uuid4().hex}"
        self._ensure_wallet(connection, account_id, lock=True)
        journal_id = self._journal(connection, account_id, "GRANT")
        connection.execute(
            wallet_asset_lots.insert().values(
                lot_id=actual_lot_id,
                account_id=account_id,
                asset_type=asset_type.value,
                origin=origin,
                available_amount=amount,
                issued_at=issued,
                expires_at=expires_at,
                source_ref=source_ref,
                issued_amount=amount,
            )
        )
        self._entry(connection, journal_id, account_id, asset_type.value, amount, reason)
        self._change_balance(
            connection,
            account_id,
            amount if asset_type is AssetType.RECHARGE else 0,
            amount if asset_type is AssetType.GIFT else 0,
        )
        return WalletAssetLot(
            actual_lot_id,
            account_id,
            asset_type,
            origin,
            amount,
            issued,
            expires_at,
            source_ref,
            amount,
        )

    def _ensure_wallet(
        self, connection: sa.Connection, account_id: str, lock: bool = False
    ) -> None:
        query = sa.select(wallet_accounts.c.account_id).where(
            wallet_accounts.c.account_id == account_id
        )
        if lock:
            query = query.with_for_update()
        if connection.execute(query).scalar_one_or_none() is None:
            try:
                with connection.begin_nested():
                    connection.execute(
                        wallet_accounts.insert().values(
                            account_id=account_id,
                            recharge_coin=0,
                            gift_coin=0,
                            created_at=datetime.now(UTC),
                        )
                    )
            except IntegrityError:
                # Another transaction created the unique account row first.
                pass

    def _journal(self, connection: sa.Connection, account_id: str, journal_type: str) -> int:
        connection.execute(
            wallet_journals.insert().values(
                account_id=account_id,
                journal_type=journal_type,
                idempotency_key=None,
                created_at=datetime.now(UTC),
            )
        )
        last_id_query = (
            "SELECT last_insert_rowid()"
            if connection.dialect.name == "sqlite"
            else "SELECT LAST_INSERT_ID()"
        )
        return int(connection.execute(sa.text(last_id_query)).scalar_one())

    def _entry(
        self,
        connection: sa.Connection,
        journal_id: int,
        account_id: str,
        asset_type: str,
        amount: int,
        reason: str,
    ) -> None:
        connection.execute(
            wallet_entries.insert().values(
                journal_id=journal_id,
                account_id=account_id,
                asset_type=asset_type,
                amount=amount,
                reason=reason,
                created_at=datetime.now(UTC),
            )
        )

    def _change_balance(
        self, connection: sa.Connection, account_id: str, recharge: int, gift: int
    ) -> None:
        connection.execute(
            wallet_accounts.update()
            .where(wallet_accounts.c.account_id == account_id)
            .values(
                recharge_coin=wallet_accounts.c.recharge_coin + recharge,
                gift_coin=wallet_accounts.c.gift_coin + gift,
            )
        )
