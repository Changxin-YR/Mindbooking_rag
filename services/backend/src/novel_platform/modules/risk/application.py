from uuid import uuid4

from novel_platform.modules.risk.domain import OrderFact, RiskSignal, RiskSignalStatus


class RiskService:
    def __init__(self) -> None:
        self._orders: dict[str, OrderFact] = {}
        self._signals: dict[str, RiskSignal] = {}

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
