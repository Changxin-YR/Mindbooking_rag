import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from novel_platform.core.auth import SessionSigner
from novel_platform.modules.content.api import build_content_routers
from novel_platform.modules.content.application import ContentService
from novel_platform.modules.content.domain import CommercialPolicy
from novel_platform.modules.risk.domain import RiskSignalStatus
from novel_platform.modules.risk.sql_service import SqlRiskService


class _EntitlementPort:
    def has_entitlement(self, account_id: str, chapter_id: str) -> bool:
        return account_id == "acct-1" and chapter_id.startswith("CH_")


def _engine() -> sa.Engine:
    metadata = sa.MetaData()
    orders = sa.Table(
        "risk_order_facts",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("amount_coin", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "risk_signals",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("signal_type", sa.String(64), nullable=False),
        sa.Column("order_id", sa.String(64), sa.ForeignKey(orders.c.id), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "login_risk_signals",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("browser", sa.String(64), nullable=False),
        sa.Column("operating_system", sa.String(64), nullable=False),
        sa.Column("ip", sa.String(64), nullable=False),
        sa.Column("region", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.Text, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "risk_watchlist_entries",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_value", sa.String(256), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("release_reason", sa.Text),
        sa.Column("evidence_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    return engine


def test_sql_risk_reloads_login_and_watchlist_facts_and_release_audit() -> None:
    engine = _engine()
    service = SqlRiskService(engine)
    login = service.record_login(
        "acct-1", "device-1", "Chrome", "Windows", "198.51.100.1", "CN", "ua"
    )
    entry = service.add_watchlist("IP", "198.51.100.1", "suspicious login", "case-1")

    rebuilt = SqlRiskService(engine)
    assert rebuilt.get_login_signal(login.id) == login
    assert rebuilt.is_watchlisted("IP", "198.51.100.1")

    released = rebuilt.release_watchlist(entry.id, "manual review", "evidence-1", "case-1")
    assert released.status == "RELEASED"
    assert rebuilt.watchlist(entry.id) == released
    assert not rebuilt.is_watchlisted("IP", "198.51.100.1")
    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT status, case_id, release_reason, evidence_id "
                "FROM risk_watchlist_entries WHERE id = :id"
            ),
            {"id": entry.id},
        ).one()
    assert row == ("RELEASED", "case-1", "manual review", "evidence-1")


def test_sql_risk_reloads_observed_signal_and_freeze_transition() -> None:
    engine = _engine()
    service = SqlRiskService(engine)
    order = service.record_order("purchase-1", "acct-1", 1000)
    signal = service.observe("acct-1", "SELF_DEALING", order.id)
    assert signal.status is RiskSignalStatus.OBSERVE

    rebuilt = SqlRiskService(engine)
    frozen = rebuilt.freeze(signal.id)
    assert frozen.status is RiskSignalStatus.FROZEN
    assert rebuilt.get_signal(signal.id).status is RiskSignalStatus.FROZEN
    assert rebuilt.get_order(order.id) == order

    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM risk_signals WHERE id = :id"), {"id": signal.id}
            ).scalar_one()
            == 1
        )


def test_reader_access_keeps_free_chapters_public_but_requires_session_for_vip() -> None:
    content = ContentService()
    book = content.create_book("author-1", "Book")
    volume = content.create_volume(book.id, "Volume 1", 1)
    free = content.create_chapter(volume.id, "Free", CommercialPolicy.FREE)
    vip = content.create_chapter(volume.id, "VIP", CommercialPolicy.VIP)
    free_version = content.create_chapter_version(free.id, content.save_draft(free.id, "free").id)
    vip_version = content.create_chapter_version(vip.id, content.save_draft(vip.id, "vip").id)
    content.publish_fixed_versions(book.id, [free_version.id, vip_version.id])
    app = FastAPI()
    app.state.session_signer = SessionSigner("test-secret")
    app.include_router(build_content_routers(content)[0])
    client = TestClient(app)

    assert client.get(f"/api/v1/books/{book.id}/chapters/{free.id}").status_code == 200
    assert client.get(f"/api/v1/books/{book.id}/chapters/{vip.id}").status_code == 403


def test_reader_vip_access_returns_clear_403_when_commerce_port_is_unavailable() -> None:
    content = ContentService()
    book = content.create_book("author-1", "Book")
    volume = content.create_volume(book.id, "Volume 1", 1)
    chapter = content.create_chapter(volume.id, "VIP", CommercialPolicy.VIP)
    version = content.create_chapter_version(chapter.id, content.save_draft(chapter.id, "vip").id)
    content.publish_fixed_versions(book.id, [version.id])
    app = FastAPI()
    signer = SessionSigner("test-secret")
    app.state.session_signer = signer
    app.include_router(build_content_routers(content)[0])
    client = TestClient(app)

    response = client.get(
        f"/api/v1/books/{book.id}/chapters/{chapter.id}",
        headers={"Authorization": f"Bearer {signer.issue('acct-1')}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CHAPTER_ACCESS_PROVIDER_UNAVAILABLE"


def test_reader_vip_access_rejects_anonymous_request_before_commerce_lookup() -> None:
    content = ContentService()
    book = content.create_book("author-1", "Book")
    volume = content.create_volume(book.id, "Volume 1", 1)
    chapter = content.create_chapter(volume.id, "VIP", CommercialPolicy.VIP)
    version = content.create_chapter_version(chapter.id, content.save_draft(chapter.id, "vip").id)
    content.publish_fixed_versions(book.id, [version.id])
    app = FastAPI()
    app.state.session_signer = SessionSigner("test-secret")
    app.state.commerce_service = _EntitlementPort()
    app.include_router(build_content_routers(content)[0])

    response = TestClient(app).get(f"/api/v1/books/{book.id}/chapters/{chapter.id}")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CHAPTER_ACCESS_REQUIRED"


def test_reader_vip_access_uses_commerce_entitlement_port() -> None:
    content = ContentService()
    book = content.create_book("author-1", "Book")
    volume = content.create_volume(book.id, "Volume 1", 1)
    chapter = content.create_chapter(volume.id, "VIP", CommercialPolicy.VIP)
    version = content.create_chapter_version(chapter.id, content.save_draft(chapter.id, "vip").id)
    content.publish_fixed_versions(book.id, [version.id])
    app = FastAPI()
    signer = SessionSigner("test-secret")
    app.state.session_signer = signer
    app.state.commerce_service = _EntitlementPort()
    app.include_router(build_content_routers(content)[0])
    response = TestClient(app).get(
        f"/api/v1/books/{book.id}/chapters/{chapter.id}",
        headers={"Authorization": f"Bearer {signer.issue('acct-1')}"},
    )

    assert response.status_code == 200
    assert response.json()["access"] == "PURCHASED"
