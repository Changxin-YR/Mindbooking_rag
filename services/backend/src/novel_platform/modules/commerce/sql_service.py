"""SQLAlchemy commerce adapter for the payment and recharge tables."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError

from novel_platform.modules.commerce.application import (
    CommerceService,
    Entitlement,
    PaymentOrder,
    Product,
    PurchaseOrder,
    RechargeCheckout,
    RechargeOrder,
)
from novel_platform.modules.commerce.refund import (
    RefundCalculationSnapshot,
    RefundSourceSnapshot,
)
from novel_platform.modules.membership.domain import AccessMode, ChapterPolicy
from novel_platform.modules.payment import PaymentProvider, ProviderEvent, ProviderStatus
from novel_platform.modules.wallet.domain import WalletPort


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


payment_orders = sa.table(
    "payment_orders",
    sa.column("id", sa.BigInteger),
    sa.column("payment_no", sa.String),
    sa.column("account_id", sa.String),
    sa.column("channel", sa.String),
    sa.column("paid_cents", sa.BigInteger),
    sa.column("status", sa.String),
    sa.column("created_at", sa.DateTime),
)
payment_channel_events = sa.table(
    "payment_channel_events",
    sa.column("id", sa.BigInteger),
    sa.column("provider", sa.String),
    sa.column("provider_event_id", sa.String),
    sa.column("payment_no", sa.String),
    sa.column("channel_transaction_id", sa.String),
    sa.column("created_at", sa.DateTime),
)
recharge_orders = sa.table(
    "recharge_orders",
    sa.column("id", sa.BigInteger),
    sa.column("recharge_no", sa.String),
    sa.column("payment_order_id", sa.BigInteger),
    sa.column("account_id", sa.String),
    sa.column("paid_cents", sa.BigInteger),
    sa.column("recharge_coin", sa.BigInteger),
    sa.column("gift_coin", sa.BigInteger),
    sa.column("status", sa.String),
    sa.column("created_at", sa.DateTime),
)
chapter_commerce_policies = sa.table(
    "chapter_commerce_policies",
    sa.column("chapter_id", sa.String),
    sa.column("price_coin", sa.BigInteger),
    sa.column("access_mode", sa.String),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)
chapter_purchase_orders = sa.table(
    "chapter_purchase_orders",
    sa.column("id", sa.BigInteger),
    sa.column("purchase_no", sa.String),
    sa.column("account_id", sa.String),
    sa.column("total_coin", sa.BigInteger),
    sa.column("status", sa.String),
    sa.column("created_at", sa.DateTime),
)
chapter_purchase_items = sa.table(
    "chapter_purchase_items",
    sa.column("id", sa.BigInteger),
    sa.column("purchase_order_id", sa.BigInteger),
    sa.column("chapter_id", sa.String),
    sa.column("price_coin", sa.BigInteger),
)
chapter_entitlements = sa.table(
    "chapter_entitlements",
    sa.column("id", sa.BigInteger),
    sa.column("account_id", sa.String),
    sa.column("chapter_id", sa.String),
    sa.column("source_purchase_no", sa.String),
    sa.column("granted_at", sa.DateTime),
)


class SqlCommerceService(CommerceService):
    """Persist commerce facts while delegating asset changes to WalletPort."""

    PRODUCTS = CommerceService.PRODUCTS

    def __init__(
        self,
        engine: Engine,
        wallet: WalletPort,
        is_real_named: Callable[[str], bool] | None = None,
        payment_provider: PaymentProvider | None = None,
        payment_provider_secret: str = "",
    ) -> None:
        super().__init__(wallet, is_real_named)
        self.engine = engine
        self.payment_provider = payment_provider
        self.payment_provider_secret = payment_provider_secret
        self.record_revenue_in_transaction: (
            Callable[[sa.Connection, str, str, int], object] | None
        ) = None
        metadata = sa.MetaData()
        try:
            self._outbox: sa.Table | None = sa.Table(
                "outbox_events", metadata, autoload_with=engine
            )
        except sa.exc.NoSuchTableError:
            self._outbox = None

    def recover_refund_assets(self, calculation: RefundCalculationSnapshot) -> None:
        self.wallet.recover_source_assets(
            self.account_id_for_refund(calculation.payment_no, calculation.recharge_no),
            calculation.recharge_no,
        )

    def register_chapter_policy(self, chapter_id: str, policy: ChapterPolicy) -> None:
        self._require_text(chapter_id, "chapter_id")
        if policy.price_coin <= 0:
            raise ValueError("price_coin must be a positive integer")
        now = self._now()
        with self.engine.begin() as connection:
            existing = connection.execute(
                sa.select(chapter_commerce_policies.c.chapter_id).where(
                    chapter_commerce_policies.c.chapter_id == chapter_id
                )
            ).scalar_one_or_none()
            values = {
                "chapter_id": chapter_id,
                "price_coin": policy.price_coin,
                "access_mode": policy.access_mode.value,
                "updated_at": now,
            }
            if existing is None:
                connection.execute(
                    chapter_commerce_policies.insert().values(created_at=now, **values)
                )
            else:
                connection.execute(
                    chapter_commerce_policies.update()
                    .where(chapter_commerce_policies.c.chapter_id == chapter_id)
                    .values(**values)
                )

    def purchase_chapter(
        self,
        account_id: str,
        chapter_id: str,
        policy: ChapterPolicy | None = None,
        membership: object | None = None,
        _attempt: int = 0,
    ) -> PurchaseOrder:
        self._require_text(account_id, "account_id")
        self._require_text(chapter_id, "chapter_id")
        try:
            with self.engine.begin() as connection:
                # Do not take an entitlement gap lock before the wallet lock. Under
                # concurrent first purchases, that lock order can deadlock MySQL.
                existing = self._existing_purchase(connection, account_id, chapter_id, lock=False)
                if existing is not None:
                    return existing
                selected = policy or self._policy_in_connection(connection, chapter_id)
                if selected is None:
                    raise ValueError("CHAPTER_POLICY_NOT_FOUND")
                if selected.access_mode in (
                    AccessMode.FREE,
                    AccessMode.LIMITED_FREE,
                    AccessMode.MEMBER_FREE,
                ):
                    raise ValueError("NOT_PURCHASABLE")
                spend = getattr(self.wallet, "spend_in_transaction", None)
                if spend is None:
                    raise ValueError("PURCHASE_TRANSACTION_CONFIGURATION_ERROR")
                lock_account = getattr(self.wallet, "lock_account_in_transaction", None)
                if lock_account is not None:
                    # The wallet adapter owns the account row lock. Acquiring it
                    # before the entitlement re-check prevents gap-lock cycles.
                    lock_account(connection, account_id)
                    existing = self._existing_purchase(connection, account_id, chapter_id)
                    if existing is not None:
                        return existing
                allocations = spend(
                    connection, account_id, selected.price_coin, reason="CHAPTER_PURCHASE"
                )
                if lock_account is None:
                    # In-memory/test wallets may not expose an account lock. Keep
                    # their behavior compatible while retaining the SQL lock path.
                    existing = self._existing_purchase(connection, account_id, chapter_id)
                    if existing is not None:
                        return existing
                now = self._now()
                purchase_no = f"PUR-{uuid4().hex}"
                result = connection.execute(
                    chapter_purchase_orders.insert().values(
                        purchase_no=purchase_no,
                        account_id=account_id,
                        total_coin=selected.price_coin,
                        status="PURCHASED",
                        created_at=now,
                    )
                )
                del result
                order_id = connection.execute(
                    sa.select(chapter_purchase_orders.c.id).where(
                        chapter_purchase_orders.c.purchase_no == purchase_no
                    )
                ).scalar_one_or_none()
                if order_id is None:
                    raise RuntimeError("purchase order primary key was not created")
                connection.execute(
                    chapter_purchase_items.insert().values(
                        purchase_order_id=order_id,
                        chapter_id=chapter_id,
                        price_coin=selected.price_coin,
                    )
                )
                entitlement = Entitlement(account_id, chapter_id, purchase_no, now)
                connection.execute(
                    chapter_entitlements.insert().values(
                        account_id=account_id,
                        chapter_id=chapter_id,
                        source_purchase_no=purchase_no,
                        granted_at=now,
                    )
                )
                if self.record_revenue_in_transaction is not None:
                    self.record_revenue_in_transaction(
                        connection, chapter_id, purchase_no, selected.price_coin
                    )
                self._append_outbox(
                    connection,
                    "ChapterPurchased",
                    purchase_no,
                    {
                        "account_id": account_id,
                        "chapter_id": chapter_id,
                        "price_coin": selected.price_coin,
                    },
                )
                self._append_outbox(
                    connection,
                    "EntitlementCreated",
                    purchase_no,
                    {"account_id": account_id, "chapter_id": chapter_id},
                )
                return PurchaseOrder(
                    purchase_no,
                    account_id,
                    chapter_id,
                    selected.price_coin,
                    tuple(allocations),
                    entitlement,
                )
        except IntegrityError:
            with self.engine.begin() as connection:
                existing = self._existing_purchase(connection, account_id, chapter_id)
                if existing is not None:
                    return existing
            raise
        except OperationalError as exc:
            # MySQL may choose a deadlock victim while concurrent requests race
            # for the same wallet and entitlement rows; retry the whole
            # transaction so the idempotent existing-purchase check can win.
            original = exc.orig
            args = getattr(original, "args", ()) if original is not None else ()
            code = args[0] if args else None
            if code in (1205, 1213) and _attempt < 3:
                return self.purchase_chapter(
                    account_id,
                    chapter_id,
                    policy=policy,
                    membership=membership,
                    _attempt=_attempt + 1,
                )
            raise

    def has_entitlement(self, account_id: str, chapter_id: str) -> bool:
        with self.engine.connect() as connection:
            return (
                connection.execute(
                    sa.select(chapter_entitlements.c.id).where(
                        chapter_entitlements.c.account_id == account_id,
                        chapter_entitlements.c.chapter_id == chapter_id,
                    )
                ).scalar_one_or_none()
                is not None
            )

    def entitlements(self, account_id: str) -> tuple[Entitlement, ...]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                sa.select(
                    chapter_entitlements.c.account_id,
                    chapter_entitlements.c.chapter_id,
                    chapter_entitlements.c.source_purchase_no,
                    chapter_entitlements.c.granted_at,
                )
                .where(chapter_entitlements.c.account_id == account_id)
                .order_by(chapter_entitlements.c.granted_at, chapter_entitlements.c.id)
            ).mappings()
            result: list[Entitlement] = []
            for row in rows:
                granted_at = row["granted_at"]
                if granted_at.tzinfo is None:
                    granted_at = granted_at.replace(tzinfo=UTC)
                result.append(
                    Entitlement(
                        str(row["account_id"]),
                        str(row["chapter_id"]),
                        str(row["source_purchase_no"]),
                        granted_at,
                    )
                )
            return tuple(result)

    @staticmethod
    def _policy_in_connection(connection: sa.Connection, chapter_id: str) -> ChapterPolicy | None:
        row = (
            connection.execute(
                sa.select(
                    chapter_commerce_policies.c.price_coin,
                    chapter_commerce_policies.c.access_mode,
                ).where(chapter_commerce_policies.c.chapter_id == chapter_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return ChapterPolicy(int(row["price_coin"]), AccessMode(str(row["access_mode"])))

    @staticmethod
    def _existing_purchase(
        connection: sa.Connection,
        account_id: str,
        chapter_id: str,
        *,
        lock: bool = True,
    ) -> PurchaseOrder | None:
        query = (
            sa.select(
                chapter_purchase_orders.c.purchase_no,
                chapter_purchase_orders.c.total_coin,
                chapter_entitlements.c.granted_at,
            )
            .select_from(
                chapter_entitlements.join(
                    chapter_purchase_orders,
                    chapter_purchase_orders.c.purchase_no
                    == chapter_entitlements.c.source_purchase_no,
                )
            )
            .where(
                chapter_entitlements.c.account_id == account_id,
                chapter_entitlements.c.chapter_id == chapter_id,
            )
        )
        if lock:
            query = query.with_for_update()
        row = connection.execute(query).mappings().one_or_none()
        if row is None:
            return None
        granted_at = row["granted_at"]
        if granted_at.tzinfo is None:
            granted_at = granted_at.replace(tzinfo=UTC)
        entitlement = Entitlement(account_id, chapter_id, str(row["purchase_no"]), granted_at)
        return PurchaseOrder(
            str(row["purchase_no"]),
            account_id,
            chapter_id,
            int(row["total_coin"]),
            (),
            entitlement,
        )

    def create_recharge(
        self,
        account_id: str,
        product_code: str,
        channel: str,
        idempotency_key: str | None = None,
    ) -> RechargeCheckout:
        self._require_text(account_id, "account_id")
        self._require_text(channel, "channel")
        if self._is_real_named is not None and not self._is_real_named(account_id):
            raise ValueError("REAL_NAME_REQUIRED")
        key = self._require_text(idempotency_key, "idempotency_key")
        try:
            product = self.PRODUCTS[product_code]
        except KeyError as exc:
            raise ValueError("UNKNOWN_RECHARGE_PRODUCT") from exc

        payment_no = self._payment_no(key)
        try:
            with self.engine.begin() as connection:
                existing = self._checkout_by_payment_no(connection, payment_no)
                if existing is not None:
                    self._ensure_same_request(existing, account_id, product, channel)
                    return existing

                created_at = self._now()
                payment = PaymentOrder(payment_no, account_id, channel, product.paid_cents)
                connection.execute(
                    payment_orders.insert().values(
                        payment_no=payment.payment_no,
                        account_id=payment.account_id,
                        channel=payment.channel,
                        paid_cents=payment.paid_cents,
                        status=payment.status,
                        created_at=created_at,
                    )
                )
                payment_id = connection.execute(
                    sa.select(payment_orders.c.id).where(
                        payment_orders.c.payment_no == payment.payment_no
                    )
                ).scalar_one()
                recharge = RechargeOrder(
                    f"RECH-{uuid4().hex}",
                    payment,
                    product.recharge_coin,
                    product.gift_coin,
                    "PENDING_PAYMENT",
                    product.gift_expires_days or 30,
                )
                connection.execute(
                    recharge_orders.insert().values(
                        recharge_no=recharge.recharge_no,
                        payment_order_id=payment_id,
                        account_id=recharge.payment_order.account_id,
                        paid_cents=recharge.payment_order.paid_cents,
                        recharge_coin=recharge.recharge_coin,
                        gift_coin=recharge.gift_coin,
                        status=recharge.status,
                        created_at=created_at,
                    )
                )
                self._append_outbox(
                    connection,
                    "RechargeOrderCreated",
                    recharge.recharge_no,
                    {
                        "payment_no": payment.payment_no,
                        "account_id": payment.account_id,
                        "paid_cents": payment.paid_cents,
                    },
                )
                return self._with_provider_checkout(RechargeCheckout(payment, recharge))
        except IntegrityError:
            # A concurrent request may have won the deterministic payment_no.
            with self.engine.begin() as connection:
                existing = self._checkout_by_payment_no(connection, payment_no)
                if existing is None:
                    raise
                self._ensure_same_request(existing, account_id, product, channel)
                return self._with_provider_checkout(existing)

    def payment_account(self, payment_no: str) -> str:
        with self.engine.connect() as connection:
            account_id = connection.execute(
                sa.select(payment_orders.c.account_id).where(
                    payment_orders.c.payment_no == payment_no
                )
            ).scalar_one_or_none()
        if account_id is None:
            raise ValueError("PAYMENT_NOT_FOUND")
        return str(account_id)

    def payment_details(self, payment_no: str) -> tuple[str, int]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    sa.select(payment_orders.c.account_id, payment_orders.c.paid_cents).where(
                        payment_orders.c.payment_no == payment_no
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ValueError("PAYMENT_NOT_FOUND")
        return str(row["account_id"]), int(row["paid_cents"])

    def handle_payment_callback(
        self,
        provider: str,
        event_id: str,
        payment_no: str,
        channel_transaction_id: str | None = None,
    ) -> str:
        self._require_text(provider, "provider")
        self._require_text(event_id, "event_id")
        self._require_text(payment_no, "payment_no")
        if channel_transaction_id is not None:
            self._require_text(channel_transaction_id, "channel_transaction_id")

        credit_pending: tuple[str, str, int, str] | None = None
        with self.engine.begin() as connection:
            event = (
                connection.execute(
                    sa.select(
                        payment_channel_events.c.payment_no,
                        payment_channel_events.c.channel_transaction_id,
                    ).where(
                        payment_channel_events.c.provider == provider,
                        payment_channel_events.c.provider_event_id == event_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if event is not None:
                if event["payment_no"] != payment_no or (
                    channel_transaction_id is not None
                    and event["channel_transaction_id"] not in (None, channel_transaction_id)
                ):
                    raise ValueError("PAYMENT_EVENT_CONFLICT")
                return self._recharge_no_for_payment(connection, payment_no)

            payment = (
                connection.execute(
                    sa.select(
                        payment_orders.c.id,
                        payment_orders.c.payment_no,
                        payment_orders.c.account_id,
                        payment_orders.c.channel,
                        payment_orders.c.paid_cents,
                        payment_orders.c.status,
                    )
                    .where(payment_orders.c.payment_no == payment_no)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if payment is None:
                raise ValueError("PAYMENT_NOT_FOUND")
            event = (
                connection.execute(
                    sa.select(
                        payment_channel_events.c.payment_no,
                        payment_channel_events.c.channel_transaction_id,
                    )
                    .where(
                        payment_channel_events.c.provider == provider,
                        payment_channel_events.c.provider_event_id == event_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if event is not None:
                if event["payment_no"] != payment_no or (
                    channel_transaction_id is not None
                    and event["channel_transaction_id"] not in (None, channel_transaction_id)
                ):
                    raise ValueError("PAYMENT_EVENT_CONFLICT")
                return self._recharge_no_for_payment(connection, payment_no)
            recharge = (
                connection.execute(
                    sa.select(
                        recharge_orders.c.recharge_no,
                        recharge_orders.c.recharge_coin,
                        recharge_orders.c.gift_coin,
                        recharge_orders.c.status,
                    ).where(recharge_orders.c.payment_order_id == payment["id"])
                )
                .mappings()
                .one_or_none()
            )
            if recharge is None:
                raise ValueError("RECHARGE_ORDER_NOT_FOUND")
            if payment["status"] == "PAID" and recharge["status"] == "PAID":
                self._record_event(
                    connection, provider, event_id, payment_no, channel_transaction_id
                )
                return str(recharge["recharge_no"])
            if payment["status"] not in ("PENDING", "PROCESSING") or recharge["status"] not in (
                "PENDING_PAYMENT",
                "PROCESSING",
            ):
                raise ValueError("PAYMENT_STATE_CONFLICT")

            self._record_event(connection, provider, event_id, payment_no, channel_transaction_id)
            try:
                self._grant_recharge_coin(
                    connection,
                    payment["account_id"],
                    int(recharge["recharge_coin"]),
                    source_ref=recharge["recharge_no"],
                )
                if recharge["gift_coin"]:
                    self._grant_gift_coin(
                        connection,
                        payment["account_id"],
                        int(recharge["gift_coin"]),
                        "PROMO",
                        self._now() + timedelta(days=30),
                        source_ref=recharge["recharge_no"],
                    )
            except Exception:
                if not callable(self.record_payment_credit_failure):
                    raise
                # Preserve the provider success fact and leave a durable
                # governance repair record after this transaction commits.
                connection.execute(
                    payment_orders.update()
                    .where(payment_orders.c.id == payment["id"])
                    .values(status="PAID")
                )
                connection.execute(
                    recharge_orders.update()
                    .where(recharge_orders.c.recharge_no == recharge["recharge_no"])
                    .values(status="CREDIT_PENDING")
                )
                self._append_outbox(
                    connection,
                    "PaymentSucceeded",
                    payment_no,
                    {
                        "account_id": payment["account_id"],
                        "recharge_no": recharge["recharge_no"],
                        "credit_status": "CREDIT_PENDING",
                    },
                )
                credit_pending = (
                    payment_no,
                    str(payment["account_id"]),
                    int(payment["paid_cents"]),
                    str(recharge["recharge_no"]),
                )
            else:
                connection.execute(
                    payment_orders.update()
                    .where(payment_orders.c.id == payment["id"])
                    .values(status="PAID")
                )
                connection.execute(
                    recharge_orders.update()
                    .where(recharge_orders.c.recharge_no == recharge["recharge_no"])
                    .values(status="PAID")
                )
                self._append_outbox(
                    connection,
                    "PaymentSucceeded",
                    payment_no,
                    {"account_id": payment["account_id"], "recharge_no": recharge["recharge_no"]},
                )
                self._append_outbox(
                    connection,
                    "RechargeCredited",
                    str(recharge["recharge_no"]),
                    {
                        "account_id": payment["account_id"],
                        "recharge_coin": int(recharge["recharge_coin"]),
                        "gift_coin": int(recharge["gift_coin"]),
                    },
                )
                return str(recharge["recharge_no"])
        assert credit_pending is not None
        self.record_payment_credit_failure(credit_pending[0], credit_pending[1], credit_pending[2])
        return credit_pending[3]

    def repair_payment_credit(self, payment_no: str) -> str:
        """Retry wallet fulfillment after the provider has already confirmed payment."""
        with self.engine.begin() as connection:
            payment = (
                connection.execute(
                    sa.select(
                        payment_orders.c.id,
                        payment_orders.c.payment_no,
                        payment_orders.c.account_id,
                        payment_orders.c.channel,
                        payment_orders.c.paid_cents,
                        payment_orders.c.status,
                    )
                    .where(payment_orders.c.payment_no == payment_no)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if payment is None:
                raise ValueError("PAYMENT_NOT_FOUND")
            recharge = (
                connection.execute(
                    sa.select(
                        recharge_orders.c.recharge_no,
                        recharge_orders.c.recharge_coin,
                        recharge_orders.c.gift_coin,
                        recharge_orders.c.status,
                    )
                    .where(recharge_orders.c.payment_order_id == payment["id"])
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if recharge is None:
                raise ValueError("RECHARGE_ORDER_NOT_FOUND")
            recharge_no = str(recharge["recharge_no"])
            if recharge["status"] == "PAID":
                return recharge_no
            if recharge["status"] != "CREDIT_PENDING":
                raise ValueError("PAYMENT_CREDIT_STATE_CONFLICT")
            snapshot_fn = getattr(self.wallet, "source_snapshot_in_transaction", None)
            if callable(snapshot_fn):
                snapshot = snapshot_fn(connection, str(payment["account_id"]), recharge_no)
            else:
                snapshot = self.wallet.source_snapshot(str(payment["account_id"]), recharge_no)
            recharge_total = snapshot.consumed_recharge_coin + snapshot.remaining_recharge_coin
            if recharge_total < int(recharge["recharge_coin"]):
                self._grant_recharge_coin(
                    connection,
                    str(payment["account_id"]),
                    int(recharge["recharge_coin"]) - recharge_total,
                    source_ref=recharge_no,
                )
            gift_total = (
                snapshot.consumed_promo_gift_coin
                + snapshot.remaining_active_promo_gift_coin
                + snapshot.naturally_expired_promo_gift_coin
            )
            if gift_total < int(recharge["gift_coin"]):
                self._grant_gift_coin(
                    connection,
                    str(payment["account_id"]),
                    int(recharge["gift_coin"]) - gift_total,
                    "PROMO",
                    self._now() + timedelta(days=30),
                    source_ref=recharge_no,
                )
            connection.execute(
                payment_orders.update()
                .where(payment_orders.c.id == payment["id"])
                .values(status="PAID")
            )
            connection.execute(
                recharge_orders.update()
                .where(recharge_orders.c.recharge_no == recharge_no)
                .values(status="PAID")
            )
            self._append_outbox(
                connection,
                "RechargeCredited",
                recharge_no,
                {
                    "account_id": payment["account_id"],
                    "recharge_coin": int(recharge["recharge_coin"]),
                    "gift_coin": int(recharge["gift_coin"]),
                    "credit_repaired": True,
                },
            )
            return recharge_no

    def handle_payment_provider_event(
        self, event: ProviderEvent, *, now: datetime | None = None
    ) -> str:
        """Verify a provider event before routing it through the payment state machine."""
        if self.payment_provider is None or not self.payment_provider_secret:
            raise ValueError("PAYMENT_PROVIDER_NOT_CONFIGURED")
        if event.event_type != "PAYMENT":
            raise ValueError("PAYMENT_EVENT_TYPE_INVALID")
        provider_name = getattr(self.payment_provider, "provider_name", event.provider)
        if event.provider != provider_name:
            raise ValueError("PAYMENT_PROVIDER_MISMATCH")
        if not event.verify_signature(self.payment_provider_secret):
            raise ValueError("PAYMENT_SIGNATURE_INVALID")
        current = _utc(now or datetime.now(UTC))
        if _utc(event.available_at) > current:
            raise ValueError("PAYMENT_EVENT_NOT_AVAILABLE")
        with self.engine.begin() as connection:
            payment = (
                connection.execute(
                    sa.select(
                        payment_orders.c.paid_cents,
                        payment_orders.c.status,
                    ).where(payment_orders.c.payment_no == event.reference_id)
                )
                .mappings()
                .one_or_none()
            )
        if payment is None:
            raise ValueError("PAYMENT_NOT_FOUND")
        if int(payment["paid_cents"]) != event.amount_cents or event.currency != "CNY":
            raise ValueError("PAYMENT_AMOUNT_MISMATCH")
        if event.status is ProviderStatus.SUCCESS:
            return self.handle_payment_callback(
                event.provider,
                event.event_id,
                event.reference_id,
                event.provider_transaction_id,
            )
        return self._handle_non_success_provider_event(event)

    def _handle_non_success_provider_event(self, event: ProviderEvent) -> str:
        with self.engine.begin() as connection:
            existing = connection.execute(
                sa.select(payment_channel_events.c.payment_no).where(
                    payment_channel_events.c.provider == event.provider,
                    payment_channel_events.c.provider_event_id == event.event_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                if existing != event.reference_id:
                    raise ValueError("PAYMENT_EVENT_CONFLICT")
                return self._recharge_no_for_payment(connection, event.reference_id)
            payment = (
                connection.execute(
                    sa.select(payment_orders.c.id, payment_orders.c.status)
                    .where(payment_orders.c.payment_no == event.reference_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if payment is None:
                raise ValueError("PAYMENT_NOT_FOUND")
            recharge = (
                connection.execute(
                    sa.select(recharge_orders.c.recharge_no, recharge_orders.c.status).where(
                        recharge_orders.c.payment_order_id == payment["id"]
                    )
                )
                .mappings()
                .one_or_none()
            )
            if recharge is None:
                raise ValueError("RECHARGE_ORDER_NOT_FOUND")
            if payment["status"] == "PAID" or recharge["status"] == "PAID":
                raise ValueError("PAYMENT_STATE_CONFLICT")
            if payment["status"] not in ("PENDING", "PROCESSING") or recharge["status"] not in (
                "PENDING_PAYMENT",
                "PROCESSING",
            ):
                raise ValueError("PAYMENT_STATE_CONFLICT")
            self._record_event(
                connection,
                event.provider,
                event.event_id,
                event.reference_id,
                event.provider_transaction_id,
            )
            status = event.status.value
            connection.execute(
                payment_orders.update()
                .where(payment_orders.c.id == payment["id"])
                .values(status=status)
            )
            connection.execute(
                recharge_orders.update()
                .where(recharge_orders.c.recharge_no == recharge["recharge_no"])
                .values(status=status)
            )
            self._append_outbox(
                connection,
                "PaymentStatusChanged",
                event.reference_id,
                {"status": status, "recharge_no": recharge["recharge_no"]},
            )
            return str(recharge["recharge_no"])

    def _append_outbox(
        self,
        connection: sa.Connection,
        event_type: str,
        aggregate_id: str,
        payload: dict[str, object],
    ) -> None:
        if self._outbox is None:
            return
        now = self._now()
        values: dict[str, object] = {
            "id": f"OUTBOX_{uuid4().hex}",
            "event_type": event_type,
            "aggregate_id": aggregate_id,
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            "attempts": 0,
            "created_at": now,
        }
        optional = {
            "status": "NEW",
            "available_at": None,
            "locked_by": None,
            "locked_at": None,
            "last_error": None,
            "processed_at": None,
        }
        values.update({name: value for name, value in optional.items() if name in self._outbox.c})
        connection.execute(self._outbox.insert().values(**values))

    def _grant_recharge_coin(
        self,
        connection: sa.Connection,
        account_id: str,
        amount: int,
        *,
        source_ref: str,
    ) -> None:
        grant = getattr(self.wallet, "grant_recharge_coin_in_transaction", None)
        if grant is None:
            self.wallet.grant_recharge_coin(account_id, amount, source_ref=source_ref)
            return
        grant(connection, account_id, amount, source_ref=source_ref)

    def _grant_gift_coin(
        self,
        connection: sa.Connection,
        account_id: str,
        amount: int,
        origin: str,
        expires_at: datetime,
        *,
        source_ref: str,
    ) -> None:
        grant = getattr(self.wallet, "grant_gift_coin_in_transaction", None)
        if grant is None:
            self.wallet.grant_gift_coin(
                account_id,
                amount,
                origin,
                expires_at,
                source_ref=source_ref,
            )
            return
        grant(
            connection,
            account_id,
            amount,
            origin,
            expires_at,
            source_ref=source_ref,
        )

    def refund_source(self, payment_no: str, recharge_no: str) -> RefundSourceSnapshot:
        with self.engine.begin() as connection:
            return self.refund_source_in_transaction(connection, payment_no, recharge_no)

    def refund_source_in_transaction(
        self, connection: sa.Connection, payment_no: str, recharge_no: str
    ) -> RefundSourceSnapshot:
        payment, recharge = self._source_orders_in_connection(
            connection, payment_no, recharge_no, require_paid=True
        )
        snapshot = getattr(self.wallet, "source_snapshot_in_transaction", None)
        if snapshot is None:
            raise ValueError("REFUND_TRANSACTION_CONFIGURATION_ERROR")
        assets = snapshot(connection, payment["account_id"], recharge_no)
        if (
            assets.consumed_recharge_coin + assets.remaining_recharge_coin
            != int(recharge["recharge_coin"])
            or assets.consumed_promo_gift_coin
            + assets.naturally_expired_promo_gift_coin
            + assets.remaining_active_promo_gift_coin
            != int(recharge["gift_coin"])
        ):
            raise ValueError("REFUND_SOURCE_NOT_FOUND")
        return RefundSourceSnapshot(
            payment_no,
            recharge_no,
            int(payment["paid_cents"]),
            assets.consumed_recharge_coin,
            assets.consumed_promo_gift_coin,
            assets.naturally_expired_promo_gift_coin,
            0,
            assets.remaining_recharge_coin,
            assets.remaining_active_promo_gift_coin,
        )

    def account_id_for_refund(self, payment_no: str, recharge_no: str) -> str:
        payment, _ = self._source_orders(payment_no, recharge_no, require_paid=False)
        return str(payment["account_id"])

    refund_account = account_id_for_refund

    def _source_orders(
        self, payment_no: str, recharge_no: str, *, require_paid: bool
    ) -> tuple[sa.RowMapping, sa.RowMapping]:
        with self.engine.begin() as connection:
            return self._source_orders_in_connection(
                connection, payment_no, recharge_no, require_paid=require_paid
            )

    @staticmethod
    def _source_orders_in_connection(
        connection: sa.Connection,
        payment_no: str,
        recharge_no: str,
        *,
        require_paid: bool,
    ) -> tuple[sa.RowMapping, sa.RowMapping]:
        payment = (
            connection.execute(
                sa.select(
                    payment_orders.c.id,
                    payment_orders.c.payment_no,
                    payment_orders.c.account_id,
                    payment_orders.c.paid_cents,
                    payment_orders.c.status,
                )
                .where(payment_orders.c.payment_no == payment_no)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        recharge = (
            connection.execute(
                sa.select(
                    recharge_orders.c.recharge_no,
                    recharge_orders.c.payment_order_id,
                    recharge_orders.c.account_id,
                    recharge_orders.c.paid_cents,
                    recharge_orders.c.recharge_coin,
                    recharge_orders.c.gift_coin,
                    recharge_orders.c.status,
                )
                .where(recharge_orders.c.recharge_no == recharge_no)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if payment is None or recharge is None:
            raise ValueError("REFUND_SOURCE_NOT_FOUND")
        if (
            recharge["payment_order_id"] != payment["id"]
            or recharge["account_id"] != payment["account_id"]
            or recharge["paid_cents"] != payment["paid_cents"]
            or (require_paid and (payment["status"] != "PAID" or recharge["status"] != "PAID"))
        ):
            raise ValueError("REFUND_SOURCE_MISMATCH")
        return payment, recharge

    @staticmethod
    def _checkout_by_payment_no(
        connection: sa.Connection, payment_no: str
    ) -> RechargeCheckout | None:
        payment = (
            connection.execute(
                sa.select(
                    payment_orders.c.id,
                    payment_orders.c.payment_no,
                    payment_orders.c.account_id,
                    payment_orders.c.channel,
                    payment_orders.c.paid_cents,
                    payment_orders.c.status,
                ).where(payment_orders.c.payment_no == payment_no)
            )
            .mappings()
            .one_or_none()
        )
        if payment is None:
            return None
        recharge = (
            connection.execute(
                sa.select(
                    recharge_orders.c.recharge_no,
                    recharge_orders.c.recharge_coin,
                    recharge_orders.c.gift_coin,
                    recharge_orders.c.status,
                ).where(recharge_orders.c.payment_order_id == payment["id"])
            )
            .mappings()
            .one_or_none()
        )
        if recharge is None:
            raise ValueError("RECHARGE_ORDER_NOT_FOUND")
        payment_order = PaymentOrder(
            payment["payment_no"],
            payment["account_id"],
            payment["channel"],
            int(payment["paid_cents"]),
            payment["status"],
        )
        return RechargeCheckout(
            payment_order,
            RechargeOrder(
                recharge["recharge_no"],
                payment_order,
                int(recharge["recharge_coin"]),
                int(recharge["gift_coin"]),
                recharge["status"],
                30,
            ),
        )

    def _with_provider_checkout(self, checkout: RechargeCheckout) -> RechargeCheckout:
        if self.payment_provider is None:
            return checkout
        return RechargeCheckout(
            checkout.payment_order,
            checkout.recharge_order,
            self.payment_provider.create_checkout(
                checkout.payment_order.payment_no,
                checkout.payment_order.paid_cents,
                currency="CNY",
            ),
        )

    @staticmethod
    def _ensure_same_request(
        checkout: RechargeCheckout, account_id: str, product: Product, channel: str
    ) -> None:
        if (
            checkout.payment_order.account_id != account_id
            or checkout.payment_order.channel != channel
            or checkout.payment_order.paid_cents != product.paid_cents
            or checkout.recharge_order.recharge_coin != product.recharge_coin
            or checkout.recharge_order.gift_coin != product.gift_coin
        ):
            raise ValueError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")

    @staticmethod
    def _recharge_no_for_payment(connection: sa.Connection, payment_no: str) -> str:
        recharge_no = connection.execute(
            sa.select(recharge_orders.c.recharge_no)
            .select_from(
                recharge_orders.join(
                    payment_orders,
                    recharge_orders.c.payment_order_id == payment_orders.c.id,
                )
            )
            .where(payment_orders.c.payment_no == payment_no)
        ).scalar_one_or_none()
        if recharge_no is None:
            raise ValueError("RECHARGE_ORDER_NOT_FOUND")
        return str(recharge_no)

    @staticmethod
    def _record_event(
        connection: sa.Connection,
        provider: str,
        event_id: str,
        payment_no: str,
        channel_transaction_id: str | None,
    ) -> None:
        existing = (
            connection.execute(
                sa.select(
                    payment_channel_events.c.payment_no,
                    payment_channel_events.c.channel_transaction_id,
                ).where(
                    payment_channel_events.c.provider == provider,
                    payment_channel_events.c.provider_event_id == event_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            if existing["payment_no"] != payment_no or (
                channel_transaction_id is not None
                and existing["channel_transaction_id"] not in (None, channel_transaction_id)
            ):
                raise ValueError("PAYMENT_EVENT_CONFLICT")
            if existing["channel_transaction_id"] is None and channel_transaction_id is not None:
                connection.execute(
                    payment_channel_events.update()
                    .where(
                        payment_channel_events.c.provider == provider,
                        payment_channel_events.c.provider_event_id == event_id,
                    )
                    .values(channel_transaction_id=channel_transaction_id)
                )
            return
        if channel_transaction_id is not None:
            existing_transaction = (
                connection.execute(
                    sa.select(
                        payment_channel_events.c.payment_no,
                        payment_channel_events.c.provider_event_id,
                    ).where(
                        payment_channel_events.c.provider == provider,
                        payment_channel_events.c.channel_transaction_id == channel_transaction_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing_transaction is not None:
                if existing_transaction["payment_no"] != payment_no:
                    raise ValueError("PAYMENT_EVENT_CONFLICT")
                connection.execute(
                    payment_channel_events.update()
                    .where(
                        payment_channel_events.c.provider == provider,
                        payment_channel_events.c.channel_transaction_id == channel_transaction_id,
                    )
                    .values(provider_event_id=event_id, created_at=SqlCommerceService._now())
                )
                return
        connection.execute(
            payment_channel_events.insert().values(
                provider=provider,
                provider_event_id=event_id,
                payment_no=payment_no,
                channel_transaction_id=channel_transaction_id,
                created_at=SqlCommerceService._now(),
            )
        )

    @staticmethod
    def _payment_no(key: str) -> str:
        return f"PAY-{sha256(key.encode('utf-8')).hexdigest()[:56]}"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC).replace(microsecond=0)

    @staticmethod
    def _require_text(value: str | None, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "IDEMPOTENCY_KEY_REQUIRED" if name == "idempotency_key" else f"{name} is required"
            )
        return value.strip()
