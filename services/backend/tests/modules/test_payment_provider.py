from datetime import timedelta

from novel_platform.modules.payment.provider import (
    ProviderStatus,
    SandboxPaymentProvider,
    SandboxPayoutProvider,
)


def test_payment_provider_creates_checkout_and_signed_event_without_wallet_access() -> None:
    provider = SandboxPaymentProvider(secret="sandbox-secret")

    checkout = provider.create_checkout("PAY-1", amount_cents=1_000, currency="CNY")
    event = provider.generate_callback_event("PAY-1", ProviderStatus.SUCCESS)

    assert checkout.payment_no == "PAY-1"
    assert checkout.amount_cents == 1_000
    assert checkout.checkout_url.startswith("https://sandbox.example/checkout/")
    assert event.reference_id == "PAY-1"
    assert event.status is ProviderStatus.SUCCESS
    assert event.verify_signature("sandbox-secret")
    assert not hasattr(provider, "wallet")
    assert not hasattr(provider, "balance")


def test_payment_provider_default_event_ids_are_unique_across_provider_instances() -> None:
    first = SandboxPaymentProvider(secret="sandbox-secret")
    second = SandboxPaymentProvider(secret="sandbox-secret")
    first.create_checkout("PAY-INSTANCE-1", amount_cents=1_000)
    second.create_checkout("PAY-INSTANCE-2", amount_cents=1_000)

    assert (
        first.generate_callback_event("PAY-INSTANCE-1").event_id
        != second.generate_callback_event("PAY-INSTANCE-2").event_id
    )


def test_payment_provider_simulates_all_callback_statuses() -> None:
    provider = SandboxPaymentProvider(secret="sandbox-secret")
    provider.create_checkout("PAY-2", amount_cents=2_000)

    statuses = (
        ProviderStatus.SUCCESS,
        ProviderStatus.FAILED,
        ProviderStatus.CANCELLED,
        ProviderStatus.TIMEOUT,
        ProviderStatus.PROCESSING,
        ProviderStatus.REJECTED,
    )

    events = tuple(provider.generate_callback_event("PAY-2", status) for status in statuses)

    assert tuple(event.status for event in events) == statuses
    assert all(event.event_type == "PAYMENT" for event in events)


def test_payment_provider_can_emit_duplicate_and_delayed_callbacks() -> None:
    provider = SandboxPaymentProvider(secret="sandbox-secret")
    provider.create_checkout("PAY-3", amount_cents=3_000)

    events = provider.simulate_callback(
        "PAY-3", ProviderStatus.PROCESSING, delay_seconds=30, duplicate=True
    )

    assert len(events) == 2
    assert events[0] == events[1]
    assert events[0].available_at - events[0].occurred_at == timedelta(seconds=30)


def test_payout_provider_emits_standardized_signed_event() -> None:
    provider = SandboxPayoutProvider(secret="sandbox-secret")

    payout = provider.create_payout(
        "WD-1", amount_cents=5_000, currency="CNY", destination="bank-account-1"
    )
    event = provider.generate_callback_event("WD-1", ProviderStatus.REJECTED)

    assert payout.payout_no == "WD-1"
    assert payout.destination == "bank-account-1"
    assert event.event_type == "PAYOUT"
    assert event.status is ProviderStatus.REJECTED
    assert event.verify_signature("sandbox-secret")
