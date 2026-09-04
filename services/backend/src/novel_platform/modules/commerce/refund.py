"""Reference-bound refund calculation and execution boundary."""

from collections.abc import Callable
from dataclasses import dataclass, fields, replace


@dataclass(frozen=True, slots=True)
class RefundSourceSnapshot:
    payment_no: str
    recharge_no: str
    original_paid_cents: int
    consumed_recharge_coin: int
    consumed_promo_gift_coin: int
    naturally_expired_promo_gift_coin: int
    prior_refunded_cents: int
    remaining_recharge_coin: int
    remaining_active_promo_gift_coin: int


@dataclass(frozen=True, slots=True)
class RefundCalculationSnapshot:
    payment_no: str
    recharge_no: str
    refund_reference: str
    original_paid_cents: int
    consumed_recharge_coin: int
    consumed_promo_gift_coin: int
    naturally_expired_promo_gift_coin: int
    prior_refunded_cents: int
    refundable_cents: int
    recoverable_recharge_coin: int
    recoverable_promo_gift_coin: int
    executed: bool = False


def _require_non_negative_int(value: int, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def calculate_refund(
    source: RefundSourceSnapshot, refund_reference: str = ""
) -> RefundCalculationSnapshot:
    """Calculate cents and same-order asset recovery using the fixed 1:1 rate."""
    for field in fields(source)[2:]:
        _require_non_negative_int(getattr(source, field.name), field.name)
    refundable = max(
        0,
        source.original_paid_cents
        - source.consumed_recharge_coin
        - source.consumed_promo_gift_coin
        - source.naturally_expired_promo_gift_coin
        - source.prior_refunded_cents,
    )
    return RefundCalculationSnapshot(
        source.payment_no,
        source.recharge_no,
        refund_reference,
        source.original_paid_cents,
        source.consumed_recharge_coin,
        source.consumed_promo_gift_coin,
        source.naturally_expired_promo_gift_coin,
        source.prior_refunded_cents,
        refundable,
        source.remaining_recharge_coin,
        source.remaining_active_promo_gift_coin,
    )


SourceLookup = Callable[[str, str], RefundSourceSnapshot]
AssetRecovery = Callable[[RefundCalculationSnapshot], None]


class RefundService:
    def __init__(self, source_lookup: SourceLookup, recover_assets: AssetRecovery) -> None:
        self._source_lookup = source_lookup
        self._recover_assets = recover_assets
        self._completed: dict[str, RefundCalculationSnapshot] = {}

    def refund(
        self, payment_no: str, recharge_no: str, refund_reference: str
    ) -> RefundCalculationSnapshot:
        for value, name in (
            (payment_no, "payment_no"),
            (recharge_no, "recharge_no"),
            (refund_reference, "refund_reference"),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} is required")
        previous = self._completed.get(refund_reference)
        if previous is not None:
            if (previous.payment_no, previous.recharge_no) != (payment_no, recharge_no):
                raise ValueError("REFUND_REFERENCE_CONFLICT")
            return previous

        source = self._source_lookup(payment_no, recharge_no)
        if (source.payment_no, source.recharge_no) != (payment_no, recharge_no):
            raise ValueError("REFUND_SOURCE_MISMATCH")
        calculation = calculate_refund(source, refund_reference)
        if calculation.refundable_cents > 0:
            calculation = replace(calculation, executed=True)
            self._recover_assets(calculation)
        self._completed[refund_reference] = calculation
        return calculation
