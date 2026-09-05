from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine

from novel_platform.modules.wallet.domain import AssetType
from novel_platform.modules.wallet.sql_service import SqlWalletService


def _schema(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE wallet_accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, account_id VARCHAR(64) UNIQUE NOT NULL, recharge_coin BIGINT NOT NULL DEFAULT 0, gift_coin BIGINT NOT NULL DEFAULT 0, created_at DATETIME NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE wallet_journals (id INTEGER PRIMARY KEY AUTOINCREMENT, account_id VARCHAR(64) NOT NULL, journal_type VARCHAR(32) NOT NULL, idempotency_key VARCHAR(128), created_at DATETIME NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE wallet_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, journal_id INTEGER NOT NULL, account_id VARCHAR(64) NOT NULL, asset_type VARCHAR(24) NOT NULL, amount BIGINT NOT NULL, reason VARCHAR(64) NOT NULL, created_at DATETIME NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE wallet_asset_lots (id INTEGER PRIMARY KEY AUTOINCREMENT, lot_id VARCHAR(64) UNIQUE NOT NULL, account_id VARCHAR(64) NOT NULL, asset_type VARCHAR(24) NOT NULL, origin VARCHAR(64) NOT NULL, available_amount BIGINT NOT NULL, issued_at DATETIME NOT NULL, expires_at DATETIME, source_ref VARCHAR(128), issued_amount BIGINT)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE wallet_lot_allocations (id INTEGER PRIMARY KEY AUTOINCREMENT, lot_id VARCHAR(64) NOT NULL, journal_id INTEGER NOT NULL, allocation_type VARCHAR(32) NOT NULL, amount BIGINT NOT NULL)"
        )


def test_sql_wallet_locks_lots_and_preserves_refund_source_facts() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _schema(engine)
    wallet = SqlWalletService(engine)
    expiry = datetime.now(UTC) + timedelta(days=1)
    wallet.grant_recharge_coin("acct-1", 100, source_ref="RECH-1")
    wallet.grant_gift_coin("acct-1", 50, "PROMO", expiry, source_ref="RECH-1")

    allocations = wallet.spend("acct-1", 120, reason="CHAPTER_PURCHASE")
    snapshot = wallet.source_snapshot("acct-1", "RECH-1")

    assert [allocation.asset_type for allocation in allocations] == [
        AssetType.GIFT,
        AssetType.RECHARGE,
    ]
    assert snapshot.consumed_recharge_coin == 70
    assert snapshot.consumed_promo_gift_coin == 50
    assert wallet.balance("acct-1").total_coin == 30
    assert len(wallet.entries("acct-1")) == 4

    wallet.recover_source_assets("acct-1", "RECH-1")
    assert wallet.balance("acct-1").total_coin == 0
    assert wallet.source_snapshot("acct-1", "RECH-1").remaining_recharge_coin == 0


def test_sql_wallet_can_recover_assets_on_a_caller_owned_connection() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _schema(engine)
    wallet = SqlWalletService(engine)
    wallet.grant_recharge_coin("acct-1", 100, source_ref="RECH-1")

    with engine.begin() as connection:
        wallet.recover_source_assets_in_transaction(connection, "acct-1", "RECH-1")

    assert wallet.balance("acct-1").total_coin == 0


def test_sql_wallet_gift_spend_mode_excludes_gift_lots() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _schema(engine)
    wallet = SqlWalletService(engine)
    wallet.grant_gift_coin("acct-1", 20, "PROMO", None, source_ref="gift")
    wallet.grant_recharge_coin("acct-1", 20, source_ref="recharge")

    with engine.begin() as connection:
        wallet.spend_in_transaction(
            connection, "acct-1", 15, reason="GIFT", spend_mode="RECHARGE_ONLY"
        )

    assert wallet.balance("acct-1").recharge_coin == 5
    assert wallet.balance("acct-1").gift_coin == 20
