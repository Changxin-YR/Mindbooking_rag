from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel_platform.modules.commerce.application import CommerceService
from novel_platform.modules.membership.domain import AccessMode, ChapterPolicy, MembershipService
from novel_platform.modules.wallet.api import build_reader_router
from novel_platform.modules.wallet.application import InsufficientFunds, WalletService


def test_recharge_uses_server_product_price_and_fixed_coin_rate() -> None:
    wallet = WalletService()
    commerce = CommerceService(wallet)

    order = commerce.create_recharge("acct-1", "RECHARGE_100", "WECHAT")

    assert order.payment_order.paid_cents == 10_000
    assert order.recharge_order.recharge_coin == 10_000
    assert order.recharge_order.gift_coin == 0


def test_gift_spend_is_expiry_first_then_fifo() -> None:
    wallet = WalletService()
    issued_at = datetime(2026, 9, 1, tzinfo=UTC)
    wallet.grant_gift_coin("acct-1", 100, "PROMO", datetime(2026, 9, 10, tzinfo=UTC), issued_at)
    wallet.grant_gift_coin("acct-1", 100, "PROMO", datetime(2026, 9, 5, tzinfo=UTC), issued_at)
    wallet.grant_gift_coin(
        "acct-1", 100, "PROMO", datetime(2026, 9, 5, tzinfo=UTC), issued_at.replace(second=1)
    )

    allocations = wallet.spend("acct-1", 250, now=datetime(2026, 9, 4, tzinfo=UTC))

    assert [(allocation.lot_id, allocation.amount) for allocation in allocations] == [
        ("lot-2", 100),
        ("lot-3", 100),
        ("lot-1", 50),
    ]


def test_expired_gift_lot_is_not_available_in_balance() -> None:
    wallet = WalletService()
    wallet.grant_gift_coin(
        "acct-1",
        100,
        "PROMO",
        datetime(2026, 9, 1, tzinfo=UTC),
    )

    assert wallet.balance("acct-1", now=datetime(2026, 9, 2, tzinfo=UTC)).gift_coin == 0


def test_wallet_rejects_overspend_and_keeps_entries_append_only() -> None:
    wallet = WalletService()
    wallet.grant_recharge_coin("acct-1", 100)
    wallet.spend("acct-1", 70)
    entries_before = wallet.entries("acct-1")

    with pytest.raises(InsufficientFunds):
        wallet.spend("acct-1", 31)

    assert wallet.balance("acct-1").recharge_coin == 30
    assert wallet.entries("acct-1") == entries_before


def test_payment_callback_is_idempotent_by_provider_and_event() -> None:
    wallet = WalletService()
    commerce = CommerceService(wallet)
    order = commerce.create_recharge("acct-1", "RECHARGE_100", "FAKE")

    first = commerce.handle_payment_callback("FAKE", "event-1", order.payment_order.payment_no)
    second = commerce.handle_payment_callback("FAKE", "event-1", order.payment_order.payment_no)

    assert first == second
    assert wallet.balance("acct-1").recharge_coin == 10_000
    assert len(wallet.entries("acct-1")) == 1


def test_concurrent_spend_cannot_overdraw_wallet() -> None:
    wallet = WalletService()
    wallet.grant_recharge_coin("acct-1", 100)

    def spend() -> bool:
        try:
            wallet.spend("acct-1", 100)
            return True
        except InsufficientFunds:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: spend(), range(2)))

    assert results.count(True) == 1
    assert wallet.balance("acct-1").total_coin == 0


def test_duplicate_chapter_purchase_does_not_debit_again() -> None:
    wallet = WalletService()
    wallet.grant_recharge_coin("acct-1", 200)
    commerce = CommerceService(wallet)
    policy = ChapterPolicy(price_coin=100, access_mode=AccessMode.VIP_REQUIRED)

    first = commerce.purchase_chapter("acct-1", "chapter-1", policy)
    second = commerce.purchase_chapter("acct-1", "chapter-1", policy)

    assert second.purchase_no == first.purchase_no
    assert wallet.balance("acct-1").total_coin == 100
    assert len(commerce.entitlements("acct-1")) == 1


def test_same_payment_event_cannot_be_reused_for_another_payment() -> None:
    wallet = WalletService()
    commerce = CommerceService(wallet)
    first = commerce.create_recharge("acct-1", "RECHARGE_100", "FAKE")
    second = commerce.create_recharge("acct-2", "RECHARGE_100", "FAKE")
    commerce.handle_payment_callback("FAKE", "event-1", first.payment_order.payment_no)

    with pytest.raises(ValueError, match="PAYMENT_EVENT_CONFLICT"):
        commerce.handle_payment_callback("FAKE", "event-1", second.payment_order.payment_no)


def test_recharge_idempotency_key_reuses_same_request_only() -> None:
    commerce = CommerceService(WalletService())

    first = commerce.create_recharge("acct-1", "RECHARGE_100", "FAKE", idempotency_key="key-1")
    second = commerce.create_recharge("acct-1", "RECHARGE_100", "FAKE", idempotency_key="key-1")

    assert second == first
    with pytest.raises(ValueError, match="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"):
        commerce.create_recharge("acct-1", "RECHARGE_100_PROMO", "FAKE", idempotency_key="key-1")


def test_payment_and_recharge_orders_are_separate() -> None:
    order = CommerceService(WalletService()).create_recharge("acct-1", "RECHARGE_100", "FAKE")

    assert order.payment_order.payment_no != order.recharge_order.recharge_no


def test_member_free_and_limited_free_do_not_create_permanent_entitlement() -> None:
    wallet = WalletService()
    commerce = CommerceService(wallet)
    membership = MembershipService()
    wallet.grant_recharge_coin("acct-1", 100)

    for mode in (AccessMode.MEMBER_FREE, AccessMode.LIMITED_FREE):
        with pytest.raises(ValueError, match="NOT_PURCHASABLE"):
            commerce.purchase_chapter(
                "acct-1",
                "chapter-1",
                ChapterPolicy(price_coin=100, access_mode=mode),
                membership,
            )

    assert commerce.entitlements("acct-1") == ()
    assert wallet.balance("acct-1").recharge_coin == 100


def test_purchased_access_survives_membership_expiry() -> None:
    membership = MembershipService()
    membership.activate("acct-1", expires_at=datetime(2026, 9, 1, tzinfo=UTC))
    membership.add_library_book("book-1")

    assert (
        membership.access(
            "acct-1",
            "chapter-1",
            ChapterPolicy(100, AccessMode.VIP_REQUIRED),
            purchased=True,
            now=datetime(2026, 9, 2, tzinfo=UTC),
        )
        == AccessMode.PURCHASED
    )
    assert (
        membership.access(
            "acct-1",
            "chapter-1",
            ChapterPolicy(100, AccessMode.VIP_REQUIRED),
            purchased=False,
            now=datetime(2026, 9, 2, tzinfo=UTC),
        )
        == AccessMode.VIP_REQUIRED
    )


def test_reader_routes_are_explicit_and_do_not_accept_client_amounts() -> None:
    app = FastAPI()
    app.include_router(build_reader_router(CommerceService(WalletService())), prefix="/api/v1")
    client = TestClient(app)

    response = client.post(
        "/api/v1/recharge",
        json={"product_code": "RECHARGE_100", "channel": "FAKE", "paid_cents": 1},
    )

    assert response.status_code == 422
    assert client.get("/api/v1/wallet", params={"account_id": "acct-1"}).status_code == 200
