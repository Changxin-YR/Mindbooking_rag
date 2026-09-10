from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.commerce.refund import RefundSourceSnapshot
from novel_platform.modules.commerce.sql_service import SqlCommerceService
from novel_platform.modules.membership.domain import AccessMode, ChapterPolicy
from novel_platform.modules.payment import ProviderStatus, SandboxPaymentProvider
from novel_platform.modules.wallet.domain import (
    AssetType,
    LotAllocation,
    WalletAssetLot,
    WalletBalance,
    WalletSourceSnapshot,
)


class FakeWallet:
    def __init__(self, source: WalletSourceSnapshot | None = None, fail: bool = False) -> None:
        self.source = source or WalletSourceSnapshot(0, 0, 0, 0, 0)
        self.fail = fail
        self.grants: list[tuple[str, int, str]] = []

    def balance(self, account_id: str, now: datetime | None = None) -> WalletBalance:
        del account_id, now
        return WalletBalance()

    def source_snapshot(
        self, account_id: str, source_ref: str, now: datetime | None = None
    ) -> WalletSourceSnapshot:
        del account_id, source_ref, now
        return self.source

    def source_snapshot_in_transaction(
        self,
        connection: sa.Connection,
        account_id: str,
        source_ref: str,
        now: datetime | None = None,
    ) -> WalletSourceSnapshot:
        del connection, account_id, source_ref, now
        return self.source

    def spend_in_transaction(
        self,
        connection: sa.Connection,
        account_id: str,
        amount: int,
        now: datetime | None = None,
        reason: str = "PURCHASE",
    ) -> tuple[LotAllocation, ...]:
        del now
        connection.execute(
            sa.text(
                "INSERT INTO wallet_mutations (account_id, asset_type, amount, source_ref) "
                "VALUES (:account_id, :asset_type, :amount, :source_ref)"
            ),
            {"account_id": account_id, "asset_type": reason, "amount": -amount, "source_ref": None},
        )
        return (LotAllocation("lot-recharge", AssetType.RECHARGE, amount),)

    def recover_source_assets(
        self, account_id: str, source_ref: str, now: datetime | None = None
    ) -> None:
        del account_id, source_ref, now

    def spend(
        self, account_id: str, amount: int, now: datetime | None = None, reason: str = "PURCHASE"
    ) -> tuple[LotAllocation, ...]:
        del account_id, amount, now, reason
        return ()

    def grant_recharge_coin(
        self, account_id: str, amount: int, reason: str = "RECHARGE", source_ref: str | None = None
    ) -> WalletAssetLot:
        if self.fail:
            raise RuntimeError("wallet unavailable")
        self.grants.append((account_id, amount, source_ref or ""))
        return WalletAssetLot(
            "lot-recharge", account_id, AssetType.RECHARGE, "RECHARGE", amount, datetime.now(UTC)
        )

    def grant_gift_coin(
        self,
        account_id: str,
        amount: int,
        origin: str,
        expires_at: datetime | None,
        issued_at: datetime | None = None,
        source_ref: str | None = None,
    ) -> WalletAssetLot:
        if self.fail:
            raise RuntimeError("wallet unavailable")
        self.grants.append((account_id, amount, source_ref or ""))
        return WalletAssetLot(
            "lot-gift",
            account_id,
            AssetType.GIFT,
            origin,
            amount,
            issued_at or datetime.now(UTC),
            expires_at,
        )


class TransactionalFailingWallet(FakeWallet):
    def grant_recharge_coin(
        self, account_id: str, amount: int, reason: str = "RECHARGE", source_ref: str | None = None
    ) -> WalletAssetLot:
        del account_id, amount, reason, source_ref
        raise AssertionError("commerce must use the shared connection")

    def grant_gift_coin(
        self,
        account_id: str,
        amount: int,
        origin: str,
        expires_at: datetime | None,
        issued_at: datetime | None = None,
        source_ref: str | None = None,
    ) -> WalletAssetLot:
        del account_id, amount, origin, expires_at, issued_at, source_ref
        raise AssertionError("commerce must use the shared connection")

    def grant_recharge_coin_in_transaction(
        self,
        connection: sa.Connection,
        account_id: str,
        amount: int,
        reason: str = "RECHARGE",
        source_ref: str | None = None,
    ) -> WalletAssetLot:
        connection.execute(
            sa.text(
                "INSERT INTO wallet_mutations (account_id, asset_type, amount, source_ref) "
                "VALUES (:account_id, :asset_type, :amount, :source_ref)"
            ),
            {
                "account_id": account_id,
                "asset_type": AssetType.RECHARGE.value,
                "amount": amount,
                "source_ref": source_ref,
            },
        )
        return WalletAssetLot(
            "lot-recharge", account_id, AssetType.RECHARGE, "RECHARGE", amount, datetime.now(UTC)
        )

    def grant_gift_coin_in_transaction(
        self,
        connection: sa.Connection,
        account_id: str,
        amount: int,
        origin: str,
        expires_at: datetime | None,
        issued_at: datetime | None = None,
        source_ref: str | None = None,
    ) -> WalletAssetLot:
        connection.execute(
            sa.text(
                "INSERT INTO wallet_mutations (account_id, asset_type, amount, source_ref) "
                "VALUES (:account_id, :asset_type, :amount, :source_ref)"
            ),
            {
                "account_id": account_id,
                "asset_type": AssetType.GIFT.value,
                "amount": amount,
                "source_ref": source_ref,
            },
        )
        del origin, issued_at
        raise RuntimeError("wallet unavailable")


class LockingFakeWallet(FakeWallet):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []

    def lock_account_in_transaction(self, connection: sa.Connection, account_id: str) -> None:
        del connection, account_id
        self.events.append("lock")

    def spend_in_transaction(
        self,
        connection: sa.Connection,
        account_id: str,
        amount: int,
        now: datetime | None = None,
        reason: str = "PURCHASE",
    ) -> tuple[LotAllocation, ...]:
        self.events.append("spend")
        return super().spend_in_transaction(connection, account_id, amount, now, reason)


def _schema() -> sa.MetaData:
    metadata = sa.MetaData()
    payment_orders = sa.Table(
        "payment_orders",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("payment_no", sa.String(64), nullable=False, unique=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("paid_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "payment_attempts",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "payment_order_id", sa.Integer, sa.ForeignKey(payment_orders.c.id), nullable=False
        ),
        sa.Column("attempt_no", sa.Integer, nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("payment_order_id", "attempt_no"),
    )
    sa.Table(
        "payment_channel_events",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_event_id", sa.String(128), nullable=False),
        sa.Column("payment_no", sa.String(64), nullable=False),
        sa.Column("channel_transaction_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_event_id"),
        sa.UniqueConstraint("provider", "channel_transaction_id"),
    )
    sa.Table(
        "recharge_orders",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("recharge_no", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "payment_order_id",
            sa.Integer,
            sa.ForeignKey(payment_orders.c.id),
            nullable=False,
            unique=True,
        ),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("paid_cents", sa.BigInteger, nullable=False),
        sa.Column("recharge_coin", sa.BigInteger, nullable=False),
        sa.Column("gift_coin", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "wallet_mutations",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("asset_type", sa.String(24), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("source_ref", sa.String(128)),
    )
    sa.Table(
        "chapter_commerce_policies",
        metadata,
        sa.Column("chapter_id", sa.String(64), primary_key=True),
        sa.Column("price_coin", sa.BigInteger, nullable=False),
        sa.Column("access_mode", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    purchase_orders = sa.Table(
        "chapter_purchase_orders",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("purchase_no", sa.String(64), nullable=False, unique=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("total_coin", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "chapter_purchase_items",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "purchase_order_id", sa.Integer, sa.ForeignKey(purchase_orders.c.id), nullable=False
        ),
        sa.Column("chapter_id", sa.String(64), nullable=False),
        sa.Column("price_coin", sa.BigInteger, nullable=False),
    )
    sa.Table(
        "chapter_entitlements",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("chapter_id", sa.String(64), nullable=False),
        sa.Column("source_purchase_no", sa.String(64), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "chapter_id"),
    )
    return metadata


def _service(wallet: FakeWallet | None = None) -> tuple[SqlCommerceService, sa.Engine]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _schema().create_all(engine)
    return SqlCommerceService(engine, wallet or FakeWallet()), engine


def test_sql_commerce_creates_orders_and_credits_callback() -> None:
    wallet = FakeWallet(WalletSourceSnapshot(0, 0, 0, 10_000, 2_000))
    service, engine = _service(wallet)

    checkout = service.create_recharge("acct-1", "RECHARGE_100_PROMO", "FAKE", "key-1")
    assert checkout.payment_order.paid_cents == 10_000
    assert checkout.recharge_order.status == "PENDING_PAYMENT"

    assert (
        service.handle_payment_callback("FAKE", "event-1", checkout.payment_order.payment_no)
        == checkout.recharge_order.recharge_no
    )
    assert wallet.grants == [
        ("acct-1", 10_000, checkout.recharge_order.recharge_no),
        ("acct-1", 2_000, checkout.recharge_order.recharge_no),
    ]
    source = service.refund_source(
        checkout.payment_order.payment_no, checkout.recharge_order.recharge_no
    )
    assert source == RefundSourceSnapshot(
        "PAY-" + checkout.payment_order.payment_no[4:],
        checkout.recharge_order.recharge_no,
        10_000,
        0,
        0,
        0,
        0,
        10_000,
        2_000,
    )
    assert service.account_id_for_refund(source.payment_no, source.recharge_no) == "acct-1"

    with engine.begin() as connection:
        assert (
            connection.execute(sa.text("SELECT status FROM payment_orders")).scalar_one() == "PAID"
        )
        assert (
            connection.execute(sa.text("SELECT status FROM recharge_orders")).scalar_one() == "PAID"
        )


def test_sql_commerce_rejects_invalid_requests_and_source_mismatch() -> None:
    service, _ = _service()
    with pytest.raises(ValueError, match="IDEMPOTENCY_KEY_REQUIRED"):
        service.create_recharge("acct-1", "RECHARGE_100", "FAKE", "")
    with pytest.raises(ValueError, match="UNKNOWN_RECHARGE_PRODUCT"):
        service.create_recharge("acct-1", "UNKNOWN", "FAKE", "key-1")
    with pytest.raises(ValueError, match="PAYMENT_NOT_FOUND"):
        service.handle_payment_callback("FAKE", "event-1", "PAY-missing")

    checkout = service.create_recharge("acct-1", "RECHARGE_100", "FAKE", "key-1")
    with pytest.raises(ValueError, match="REFUND_SOURCE_NOT_FOUND"):
        service.refund_source(checkout.payment_order.payment_no, "RECH-missing")

    other = service.create_recharge("acct-2", "RECHARGE_100", "FAKE", "key-2")
    with pytest.raises(ValueError, match="REFUND_SOURCE_MISMATCH"):
        service.refund_source(checkout.payment_order.payment_no, other.recharge_order.recharge_no)


def test_sql_commerce_persists_idempotency_and_callback_conflicts() -> None:
    service, engine = _service()
    first = service.create_recharge("acct-1", "RECHARGE_100", "FAKE", "key-1")
    second_service = SqlCommerceService(engine, FakeWallet())
    assert second_service.create_recharge("acct-1", "RECHARGE_100", "FAKE", "key-1") == first
    with pytest.raises(ValueError, match="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"):
        second_service.create_recharge("acct-2", "RECHARGE_100", "FAKE", "key-1")

    second = service.create_recharge("acct-2", "RECHARGE_100", "FAKE", "key-2")
    service.handle_payment_callback("FAKE", "event-1", first.payment_order.payment_no)
    assert (
        service.handle_payment_callback("FAKE", "event-1", first.payment_order.payment_no)
        == first.recharge_order.recharge_no
    )
    with pytest.raises(ValueError, match="PAYMENT_EVENT_CONFLICT"):
        service.handle_payment_callback("FAKE", "event-1", second.payment_order.payment_no)

    with engine.begin() as connection:
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM payment_channel_events")).scalar_one()
            == 1
        )


def test_sql_commerce_callback_rolls_back_when_wallet_credit_fails() -> None:
    service, engine = _service(FakeWallet(fail=True))
    checkout = service.create_recharge("acct-1", "RECHARGE_100", "FAKE", "key-1")

    with pytest.raises(RuntimeError, match="wallet unavailable"):
        service.handle_payment_callback("FAKE", "event-1", checkout.payment_order.payment_no)

    with engine.begin() as connection:
        assert (
            connection.execute(sa.text("SELECT status FROM payment_orders")).scalar_one()
            == "PENDING"
        )
        assert (
            connection.execute(sa.text("SELECT status FROM recharge_orders")).scalar_one()
            == "PENDING_PAYMENT"
        )
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM payment_channel_events")).scalar_one()
            == 0
        )


def test_sql_commerce_shared_transaction_rolls_back_partial_wallet_grants() -> None:
    service, engine = _service(TransactionalFailingWallet())
    checkout = service.create_recharge("acct-1", "RECHARGE_100_PROMO", "FAKE", "key-1")

    with pytest.raises(RuntimeError, match="wallet unavailable"):
        service.handle_payment_callback("FAKE", "event-1", checkout.payment_order.payment_no)

    with engine.begin() as connection:
        assert (
            connection.execute(sa.text("SELECT status FROM payment_orders")).scalar_one()
            == "PENDING"
        )
        assert (
            connection.execute(sa.text("SELECT status FROM recharge_orders")).scalar_one()
            == "PENDING_PAYMENT"
        )
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM payment_channel_events")).scalar_one()
            == 0
        )
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM wallet_mutations")).scalar_one() == 0
        )


def test_sql_commerce_preserves_success_and_records_credit_pending_when_repair_port_is_configured() -> (
    None
):
    service, engine = _service(FakeWallet(fail=True))
    checkout = service.create_recharge("acct-1", "RECHARGE_100", "FAKE", "key-credit-pending")
    pending: list[tuple[str, str, int]] = []
    service.record_payment_credit_failure = lambda payment_id, account_id, amount_cents: (
        pending.append((payment_id, account_id, amount_cents))
    )

    assert (
        service.handle_payment_callback(
            "FAKE", "event-credit-pending", checkout.payment_order.payment_no, "tx-credit-pending"
        )
        == checkout.recharge_order.recharge_no
    )

    with engine.begin() as connection:
        assert (
            connection.execute(sa.text("SELECT status FROM payment_orders")).scalar_one() == "PAID"
        )
        assert (
            connection.execute(sa.text("SELECT status FROM recharge_orders")).scalar_one()
            == "CREDIT_PENDING"
        )
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM payment_channel_events")).scalar_one()
            == 1
        )
    assert pending == [
        (checkout.payment_order.payment_no, "acct-1", checkout.payment_order.paid_cents)
    ]


def test_sql_commerce_repair_payment_credit_is_idempotent() -> None:
    wallet = FakeWallet(fail=True)
    service, engine = _service(wallet)
    checkout = service.create_recharge("acct-1", "RECHARGE_100", "FAKE", "key-credit-repair")
    service.record_payment_credit_failure = lambda *_: None
    service.handle_payment_callback(
        "FAKE", "event-credit-repair", checkout.payment_order.payment_no
    )
    wallet.fail = False

    assert service.repair_payment_credit(checkout.payment_order.payment_no) == (
        checkout.recharge_order.recharge_no
    )
    assert service.repair_payment_credit(checkout.payment_order.payment_no) == (
        checkout.recharge_order.recharge_no
    )
    with engine.begin() as connection:
        assert (
            connection.execute(sa.text("SELECT status FROM recharge_orders")).scalar_one() == "PAID"
        )


def test_sql_commerce_returns_provider_checkout_and_processes_verified_provider_event() -> None:
    provider = SandboxPaymentProvider(secret="sandbox-secret")
    service, _ = _service()
    service.payment_provider = provider
    service.payment_provider_secret = "sandbox-secret"

    checkout = service.create_recharge("acct-1", "RECHARGE_100", "SANDBOX", "provider-key")
    assert checkout.provider_checkout is not None
    assert checkout.provider_checkout.provider == "SANDBOX"

    event = provider.generate_callback_event(
        checkout.payment_order.payment_no, ProviderStatus.SUCCESS
    )
    assert service.handle_payment_provider_event(event) == checkout.recharge_order.recharge_no

    duplicate = provider.generate_callback_event(
        checkout.payment_order.payment_no, ProviderStatus.SUCCESS, event_id=event.event_id
    )
    assert service.handle_payment_provider_event(duplicate) == checkout.recharge_order.recharge_no


def test_sql_commerce_provider_failure_does_not_credit_wallet() -> None:
    provider = SandboxPaymentProvider(secret="sandbox-secret")
    service, engine = _service()
    service.payment_provider = provider
    service.payment_provider_secret = "sandbox-secret"
    checkout = service.create_recharge("acct-1", "RECHARGE_100", "SANDBOX", "failed-key")
    event = provider.generate_callback_event(
        checkout.payment_order.payment_no, ProviderStatus.FAILED
    )

    service.handle_payment_provider_event(event)
    with engine.begin() as connection:
        assert (
            connection.execute(sa.text("SELECT status FROM payment_orders")).scalar_one()
            == "FAILED"
        )
        assert (
            connection.execute(sa.text("SELECT status FROM recharge_orders")).scalar_one()
            == "FAILED"
        )
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM wallet_mutations")).scalar_one() == 0
        )


def test_sql_commerce_provider_status_updates_reuse_transaction_event() -> None:
    provider = SandboxPaymentProvider(secret="sandbox-secret")
    service, engine = _service()
    service.payment_provider = provider
    service.payment_provider_secret = "sandbox-secret"

    paid_checkout = service.create_recharge(
        "acct-processing-paid", "RECHARGE_100", "SANDBOX", "processing-paid"
    )
    processing = provider.generate_callback_event(
        paid_checkout.payment_order.payment_no, ProviderStatus.PROCESSING
    )
    assert (
        service.handle_payment_provider_event(processing)
        == paid_checkout.recharge_order.recharge_no
    )
    success = provider.generate_callback_event(
        paid_checkout.payment_order.payment_no, ProviderStatus.SUCCESS
    )
    assert (
        service.handle_payment_provider_event(success) == paid_checkout.recharge_order.recharge_no
    )

    failed_checkout = service.create_recharge(
        "acct-processing-failed", "RECHARGE_100", "SANDBOX", "processing-failed"
    )
    pending = provider.generate_callback_event(
        failed_checkout.payment_order.payment_no, ProviderStatus.PROCESSING
    )
    assert (
        service.handle_payment_provider_event(pending) == failed_checkout.recharge_order.recharge_no
    )
    failed = provider.generate_callback_event(
        failed_checkout.payment_order.payment_no, ProviderStatus.FAILED
    )
    assert (
        service.handle_payment_provider_event(failed) == failed_checkout.recharge_order.recharge_no
    )

    with engine.begin() as connection:
        statuses = (
            connection.execute(sa.text("SELECT status FROM payment_orders ORDER BY id"))
            .scalars()
            .all()
        )
        assert statuses[-2:] == ["PAID", "FAILED"]
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM payment_channel_events")).scalar_one()
            == 2
        )


def test_sql_commerce_provider_terminal_status_cannot_regress() -> None:
    provider = SandboxPaymentProvider(secret="sandbox-secret")
    service, _ = _service()
    service.payment_provider = provider
    service.payment_provider_secret = "sandbox-secret"
    checkout = service.create_recharge("acct-terminal", "RECHARGE_100", "SANDBOX", "terminal")
    failed = provider.generate_callback_event(
        checkout.payment_order.payment_no, ProviderStatus.FAILED
    )
    service.handle_payment_provider_event(failed)
    processing = provider.generate_callback_event(
        checkout.payment_order.payment_no, ProviderStatus.PROCESSING
    )
    with pytest.raises(ValueError, match="PAYMENT_STATE_CONFLICT"):
        service.handle_payment_provider_event(processing)


def test_sql_commerce_provider_callback_accepts_naive_event_datetime() -> None:
    provider = SandboxPaymentProvider(
        secret="sandbox-secret", clock=lambda: datetime.fromisoformat("2026-09-05T12:00:00")
    )
    service, _ = _service()
    service.payment_provider = provider
    service.payment_provider_secret = "sandbox-secret"
    checkout = service.create_recharge("acct-naive", "RECHARGE_100", "SANDBOX", "naive-clock")

    event = provider.generate_callback_event(
        checkout.payment_order.payment_no, ProviderStatus.SUCCESS
    )
    assert (
        service.handle_payment_provider_event(event, now=datetime(2026, 9, 5, 12, tzinfo=UTC))
        == checkout.recharge_order.recharge_no
    )


def test_sql_chapter_purchase_is_persisted_and_idempotent() -> None:
    wallet = FakeWallet()
    service, engine = _service(wallet)
    service.register_chapter_policy("chapter-1", ChapterPolicy(100, AccessMode.PURCHASED))

    first = service.purchase_chapter("acct-1", "chapter-1")
    second = service.purchase_chapter("acct-1", "chapter-1")

    assert second.purchase_no == first.purchase_no
    assert second.entitlement == first.entitlement
    assert service.has_entitlement("acct-1", "chapter-1")
    assert SqlCommerceService(engine, FakeWallet()).has_entitlement("acct-1", "chapter-1")
    with engine.begin() as connection:
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM chapter_purchase_orders")).scalar_one()
            == 1
        )
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM chapter_purchase_items")).scalar_one()
            == 1
        )
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM chapter_entitlements")).scalar_one()
            == 1
        )
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM wallet_mutations")).scalar_one() == 1
        )


def test_sql_chapter_purchase_locks_wallet_before_spend() -> None:
    wallet = LockingFakeWallet()
    service, _ = _service(wallet)
    service.register_chapter_policy("chapter-1", ChapterPolicy(100, AccessMode.PURCHASED))

    service.purchase_chapter("acct-1", "chapter-1")

    assert wallet.events == ["lock", "spend"]


def test_sql_chapter_purchase_passes_revenue_context_to_finance_port() -> None:
    service, _ = _service(FakeWallet())
    service.register_chapter_policy("chapter-1", ChapterPolicy(100, AccessMode.PURCHASED))
    seen: list[tuple[str, str, str, int]] = []

    def record_revenue(
        connection: sa.Connection,
        chapter_id: str,
        source_ref: str,
        gross_cents: int,
    ) -> None:
        del connection
        seen.append((chapter_id, source_ref, "CHAPTER_PURCHASE", gross_cents))

    service.record_revenue_in_transaction = record_revenue

    purchase = service.purchase_chapter("acct-1", "chapter-1")

    assert seen == [("chapter-1", purchase.purchase_no, "CHAPTER_PURCHASE", 100)]
