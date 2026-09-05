from datetime import UTC, datetime
from threading import RLock

from novel_platform.modules.wallet.domain import (
    AssetType,
    LotAllocation,
    WalletAssetLot,
    WalletBalance,
    WalletEntry,
    WalletSourceSnapshot,
    require_positive_int,
)


class InsufficientFunds(ValueError):
    """The account cannot spend the requested number of coins."""


class WalletService:
    def __init__(self) -> None:
        self._balances: dict[str, WalletBalance] = {}
        self._lots: dict[str, WalletAssetLot] = {}
        self._entries: dict[str, list[WalletEntry]] = {}
        self._lot_sequence = 0
        self._entry_sequence = 0
        self._lock = RLock()

    def balance(self, account_id: str, now: datetime | None = None) -> WalletBalance:
        with self._lock:
            balance = self._balances.get(account_id, WalletBalance())
            at = now or datetime.now(UTC)
            expired = sum(
                lot.available_amount
                for lot in self._lots.values()
                if lot.account_id == account_id
                and lot.asset_type is AssetType.GIFT
                and lot.expires_at is not None
                and lot.expires_at <= at
            )
            return WalletBalance(balance.recharge_coin, max(0, balance.gift_coin - expired))

    def entries(self, account_id: str) -> tuple[WalletEntry, ...]:
        with self._lock:
            return tuple(self._entries.get(account_id, ()))

    def grant_recharge_coin(
        self,
        account_id: str,
        amount: int,
        reason: str = "RECHARGE",
        source_ref: str | None = None,
    ) -> WalletAssetLot:
        return self._grant(
            account_id, AssetType.RECHARGE, amount, "RECHARGE", None, reason, source_ref=source_ref
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
            issued_at,
            source_ref,
        )

    def source_snapshot(
        self, account_id: str, source_ref: str, now: datetime | None = None
    ) -> WalletSourceSnapshot:
        at = now or datetime.now(UTC)
        with self._lock:
            lots = [
                lot
                for lot in self._lots.values()
                if lot.account_id == account_id and lot.source_ref == source_ref
            ]
            recharge = [lot for lot in lots if lot.asset_type is AssetType.RECHARGE]
            promo_gifts = [
                lot for lot in lots if lot.asset_type is AssetType.GIFT and lot.origin == "PROMO"
            ]

            def issued(lot: WalletAssetLot) -> int:
                return lot.issued_amount or lot.available_amount

            return WalletSourceSnapshot(
                sum(issued(lot) - lot.available_amount for lot in recharge),
                sum(issued(lot) - lot.available_amount for lot in promo_gifts),
                sum(
                    lot.available_amount
                    for lot in promo_gifts
                    if lot.expires_at is not None and lot.expires_at <= at
                ),
                sum(lot.available_amount for lot in recharge),
                sum(
                    lot.available_amount
                    for lot in promo_gifts
                    if lot.expires_at is None or lot.expires_at > at
                ),
            )

    def recover_source_assets(
        self, account_id: str, source_ref: str, now: datetime | None = None
    ) -> None:
        at = now or datetime.now(UTC)
        with self._lock:
            lots = [
                lot
                for lot in self._lots.values()
                if lot.account_id == account_id
                and lot.source_ref == source_ref
                and lot.available_amount > 0
                and (
                    lot.asset_type is AssetType.RECHARGE
                    or (
                        lot.asset_type is AssetType.GIFT
                        and lot.origin == "PROMO"
                        and (lot.expires_at is None or lot.expires_at > at)
                    )
                )
            ]
            for lot in lots:
                amount = lot.available_amount
                lot.available_amount = 0
                self._append_entry(account_id, lot.asset_type, -amount, "REFUND_RECOVERY")

    def spend(
        self,
        account_id: str,
        amount: int,
        now: datetime | None = None,
        reason: str = "PURCHASE",
    ) -> tuple[LotAllocation, ...]:
        require_positive_int(amount, "amount")
        now = now or datetime.now(UTC)
        with self._lock:
            balance = self.balance(account_id, now)
            if balance.total_coin < amount:
                raise InsufficientFunds("INSUFFICIENT_FUNDS")

            lots = self._spendable_lots(account_id, now)
            remaining = amount
            allocations: list[LotAllocation] = []
            for lot in lots:
                if remaining == 0:
                    break
                consumed = min(lot.available_amount, remaining)
                allocations.append(LotAllocation(lot.lot_id, lot.asset_type, consumed))
                remaining -= consumed
            if remaining:
                raise InsufficientFunds("INSUFFICIENT_FUNDS")

            for allocation in allocations:
                lot = self._lots[allocation.lot_id]
                lot.available_amount -= allocation.amount
                self._append_entry(account_id, lot.asset_type, -allocation.amount, reason)
            return tuple(allocations)

    def _grant(
        self,
        account_id: str,
        asset_type: AssetType,
        amount: int,
        origin: str,
        expires_at: datetime | None,
        reason: str,
        issued_at: datetime | None = None,
        source_ref: str | None = None,
    ) -> WalletAssetLot:
        require_positive_int(amount, "amount")
        with self._lock:
            self._lot_sequence += 1
            lot = WalletAssetLot(
                lot_id=f"lot-{self._lot_sequence}",
                account_id=account_id,
                asset_type=asset_type,
                origin=origin,
                available_amount=amount,
                issued_at=issued_at or datetime.now(UTC),
                expires_at=expires_at,
                source_ref=source_ref,
                issued_amount=amount,
            )
            self._lots[lot.lot_id] = lot
            self._append_entry(account_id, asset_type, amount, reason)
            return lot

    def _append_entry(
        self, account_id: str, asset_type: AssetType, amount: int, reason: str
    ) -> None:
        self._entry_sequence += 1
        entry = WalletEntry(f"entry-{self._entry_sequence}", account_id, asset_type, amount, reason)
        self._entries.setdefault(account_id, []).append(entry)
        balance = self._balances.get(account_id, WalletBalance())
        if asset_type is AssetType.RECHARGE:
            balance = WalletBalance(balance.recharge_coin + amount, balance.gift_coin)
        else:
            balance = WalletBalance(balance.recharge_coin, balance.gift_coin + amount)
        if balance.recharge_coin < 0 or balance.gift_coin < 0:
            raise InsufficientFunds("INSUFFICIENT_FUNDS")
        self._balances[account_id] = balance

    def _spendable_lots(self, account_id: str, now: datetime) -> list[WalletAssetLot]:
        gifts = [
            lot
            for lot in self._lots.values()
            if lot.account_id == account_id
            and lot.asset_type is AssetType.GIFT
            and lot.available_amount > 0
            and (lot.expires_at is None or lot.expires_at > now)
        ]
        recharge = [
            lot
            for lot in self._lots.values()
            if lot.account_id == account_id
            and lot.asset_type is AssetType.RECHARGE
            and lot.available_amount > 0
        ]
        gifts.sort(
            key=lambda lot: (lot.expires_at is None, lot.expires_at, lot.issued_at, lot.lot_id)
        )
        recharge.sort(key=lambda lot: (lot.issued_at, lot.lot_id))
        return gifts + recharge
