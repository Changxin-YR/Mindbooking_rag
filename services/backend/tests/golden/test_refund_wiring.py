from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import sleep, time

from fastapi.testclient import TestClient

from novel_platform.main import create_app
from novel_platform.modules.commerce.application import CommerceService
from novel_platform.modules.commerce.refund import (
    RefundCalculationSnapshot,
    RefundService,
    RefundSourceSnapshot,
)
from novel_platform.modules.wallet.api import payment_callback_signature
from novel_platform.modules.wallet.application import WalletService


def test_commerce_refund_source_traces_only_the_bound_recharge_lots() -> None:
    wallet = WalletService()
    commerce = CommerceService(wallet)
    first = commerce.create_recharge("acct-1", "RECHARGE_100_PROMO", "FAKE")
    second = commerce.create_recharge("acct-1", "RECHARGE_100_PROMO", "FAKE")
    commerce.handle_payment_callback("FAKE", "event-1", first.payment_order.payment_no)
    commerce.handle_payment_callback("FAKE", "event-2", second.payment_order.payment_no)
    wallet.spend("acct-1", 500, reason="CHAPTER_PURCHASE")

    snapshot = commerce.refund_source(
        first.payment_order.payment_no, first.recharge_order.recharge_no
    )

    assert snapshot.consumed_recharge_coin == 0
    assert snapshot.consumed_promo_gift_coin == 500
    assert snapshot.remaining_recharge_coin == 10_000
    assert snapshot.remaining_active_promo_gift_coin == 1_500


def test_live_refund_route_uses_commerce_ports_and_recovers_source_assets() -> None:
    client = TestClient(create_app())
    account = client.post(
        "/api/v1/iam/accounts",
        json={"phone": "13800138020", "password": "Correct#123"},
    ).json()["account_id"]
    token = client.post(
        "/api/v1/iam/sessions",
        json={"phone": "13800138020", "password": "Correct#123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    real_name = client.post(
        f"/api/v1/iam/accounts/{account}/real-name",
        json={"name": "测试用户", "identity_document": "11010119900101001X"},
        headers=headers,
    )
    assert real_name.status_code == 201
    checkout = client.post(
        "/api/v1/recharge",
        json={
            "account_id": account,
            "product_code": "RECHARGE_100_PROMO",
            "channel": "FAKE",
        },
        headers=headers,
    ).json()
    callback_timestamp = str(int(time()))
    callback = client.post(
        "/api/v1/recharge/callback",
        json={
            "provider": "FAKE",
            "event_id": "event-1",
            "payment_no": checkout["payment_no"],
        },
        headers={
            "X-Payment-Timestamp": callback_timestamp,
            "X-Payment-Signature": payment_callback_signature(
                "development-only-payment-callback-secret",
                "FAKE",
                "event-1",
                checkout["payment_no"],
                callback_timestamp,
            ),
        },
    )
    assert callback.status_code == 200

    response = client.post(
        "/api/v1/refunds",
        json={
            "payment_no": checkout["payment_no"],
            "recharge_no": checkout["recharge_no"],
            "refund_reference": "REF-1",
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["refundable_cents"] == 10_000
    assert response.json()["recoverable_recharge_coin"] == 10_000
    assert response.json()["recoverable_promo_gift_coin"] == 2_000
    assert response.json()["executed"] is True
    assert client.get("/api/v1/wallet", params={"account_id": account}, headers=headers).json() == {
        "account_id": account,
        "recharge_coin": 0,
        "gift_coin": 0,
        "total_coin": 0,
    }


def test_payment_callback_requires_a_fresh_valid_signature() -> None:
    client = TestClient(create_app())
    account = client.post(
        "/api/v1/iam/accounts",
        json={"phone": "13800138044", "password": "Correct#123"},
    ).json()["account_id"]
    token = client.post(
        "/api/v1/iam/sessions", json={"phone": "13800138044", "password": "Correct#123"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        f"/api/v1/iam/accounts/{account}/real-name",
        json={"name": "测试用户", "identity_document": "11010119900101002X"},
        headers=headers,
    )
    checkout = client.post(
        "/api/v1/recharge",
        json={"account_id": account, "product_code": "RECHARGE_100", "channel": "FAKE"},
        headers=headers,
    ).json()
    timestamp = str(int(time()))
    payload = {
        "provider": "FAKE",
        "event_id": "event-signed",
        "payment_no": checkout["payment_no"],
    }

    assert client.post("/api/v1/recharge/callback", json=payload).status_code == 401
    assert (
        client.post(
            "/api/v1/recharge/callback",
            json=payload,
            headers={"X-Payment-Timestamp": timestamp, "X-Payment-Signature": "wrong"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/recharge/callback",
            json=payload,
            headers={
                "X-Payment-Timestamp": timestamp,
                "X-Payment-Signature": payment_callback_signature(
                    "development-only-payment-callback-secret",
                    payload["provider"],
                    payload["event_id"],
                    payload["payment_no"],
                    timestamp,
                ),
            },
        ).status_code
        == 200
    )


def test_refund_reference_is_idempotent_under_concurrency() -> None:
    recovered: list[RefundCalculationSnapshot] = []
    source = RefundSourceSnapshot("PAY-1", "RECH-1", 100, 0, 0, 0, 0, 100, 0)

    def recover(snapshot: RefundCalculationSnapshot) -> None:
        recovered.append(snapshot)
        sleep(0.01)

    service = RefundService(lambda _payment, _recharge: source, recover)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: service.refund("PAY-1", "RECH-1", "REF-1"),
                range(2),
            )
        )

    assert results[0] == results[1]
    assert len(recovered) == 1


def test_refund_rejects_incomplete_source_lots() -> None:
    wallet = WalletService()
    commerce = CommerceService(wallet)
    checkout = commerce.create_recharge("acct-1", "RECHARGE_100_PROMO", "FAKE")
    commerce.handle_payment_callback("FAKE", "event-1", checkout.payment_order.payment_no)
    wallet._lots.clear()

    service = RefundService(commerce.refund_source, commerce.recover_refund_assets)

    try:
        service.refund(
            checkout.payment_order.payment_no,
            checkout.recharge_order.recharge_no,
            "REF-1",
        )
    except ValueError as exc:
        assert str(exc) == "REFUND_SOURCE_NOT_FOUND"
    else:
        raise AssertionError("incomplete source lots must reject refund")


def test_refund_recovery_is_idempotent_across_service_instances() -> None:
    wallet = WalletService()
    commerce = CommerceService(wallet)
    checkout = commerce.create_recharge("acct-1", "RECHARGE_100_PROMO", "FAKE")
    commerce.handle_payment_callback("FAKE", "event-1", checkout.payment_order.payment_no)
    lookup_barrier = Barrier(2)

    def lookup(payment_no: str, recharge_no: str) -> RefundSourceSnapshot:
        source = commerce.refund_source(payment_no, recharge_no)
        lookup_barrier.wait()
        return source

    services = [
        RefundService(lookup, commerce.recover_refund_assets),
        RefundService(lookup, commerce.recover_refund_assets),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda service: service.refund(
                    checkout.payment_order.payment_no,
                    checkout.recharge_order.recharge_no,
                    "REF-1",
                ),
                services,
            )
        )

    assert results[0].refundable_cents == 10_000
    assert results[1].refundable_cents == 10_000
    assert len(wallet.entries("acct-1")) == 4
    assert (
        commerce.refund_source(
            checkout.payment_order.payment_no,
            checkout.recharge_order.recharge_no,
        ).prior_refunded_cents
        == 10_000
    )
