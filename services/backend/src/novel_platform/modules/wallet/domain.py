from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class AssetType(StrEnum):
    RECHARGE = "RECHARGE_COIN"
    GIFT = "GIFT_COIN"


@dataclass(frozen=True, slots=True)
class WalletBalance:
    recharge_coin: int = 0
    gift_coin: int = 0

    @property
    def total_coin(self) -> int:
        return self.recharge_coin + self.gift_coin


@dataclass(frozen=True, slots=True)
class WalletEntry:
    entry_id: str
    account_id: str
    asset_type: AssetType
    amount: int
    reason: str


@dataclass(slots=True)
class WalletAssetLot:
    lot_id: str
    account_id: str
    asset_type: AssetType
    origin: str
    available_amount: int
    issued_at: datetime
    expires_at: datetime | None = None
    source_ref: str | None = None
    issued_amount: int = 0


@dataclass(frozen=True, slots=True)
class WalletSourceSnapshot:
    consumed_recharge_coin: int
    consumed_promo_gift_coin: int
    naturally_expired_promo_gift_coin: int
    remaining_recharge_coin: int
    remaining_active_promo_gift_coin: int


@dataclass(frozen=True, slots=True)
class LotAllocation:
    lot_id: str
    asset_type: AssetType
    amount: int


class WalletPort(Protocol):
    def balance(self, account_id: str, now: datetime | None = None) -> WalletBalance: ...

    def source_snapshot(
        self, account_id: str, source_ref: str, now: datetime | None = None
    ) -> WalletSourceSnapshot: ...

    def recover_source_assets(
        self, account_id: str, source_ref: str, now: datetime | None = None
    ) -> None: ...

    def spend(
        self, account_id: str, amount: int, now: datetime | None = None, reason: str = "PURCHASE"
    ) -> tuple[LotAllocation, ...]: ...

    def grant_recharge_coin(
        self, account_id: str, amount: int, reason: str = "RECHARGE", source_ref: str | None = None
    ) -> WalletAssetLot: ...

    def grant_gift_coin(
        self,
        account_id: str,
        amount: int,
        origin: str,
        expires_at: datetime | None,
        issued_at: datetime | None = None,
        source_ref: str | None = None,
    ) -> WalletAssetLot: ...


def require_positive_int(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value
