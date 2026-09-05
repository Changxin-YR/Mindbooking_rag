from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any, ClassVar

from novel_platform.modules.commerce.refund import (
    RefundCalculationSnapshot,
    RefundSourceSnapshot,
)
from novel_platform.modules.membership.domain import AccessMode, ChapterPolicy, MembershipService
from novel_platform.modules.payment import Checkout, PaymentProvider, ProviderEvent, ProviderStatus
from novel_platform.modules.wallet.domain import LotAllocation, WalletPort, require_positive_int


@dataclass(frozen=True, slots=True)
class Product:
    product_code: str
    paid_cents: int
    recharge_coin: int
    gift_coin: int = 0
    gift_expires_days: int | None = 30


@dataclass(frozen=True, slots=True)
class PaymentOrder:
    payment_no: str
    account_id: str
    channel: str
    paid_cents: int
    status: str = "PENDING"


@dataclass(frozen=True, slots=True)
class RechargeOrder:
    recharge_no: str
    payment_order: PaymentOrder
    recharge_coin: int
    gift_coin: int
    status: str = "PENDING_PAYMENT"
    gift_expires_days: int = 30


@dataclass(frozen=True, slots=True)
class RechargeCheckout:
    payment_order: PaymentOrder
    recharge_order: RechargeOrder
    provider_checkout: Checkout | None = None


@dataclass(frozen=True, slots=True)
class Entitlement:
    account_id: str
    chapter_id: str
    purchase_no: str
    granted_at: datetime


@dataclass(frozen=True, slots=True)
class PurchaseOrder:
    purchase_no: str
    account_id: str
    chapter_id: str
    price_coin: int
    allocations: tuple[LotAllocation, ...]
    entitlement: Entitlement


class CommerceService:
    PRODUCTS: ClassVar[dict[str, Product]] = {
        "RECHARGE_100": Product("RECHARGE_100", 10_000, 10_000),
        "RECHARGE_100_PROMO": Product("RECHARGE_100_PROMO", 10_000, 10_000, 2_000),
    }

    def __init__(
        self,
        wallet: WalletPort,
        is_real_named: Callable[[str], bool] | None = None,
        payment_provider: PaymentProvider | None = None,
        payment_provider_secret: str = "",
    ) -> None:
        self.wallet = wallet
        self._is_real_named = is_real_named
        self._payment_sequence = 0
        self._recharge_sequence = 0
        self._purchase_sequence = 0
        self._recharges: dict[str, RechargeOrder] = {}
        self._payments: dict[str, PaymentOrder] = {}
        self._callbacks: dict[tuple[str, str], str] = {}
        self._idempotency: dict[str, tuple[tuple[str, str, str], RechargeCheckout]] = {}
        self._entitlements: dict[tuple[str, str], Entitlement] = {}
        self._chapter_policies: dict[str, ChapterPolicy] = {}
        self._refunded_cents: dict[str, int] = {}
        self._refunds: dict[str, RefundCalculationSnapshot] = {}
        self._lock = RLock()
        self.payment_provider = payment_provider
        self.payment_provider_secret = payment_provider_secret
        self.record_revenue_in_transaction: Callable[[Any, str, str, int], object] | None = None

    def create_recharge(
        self,
        account_id: str,
        product_code: str,
        channel: str,
        idempotency_key: str | None = None,
    ) -> RechargeCheckout:
        with self._lock:
            if self._is_real_named is not None and not self._is_real_named(account_id):
                raise ValueError("REAL_NAME_REQUIRED")
            try:
                product = self.PRODUCTS[product_code]
            except KeyError as exc:
                raise ValueError("UNKNOWN_RECHARGE_PRODUCT") from exc
            fingerprint = (account_id, product_code, channel)
            if idempotency_key:
                previous = self._idempotency.get(idempotency_key)
                if previous:
                    if previous[0] != fingerprint:
                        raise ValueError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
                    return previous[1]
            self._payment_sequence += 1
            self._recharge_sequence += 1
            payment = PaymentOrder(
                f"PAY-{self._payment_sequence}", account_id, channel, product.paid_cents
            )
            order = RechargeOrder(
                f"RECH-{self._recharge_sequence}",
                payment,
                product.recharge_coin,
                product.gift_coin,
                "PENDING_PAYMENT",
                product.gift_expires_days or 30,
            )
            self._payments[payment.payment_no] = payment
            self._recharges[order.recharge_no] = order
            checkout = RechargeCheckout(
                payment,
                order,
                self.payment_provider.create_checkout(payment.payment_no, payment.paid_cents)
                if self.payment_provider is not None
                else None,
            )
            if idempotency_key:
                self._idempotency[idempotency_key] = (fingerprint, checkout)
            return checkout

    def handle_payment_callback(self, provider: str, event_id: str, payment_no: str) -> str:
        with self._lock:
            key = (provider, event_id)
            if key in self._callbacks:
                existing_recharge = self._recharges[self._callbacks[key]]
                if existing_recharge.payment_order.payment_no != payment_no:
                    raise ValueError("PAYMENT_EVENT_CONFLICT")
                return self._callbacks[key]
            try:
                payment = self._payments[payment_no]
            except KeyError as exc:
                raise ValueError("PAYMENT_NOT_FOUND") from exc
            recharge = next(
                order
                for order in self._recharges.values()
                if order.payment_order.payment_no == payment_no
            )
            if recharge.status == "PAID":
                self._callbacks[key] = recharge.recharge_no
                return recharge.recharge_no
            self.wallet.grant_recharge_coin(
                payment.account_id, recharge.recharge_coin, source_ref=recharge.recharge_no
            )
            if recharge.gift_coin:
                product_expiry = datetime.now(UTC).replace(microsecond=0) + timedelta(
                    days=recharge.gift_expires_days
                )
                self.wallet.grant_gift_coin(
                    payment.account_id,
                    recharge.gift_coin,
                    "PROMO",
                    product_expiry,
                    source_ref=recharge.recharge_no,
                )
            paid = PaymentOrder(
                payment.payment_no, payment.account_id, payment.channel, payment.paid_cents, "PAID"
            )
            self._payments[payment_no] = paid
            self._recharges[recharge.recharge_no] = RechargeOrder(
                recharge.recharge_no,
                paid,
                recharge.recharge_coin,
                recharge.gift_coin,
                "PAID",
                recharge.gift_expires_days,
            )
            self._callbacks[key] = recharge.recharge_no
            return recharge.recharge_no

    def handle_payment_provider_event(
        self, event: ProviderEvent, *, now: datetime | None = None
    ) -> str:
        if self.payment_provider is None or not self.payment_provider_secret:
            raise ValueError("PAYMENT_PROVIDER_NOT_CONFIGURED")
        if event.event_type != "PAYMENT":
            raise ValueError("PAYMENT_EVENT_TYPE_INVALID")
        provider_name = getattr(self.payment_provider, "provider_name", event.provider)
        if event.provider != provider_name:
            raise ValueError("PAYMENT_PROVIDER_MISMATCH")
        if not event.verify_signature(self.payment_provider_secret):
            raise ValueError("PAYMENT_SIGNATURE_INVALID")
        current = now or datetime.now(UTC)
        if event.available_at > current:
            raise ValueError("PAYMENT_EVENT_NOT_AVAILABLE")
        with self._lock:
            payment = self._payments.get(event.reference_id)
            if payment is None:
                raise ValueError("PAYMENT_NOT_FOUND")
            if payment.paid_cents != event.amount_cents or event.currency != "CNY":
                raise ValueError("PAYMENT_AMOUNT_MISMATCH")
            if event.status is ProviderStatus.SUCCESS:
                return self.handle_payment_callback(
                    event.provider, event.event_id, event.reference_id
                )
            key = (event.provider, event.event_id)
            existing = self._callbacks.get(key)
            if existing is not None:
                recharge = self._recharges[existing]
                if recharge.payment_order.payment_no != event.reference_id:
                    raise ValueError("PAYMENT_EVENT_CONFLICT")
                return existing
            recharge = next(
                order
                for order in self._recharges.values()
                if order.payment_order.payment_no == event.reference_id
            )
            if payment.status == "PAID" or recharge.status == "PAID":
                raise ValueError("PAYMENT_STATE_CONFLICT")
            updated_payment = PaymentOrder(
                payment.payment_no,
                payment.account_id,
                payment.channel,
                payment.paid_cents,
                event.status.value,
            )
            self._payments[payment.payment_no] = updated_payment
            self._recharges[recharge.recharge_no] = RechargeOrder(
                recharge.recharge_no,
                updated_payment,
                recharge.recharge_coin,
                recharge.gift_coin,
                event.status.value,
                recharge.gift_expires_days,
            )
            self._callbacks[key] = recharge.recharge_no
            return recharge.recharge_no

    def refund_source(self, payment_no: str, recharge_no: str) -> RefundSourceSnapshot:
        with self._lock:
            try:
                payment = self._payments[payment_no]
                recharge = self._recharges[recharge_no]
            except KeyError as exc:
                raise ValueError("REFUND_SOURCE_NOT_FOUND") from exc
            if (
                recharge.payment_order.payment_no != payment_no
                or recharge.payment_order.account_id != payment.account_id
                or recharge.status != "PAID"
                or payment.status != "PAID"
            ):
                raise ValueError("REFUND_SOURCE_MISMATCH")
            assets = self.wallet.source_snapshot(payment.account_id, recharge_no)
            if (
                assets.consumed_recharge_coin + assets.remaining_recharge_coin
                != recharge.recharge_coin
                or assets.consumed_promo_gift_coin
                + assets.naturally_expired_promo_gift_coin
                + assets.remaining_active_promo_gift_coin
                != recharge.gift_coin
            ):
                raise ValueError("REFUND_SOURCE_NOT_FOUND")
            return RefundSourceSnapshot(
                payment_no,
                recharge_no,
                payment.paid_cents,
                assets.consumed_recharge_coin,
                assets.consumed_promo_gift_coin,
                assets.naturally_expired_promo_gift_coin,
                self._refunded_cents.get(recharge_no, 0),
                assets.remaining_recharge_coin,
                assets.remaining_active_promo_gift_coin,
            )

    def refund_account(self, payment_no: str, recharge_no: str) -> str:
        with self._lock:
            try:
                payment = self._payments[payment_no]
                recharge = self._recharges[recharge_no]
            except KeyError as exc:
                raise ValueError("REFUND_SOURCE_NOT_FOUND") from exc
            if (
                recharge.payment_order.payment_no != payment_no
                or recharge.payment_order.account_id != payment.account_id
            ):
                raise ValueError("REFUND_SOURCE_MISMATCH")
            return payment.account_id

    def recover_refund_assets(self, calculation: RefundCalculationSnapshot) -> None:
        with self._lock:
            previous = self._refunds.get(calculation.refund_reference)
            if previous is not None:
                if (previous.payment_no, previous.recharge_no) != (
                    calculation.payment_no,
                    calculation.recharge_no,
                ):
                    raise ValueError("REFUND_REFERENCE_CONFLICT")
                return
            payment = self._payments.get(calculation.payment_no)
            recharge = self._recharges.get(calculation.recharge_no)
            if payment is None or recharge is None or recharge.payment_order != payment:
                raise ValueError("REFUND_SOURCE_MISMATCH")
            self.wallet.recover_source_assets(payment.account_id, recharge.recharge_no)
            self._refunded_cents[recharge.recharge_no] = (
                self._refunded_cents.get(recharge.recharge_no, 0) + calculation.refundable_cents
            )
            self._refunds[calculation.refund_reference] = calculation

    def register_chapter_policy(self, chapter_id: str, policy: ChapterPolicy) -> None:
        with self._lock:
            require_positive_int(policy.price_coin, "price_coin")
            self._chapter_policies[chapter_id] = policy

    def purchase_chapter(
        self,
        account_id: str,
        chapter_id: str,
        policy: ChapterPolicy | None = None,
        membership: MembershipService | None = None,
    ) -> PurchaseOrder:
        with self._lock:
            existing = self._entitlements.get((account_id, chapter_id))
            if existing:
                return PurchaseOrder(existing.purchase_no, account_id, chapter_id, 0, (), existing)
            selected = policy or self._chapter_policies.get(chapter_id)
            if selected is None:
                raise ValueError("CHAPTER_POLICY_NOT_FOUND")
            if selected.access_mode in (
                AccessMode.FREE,
                AccessMode.LIMITED_FREE,
                AccessMode.MEMBER_FREE,
            ):
                raise ValueError("NOT_PURCHASABLE")
            self._purchase_sequence += 1
            allocations = self.wallet.spend(
                account_id, selected.price_coin, reason="CHAPTER_PURCHASE"
            )
            entitlement = Entitlement(
                account_id,
                chapter_id,
                f"PUR-{self._purchase_sequence}",
                datetime.now(UTC),
            )
            if self.record_revenue_in_transaction is not None:
                self.record_revenue_in_transaction(
                    None, chapter_id, entitlement.purchase_no, selected.price_coin
                )
            self._entitlements[(account_id, chapter_id)] = entitlement
            del membership
            return PurchaseOrder(
                entitlement.purchase_no,
                account_id,
                chapter_id,
                selected.price_coin,
                allocations,
                entitlement,
            )

    def entitlements(self, account_id: str) -> tuple[Entitlement, ...]:
        return tuple(item for item in self._entitlements.values() if item.account_id == account_id)

    def has_entitlement(self, account_id: str, chapter_id: str) -> bool:
        return (account_id, chapter_id) in self._entitlements
