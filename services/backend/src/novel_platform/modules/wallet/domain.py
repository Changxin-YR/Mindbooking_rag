from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


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


@dataclass(frozen=True, slots=True)
class LotAllocation:
    lot_id: str
    asset_type: AssetType
    amount: int


def require_positive_int(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value
