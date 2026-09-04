from dataclasses import dataclass
from enum import StrEnum


class RiskSignalStatus(StrEnum):
    OBSERVE = "OBSERVE"
    FROZEN = "FROZEN"


@dataclass(frozen=True, slots=True)
class OrderFact:
    id: str
    account_id: str
    amount_coin: int


@dataclass(slots=True)
class RiskSignal:
    id: str
    account_id: str
    signal_type: str
    order_id: str
    status: RiskSignalStatus = RiskSignalStatus.OBSERVE
