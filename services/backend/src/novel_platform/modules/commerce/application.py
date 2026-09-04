from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from novel_platform.modules.membership.domain import AccessMode, ChapterPolicy, MembershipService
from novel_platform.modules.wallet.application import WalletService
from novel_platform.modules.wallet.domain import LotAllocation, require_positive_int


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

    def __init__(self, wallet: WalletService) -> None:
        self.wallet = wallet
        self._payment_sequence = 0
        self._recharge_sequence = 0
        self._purchase_sequence = 0
        self._recharges: dict[str, RechargeOrder] = {}
        self._payments: dict[str, PaymentOrder] = {}
        self._callbacks: dict[tuple[str, str], str] = {}
        self._idempotency: dict[str, tuple[tuple[str, str, str], RechargeCheckout]] = {}
        self._entitlements: dict[tuple[str, str], Entitlement] = {}
        self._chapter_policies: dict[str, ChapterPolicy] = {}

    def create_recharge(
        self,
        account_id: str,
        product_code: str,
        channel: str,
        idempotency_key: str | None = None,
    ) -> RechargeCheckout:
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
        checkout = RechargeCheckout(payment, order)
        if idempotency_key:
            self._idempotency[idempotency_key] = (fingerprint, checkout)
        return checkout

    def handle_payment_callback(self, provider: str, event_id: str, payment_no: str) -> str:
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
        self.wallet.grant_recharge_coin(payment.account_id, recharge.recharge_coin)
        if recharge.gift_coin:
            product_expiry = datetime.now(UTC).replace(microsecond=0) + timedelta(
                days=recharge.gift_expires_days
            )
            self.wallet.grant_gift_coin(
                payment.account_id,
                recharge.gift_coin,
                "PROMO",
                product_expiry,
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

    def register_chapter_policy(self, chapter_id: str, policy: ChapterPolicy) -> None:
        require_positive_int(policy.price_coin, "price_coin")
        self._chapter_policies[chapter_id] = policy

    def purchase_chapter(
        self,
        account_id: str,
        chapter_id: str,
        policy: ChapterPolicy | None = None,
        membership: MembershipService | None = None,
    ) -> PurchaseOrder:
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
        allocations = self.wallet.spend(account_id, selected.price_coin, reason="CHAPTER_PURCHASE")
        entitlement = Entitlement(
            account_id,
            chapter_id,
            f"PUR-{self._purchase_sequence}",
            datetime.now(UTC),
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
