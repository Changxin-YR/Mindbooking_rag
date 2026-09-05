"""Payment and payout provider ports with deterministic sandbox adapters."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from hmac import compare_digest
from hmac import new as hmac_new
from types import MappingProxyType
from typing import Protocol
from urllib.parse import quote


class ProviderStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    PROCESSING = "PROCESSING"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class Checkout:
    payment_no: str
    provider: str
    amount_cents: int
    currency: str
    checkout_url: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Payout:
    payout_no: str
    provider: str
    amount_cents: int
    currency: str
    destination: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    provider: str
    event_type: str
    event_id: str
    reference_id: str
    provider_transaction_id: str
    status: ProviderStatus
    amount_cents: int
    currency: str
    occurred_at: datetime
    available_at: datetime
    signature: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def verify_signature(self, secret: str) -> bool:
        return compare_digest(self.signature, _event_signature(secret, self))


class PaymentProvider(Protocol):
    def create_checkout(
        self, payment_no: str, amount_cents: int, currency: str = "CNY"
    ) -> Checkout: ...

    def generate_callback_event(
        self,
        payment_no: str,
        status: ProviderStatus | str = ProviderStatus.SUCCESS,
        *,
        event_id: str | None = None,
        delay_seconds: int = 0,
    ) -> ProviderEvent: ...

    def simulate_callback(
        self,
        payment_no: str,
        status: ProviderStatus | str = ProviderStatus.SUCCESS,
        *,
        event_id: str | None = None,
        delay_seconds: int = 0,
        duplicate: bool = False,
    ) -> tuple[ProviderEvent, ...]: ...


class PayoutProvider(Protocol):
    def create_payout(
        self, payout_no: str, amount_cents: int, currency: str, destination: str
    ) -> Payout: ...

    def generate_callback_event(
        self,
        payout_no: str,
        status: ProviderStatus | str = ProviderStatus.SUCCESS,
        *,
        event_id: str | None = None,
        delay_seconds: int = 0,
    ) -> ProviderEvent: ...

    def simulate_callback(
        self,
        payout_no: str,
        status: ProviderStatus | str = ProviderStatus.SUCCESS,
        *,
        event_id: str | None = None,
        delay_seconds: int = 0,
        duplicate: bool = False,
    ) -> tuple[ProviderEvent, ...]: ...


class _SandboxProvider:
    _event_type: str

    def __init__(
        self,
        secret: str,
        provider_name: str = "SANDBOX",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not secret:
            raise ValueError("provider secret must not be empty")
        if not provider_name:
            raise ValueError("provider name must not be empty")
        self.secret = secret
        self.provider_name = provider_name
        self._clock = clock or (lambda: datetime.now(UTC))
        self._references: dict[str, tuple[int, str]] = {}
        self._event_sequence = 0

    def _register(self, reference_id: str, amount_cents: int, currency: str) -> datetime:
        _require_text(reference_id, "reference_id")
        _require_positive_int(amount_cents, "amount_cents")
        normalized_currency = _currency(currency)
        previous = self._references.get(reference_id)
        if previous is not None and previous != (amount_cents, normalized_currency):
            raise ValueError("PROVIDER_REFERENCE_CONFLICT")
        self._references[reference_id] = (amount_cents, normalized_currency)
        return self._clock()

    def _event(
        self,
        reference_id: str,
        status: ProviderStatus | str,
        event_id: str | None,
        delay_seconds: int,
    ) -> ProviderEvent:
        try:
            normalized_status = ProviderStatus(status)
        except ValueError as exc:
            raise ValueError("UNSUPPORTED_PROVIDER_STATUS") from exc
        if type(delay_seconds) is not int or delay_seconds < 0:
            raise ValueError("delay_seconds must be a non-negative integer")
        try:
            amount_cents, currency = self._references[reference_id]
        except KeyError as exc:
            raise ValueError("PROVIDER_REFERENCE_NOT_FOUND") from exc
        if event_id is None:
            self._event_sequence += 1
            reference_digest = sha256(reference_id.encode("utf-8")).hexdigest()[:24]
            normalized_event_id = (
                f"{self.provider_name.lower()}-{reference_digest}-event-{self._event_sequence}"
            )
        else:
            normalized_event_id = _require_text(event_id, "event_id")
        occurred_at = self._clock()
        available_at = occurred_at + timedelta(seconds=delay_seconds)
        event = ProviderEvent(
            provider=self.provider_name,
            event_type=self._event_type,
            event_id=normalized_event_id,
            reference_id=reference_id,
            provider_transaction_id=f"{self.provider_name.lower()}-tx-{reference_id}",
            status=normalized_status,
            amount_cents=amount_cents,
            currency=currency,
            occurred_at=occurred_at,
            available_at=available_at,
            signature="",
        )
        return ProviderEvent(
            provider=event.provider,
            event_type=event.event_type,
            event_id=event.event_id,
            reference_id=event.reference_id,
            provider_transaction_id=event.provider_transaction_id,
            status=event.status,
            amount_cents=event.amount_cents,
            currency=event.currency,
            occurred_at=event.occurred_at,
            available_at=event.available_at,
            signature=_event_signature(self.secret, event),
        )

    def generate_callback_event(
        self,
        reference_id: str,
        status: ProviderStatus | str = ProviderStatus.SUCCESS,
        *,
        event_id: str | None = None,
        delay_seconds: int = 0,
    ) -> ProviderEvent:
        return self._event(reference_id, status, event_id, delay_seconds)

    def simulate_callback(
        self,
        reference_id: str,
        status: ProviderStatus | str = ProviderStatus.SUCCESS,
        *,
        event_id: str | None = None,
        delay_seconds: int = 0,
        duplicate: bool = False,
    ) -> tuple[ProviderEvent, ...]:
        event = self._event(reference_id, status, event_id, delay_seconds)
        return (event, event) if duplicate else (event,)


class SandboxPaymentProvider(_SandboxProvider):
    _event_type = "PAYMENT"

    def create_checkout(
        self, payment_no: str, amount_cents: int, currency: str = "CNY"
    ) -> Checkout:
        created_at = self._register(payment_no, amount_cents, currency)
        normalized_currency = _currency(currency)
        return Checkout(
            payment_no=payment_no,
            provider=self.provider_name,
            amount_cents=amount_cents,
            currency=normalized_currency,
            checkout_url=f"https://sandbox.example/checkout/{quote(payment_no, safe='')}",
            created_at=created_at,
        )


class SandboxPayoutProvider(_SandboxProvider):
    _event_type = "PAYOUT"

    def create_payout(
        self, payout_no: str, amount_cents: int, currency: str, destination: str
    ) -> Payout:
        created_at = self._register(payout_no, amount_cents, currency)
        return Payout(
            payout_no=payout_no,
            provider=self.provider_name,
            amount_cents=amount_cents,
            currency=_currency(currency),
            destination=_require_text(destination, "destination"),
            created_at=created_at,
        )


MockPaymentProvider = SandboxPaymentProvider
MockPayoutProvider = SandboxPayoutProvider


def _event_signature(secret: str, event: ProviderEvent) -> str:
    canonical = "\n".join(
        (
            event.provider,
            event.event_type,
            event.event_id,
            event.reference_id,
            event.provider_transaction_id,
            str(event.amount_cents),
            event.currency,
            event.status.value,
            event.occurred_at.isoformat(),
            event.available_at.isoformat(),
        )
    )
    return hmac_new(secret.encode("utf-8"), canonical.encode("utf-8"), sha256).hexdigest()


def _require_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _require_positive_int(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _currency(value: str) -> str:
    normalized = _require_text(value, "currency").upper()
    if len(normalized) != 3 or not normalized.isascii() or not normalized.isalpha():
        raise ValueError("currency must be a 3-letter code")
    return normalized
