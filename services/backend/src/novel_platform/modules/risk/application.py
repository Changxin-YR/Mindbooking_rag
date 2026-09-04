from uuid import uuid4

from novel_platform.modules.risk.domain import (
    LoginRiskSignal,
    OrderFact,
    RiskSignal,
    RiskSignalStatus,
    WatchlistEntry,
)


class RiskService:
    def __init__(self) -> None:
        self._orders: dict[str, OrderFact] = {}
        self._signals: dict[str, RiskSignal] = {}
        self._logins: dict[str, LoginRiskSignal] = {}
        self._watchlist: dict[str, WatchlistEntry] = {}

    def record_order(self, order_id: str, account_id: str, amount_coin: int) -> OrderFact:
        if order_id in self._orders:
            return self._orders[order_id]
        order = OrderFact(id=order_id, account_id=account_id, amount_coin=amount_coin)
        self._orders[order.id] = order
        return order

    def get_order(self, order_id: str) -> OrderFact:
        return self._orders[order_id]

    def observe(self, account_id: str, signal_type: str, order_id: str) -> RiskSignal:
        if order_id not in self._orders:
            raise KeyError(f"order {order_id} not found")
        signal = RiskSignal(
            id=f"RSK_{uuid4().hex}",
            account_id=account_id,
            signal_type=signal_type,
            order_id=order_id,
        )
        self._signals[signal.id] = signal
        return signal

    def get_signal(self, signal_id: str) -> RiskSignal:
        return self._signals[signal_id]

    def freeze(self, signal_id: str) -> RiskSignal:
        signal = self.get_signal(signal_id)
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
            f"LOGIN_{uuid4().hex}",
            account_id,
            device_id,
            browser,
            operating_system,
            ip,
            region,
            user_agent,
        )
        self._logins[signal.id] = signal
        return signal

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
        self._watchlist[entry.id] = entry
        return entry

    def is_watchlisted(self, target_type: str, target_value: str) -> bool:
        return any(
            entry.status == "ACTIVE"
            and entry.target_type == target_type
            and entry.target_value == target_value
            for entry in self._watchlist.values()
        )

    def release_watchlist(
        self, entry_id: str, reason: str, evidence_id: str, case_id: str
    ) -> WatchlistEntry:
        entry = self._watchlist[entry_id]
        if entry.case_id != case_id or not reason.strip() or not evidence_id.strip():
            raise ValueError("WATCHLIST_RELEASE_INVALID")
        entry.status = "RELEASED"
        entry.release_reason = reason.strip()
        entry.evidence_id = evidence_id
        return entry

    def watchlist(self, entry_id: str) -> WatchlistEntry:
        return self._watchlist[entry_id]
