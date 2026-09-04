from dataclasses import dataclass
from enum import StrEnum


class RiskSignalStatus(StrEnum):
    OBSERVE = "OBSERVE"
    FROZEN = "FROZEN"


@dataclass(frozen=True, slots=True)
class LoginRiskSignal:
    id: str
    account_id: str
    device_id: str
    browser: str
    operating_system: str
    ip: str
    region: str
    user_agent: str
    status: RiskSignalStatus = RiskSignalStatus.OBSERVE


@dataclass(slots=True)
class WatchlistEntry:
    id: str
    target_type: str
    target_value: str
    reason: str
    case_id: str
    status: str = "ACTIVE"
    release_reason: str | None = None
    evidence_id: str | None = None


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
