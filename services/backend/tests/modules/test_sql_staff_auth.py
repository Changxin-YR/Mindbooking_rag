from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.core.auth import SessionSigner
from novel_platform.modules.platform.application import PlatformApplication
from novel_platform.modules.platform.repository import SqlPlatformRepository
from novel_platform.modules.platform.staff_auth import StaffAuthService, StaffMFARequired


def _schema() -> sa.MetaData:
    metadata = sa.MetaData()
    staff_accounts = sa.Table(
        "staff_accounts",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("employee_code", sa.String(128), nullable=False, unique=True),
        sa.Column("department", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
    )
    sa.Table(
        "staff_permissions",
        metadata,
        sa.Column("staff_id", sa.String(36), sa.ForeignKey(staff_accounts.c.id), primary_key=True),
        sa.Column("permission", sa.String(255), primary_key=True),
    )
    sa.Table(
        "staff_data_scopes",
        metadata,
        sa.Column("staff_id", sa.String(36), sa.ForeignKey(staff_accounts.c.id), primary_key=True),
        sa.Column("scope_type", sa.String(64), primary_key=True),
        sa.Column("scope_value", sa.String(255), primary_key=True),
    )
    sa.Table(
        "staff_credentials",
        metadata,
        sa.Column("staff_id", sa.String(36), sa.ForeignKey(staff_accounts.c.id), primary_key=True),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "staff_sessions",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("staff_id", sa.String(36), sa.ForeignKey(staff_accounts.c.id), nullable=False),
        sa.Column("token_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    return metadata


def test_sql_staff_repository_persists_credentials_permissions_and_revocation() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _schema().create_all(engine)
    platform = PlatformApplication(SqlPlatformRepository(engine))
    staff = platform.create_staff("sql-ops", "platform")
    platform.grant_permission(staff.id, "finance.read")
    platform.grant_data_scope(staff.id, "ALL", "*")
    auth = StaffAuthService(platform, SessionSigner("secret"), engine=engine)

    auth.set_password(staff.id, "SqlStaffPassword#123")
    session = auth.authenticate("sql-ops", "SqlStaffPassword#123")
    assert auth.verify(session.token) is not None
    assert platform.can_access(staff.id, "finance.read", "ALL", "*")

    auth.revoke_all_for_staff(staff.id)
    assert auth.verify(session.token) is None

    with engine.begin() as connection:
        assert (
            connection.execute(
                sa.text("SELECT COUNT(*) FROM staff_sessions WHERE staff_id = :staff_id"),
                {"staff_id": staff.id},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                sa.text("SELECT COUNT(*) FROM staff_credentials WHERE staff_id = :staff_id"),
                {"staff_id": staff.id},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                sa.text(
                    "SELECT COUNT(*) FROM staff_sessions "
                    "WHERE staff_id = :staff_id AND revoked_at IS NOT NULL"
                ),
                {"staff_id": staff.id},
            ).scalar_one()
            == 1
        )
        assert isinstance(datetime.now(UTC), datetime)


def test_sql_staff_mfa_recovery_code_is_one_time_and_audited() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = _schema()
    sa.Table(
        "staff_mfa_factors",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("staff_id", sa.String(36), nullable=False),
        sa.Column("factor_type", sa.String(32), nullable=False),
        sa.Column("secret_ciphertext", sa.Text, nullable=False),
        sa.Column("recovery_codes_hash", sa.Text),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "staff_mfa_audits",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("staff_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor_staff_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    platform = PlatformApplication(SqlPlatformRepository(engine))
    staff = platform.create_staff("mfa-sql", "finance")
    platform.grant_permission(staff.id, "finance.read")
    platform.grant_data_scope(staff.id, "ALL", "*")
    auth = StaffAuthService(
        platform, SessionSigner("secret"), engine=engine, mfa_encryption_key="key"
    )
    auth.set_password(staff.id, "SqlStaffPassword#123")

    with pytest.raises(StaffMFARequired):
        auth.authenticate("mfa-sql", "SqlStaffPassword#123")

    _, recovery_codes = auth.enroll_totp_with_recovery(
        staff.id, secret="JBSWY3DPEHPK3PXP", actor_staff_id=staff.id
    )
    assert recovery_codes
    assert auth.verify_totp(staff.id, recovery_codes[0])
    assert not auth.verify_totp(staff.id, recovery_codes[0])

    auth.disable_totp(staff.id, staff.id)
    assert not auth.has_active_totp(staff.id)
    with engine.begin() as connection:
        actions = (
            connection.execute(
                sa.text(
                    "SELECT action FROM staff_mfa_audits WHERE staff_id = :staff_id ORDER BY created_at"
                ),
                {"staff_id": staff.id},
            )
            .scalars()
            .all()
        )
    assert actions == ["ENABLED", "DISABLED"]
