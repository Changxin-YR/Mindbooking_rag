from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel_platform.modules.commerce.api import build_refund_router
from novel_platform.modules.commerce.refund import (
    RefundCalculationSnapshot,
    RefundService,
    RefundSourceSnapshot,
    calculate_refund,
)


def source(
    *,
    payment_no: str = "PAY-1",
    recharge_no: str = "RECH-1",
    original_paid_cents: int = 10_000,
    consumed_recharge_coin: int = 0,
    consumed_promo_gift_coin: int = 500,
    naturally_expired_promo_gift_coin: int = 1_000,
    prior_refunded_cents: int = 0,
    remaining_recharge_coin: int = 10_000,
    remaining_active_promo_gift_coin: int = 500,
) -> RefundSourceSnapshot:
    return RefundSourceSnapshot(
        payment_no,
        recharge_no,
        original_paid_cents,
        consumed_recharge_coin,
        consumed_promo_gift_coin,
        naturally_expired_promo_gift_coin,
        prior_refunded_cents,
        remaining_recharge_coin,
        remaining_active_promo_gift_coin,
    )


def test_frozen_refund_formula_returns_cash_and_same_source_recovery() -> None:
    snapshot = calculate_refund(source())

    assert snapshot == RefundCalculationSnapshot(
        payment_no="PAY-1",
        recharge_no="RECH-1",
        refund_reference="",
        original_paid_cents=10_000,
        consumed_recharge_coin=0,
        consumed_promo_gift_coin=500,
        naturally_expired_promo_gift_coin=1_000,
        prior_refunded_cents=0,
        refundable_cents=8_500,
        recoverable_recharge_coin=10_000,
        recoverable_promo_gift_coin=500,
        executed=False,
    )

    recovered: list[RefundCalculationSnapshot] = []
    executed = RefundService(lambda _payment, _recharge: source(), recovered.append).refund(
        "PAY-1", "RECH-1", "REF-1"
    )
    assert executed.refundable_cents == 8_500
    assert executed.recoverable_recharge_coin == 10_000
    assert executed.recoverable_promo_gift_coin == 500
    assert executed.executed is True
    assert recovered == [executed]


def test_non_positive_refund_does_not_recover_remaining_assets() -> None:
    recovered: list[RefundCalculationSnapshot] = []
    service = RefundService(
        lambda _payment, _recharge: source(
            consumed_recharge_coin=5_000,
            consumed_promo_gift_coin=5_000,
            naturally_expired_promo_gift_coin=1_000,
        ),
        recovered.append,
    )

    result = service.refund("PAY-1", "RECH-1", "REF-1")

    assert result.refundable_cents == 0
    assert result.executed is False
    assert recovered == []


def test_refund_api_rejects_client_amount_and_uses_references_only() -> None:
    service = RefundService(lambda _payment, _recharge: source(), lambda _snapshot: None)
    app = FastAPI()
    app.include_router(build_refund_router(service), prefix="/api/v1")
    client = TestClient(app)

    response = client.post(
        "/api/v1/refunds",
        json={
            "payment_no": "PAY-1",
            "recharge_no": "RECH-1",
            "refund_reference": "REF-1",
            "refund_amount_cents": 10_000,
        },
    )

    assert response.status_code == 422
