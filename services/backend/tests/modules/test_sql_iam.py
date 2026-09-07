import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.core.auth import SessionSigner
from novel_platform.modules.iam.domain import RealNameSlotStatus
from novel_platform.modules.iam.repository import SqlIdentityRepository


def _repository() -> SqlIdentityRepository:
    metadata = sa.MetaData()
    identities = sa.Table(
        "login_identities",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("identity_type", sa.String(32), nullable=False),
        sa.Column("normalized_value", sa.String(255), nullable=False),
        sa.UniqueConstraint("identity_type", "normalized_value"),
    )
    accounts = sa.Table(
        "platform_accounts",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("account_no", sa.String(32), unique=True),
        sa.Column("nickname", sa.String(64)),
        sa.Column("login_name", sa.String(32), unique=True),
    )
    sa.Table(
        "login_identity_accounts",
        metadata,
        sa.Column("identity_id", sa.String(36), sa.ForeignKey(identities.c.id), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey(accounts.c.id), primary_key=True),
    )
    sa.Table(
        "login_identity_routing",
        metadata,
        sa.Column("identity_id", sa.String(36), sa.ForeignKey(identities.c.id), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey(accounts.c.id), nullable=False),
    )
    sa.Table(
        "real_name_subjects",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("id_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("encrypted_name", sa.Text, nullable=False),
        sa.Column("encrypted_id_number", sa.Text, nullable=False),
    )
    sa.Table(
        "account_real_name_links",
        metadata,
        sa.Column("account_id", sa.String(36), primary_key=True),
        sa.Column("real_name_subject_id", sa.String(36), nullable=False),
        sa.Column("slot_status", sa.String(32), nullable=False),
    )
    sa.Table(
        "account_password_credentials",
        metadata,
        sa.Column("account_id", sa.String(36), primary_key=True),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "auth_sessions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("token_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("revoked_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    return SqlIdentityRepository(engine, "test-real-name-encryption-key")


def test_sql_identity_repository_persists_accounts_passwords_and_real_name_links() -> None:
    repository = _repository()
    identity = repository.get_or_create_phone_identity("13800138000")
    account = repository.create_account()
    repository.link_account(identity.id, account.id)

    assert repository.default_account_id(identity.id) == account.id
    assert repository.accounts_for_identity(identity.id)[0].id == account.id
    repository.set_password_hash(account.id, "password-hash")
    assert repository.password_hash_for_account(account.id) == "password-hash"

    subject = repository.get_or_create_real_name_subject(
        "fingerprint", "姓名", "11010119900101001X"
    )
    link = repository.link_real_name_account(account.id, subject.id, RealNameSlotStatus.ACTIVE)
    assert link.real_name_subject_id == subject.id
    assert repository.has_active_real_name_link(account.id)
    assert repository.count_active_real_name_links("fingerprint") == 1
    with repository.engine.connect() as connection:
        encrypted_name, encrypted_id = connection.execute(
            sa.text("SELECT encrypted_name, encrypted_id_number FROM real_name_subjects")
        ).one()
    assert encrypted_name != "姓名"
    assert encrypted_id != "11010119900101001X"
    assert encrypted_name.startswith("gAAAA")


def test_sql_session_store_persists_and_revokes_account_session() -> None:
    repository = _repository()
    signer = SessionSigner("session-secret")
    signer.bind_session_store(repository)

    token = signer.issue("account-1")
    assert signer.verify(token) is not None

    rebuilt = SqlIdentityRepository(repository.engine, "test-real-name-encryption-key")
    rebuilt_signer = SessionSigner("session-secret")
    rebuilt_signer.bind_session_store(rebuilt)
    assert rebuilt_signer.verify(token) is not None

    rebuilt_signer.revoke(token)
    assert rebuilt_signer.verify(token) is None
