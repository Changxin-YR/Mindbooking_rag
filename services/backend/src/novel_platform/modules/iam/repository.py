from base64 import urlsafe_b64encode
from collections import defaultdict
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from os import getenv
from threading import RLock
from typing import Protocol
from uuid import uuid4

import sqlalchemy as sa
from cryptography.fernet import Fernet
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from novel_platform.modules.iam.domain import (
    AccountLoginNameTakenError,
    AccountRealNameLink,
    AccountStatus,
    IdentityType,
    LoginIdentity,
    PlatformAccount,
    RealNameSlotStatus,
    RealNameSubject,
    public_account_no,
)


class IdentityRepository(Protocol):
    def get_or_create_phone_identity(self, phone: str) -> LoginIdentity: ...

    def create_account(self) -> PlatformAccount: ...

    def account_for_id(self, account_id: str) -> PlatformAccount | None: ...

    def update_account_profile(
        self, account_id: str, *, nickname: str | None = None, login_name: str | None = None
    ) -> PlatformAccount: ...

    def link_account(self, identity_id: str, account_id: str) -> None: ...

    def accounts_for_identity(self, identity_id: str) -> list[PlatformAccount]: ...

    def default_account_id(self, identity_id: str) -> str | None: ...

    def set_default_account(self, identity_id: str, account_id: str) -> None: ...

    def lock_real_name_subject(self, fingerprint: str) -> AbstractContextManager[None]: ...

    def get_or_create_real_name_subject(
        self, fingerprint: str, name: str, identity_document: str | None = None
    ) -> RealNameSubject: ...

    def link_real_name_account(
        self, account_id: str, subject_id: str, status: RealNameSlotStatus
    ) -> AccountRealNameLink: ...

    def real_name_link_for_account(self, account_id: str) -> AccountRealNameLink | None: ...

    def has_active_real_name_link(self, account_id: str) -> bool: ...

    def count_active_real_name_links(self, fingerprint: str) -> int: ...

    def set_password_hash(self, account_id: str, password_hash: str) -> None: ...

    def password_hash_for_account(self, account_id: str) -> str | None: ...


class InMemoryIdentityRepository:
    """Development repository; production wiring must provide a transactional adapter."""

    def __init__(self) -> None:
        self._guard = RLock()
        self._identity_by_phone: dict[str, LoginIdentity] = {}
        self._accounts: dict[str, PlatformAccount] = {}
        self._accounts_by_identity: defaultdict[str, list[str]] = defaultdict(list)
        self._routing: dict[str, str] = {}
        self._subjects_by_fingerprint: dict[str, RealNameSubject] = {}
        self._subjects_by_id: dict[str, RealNameSubject] = {}
        self._real_name_links: dict[str, AccountRealNameLink] = {}
        self._real_name_locks: dict[str, RLock] = {}
        self._real_name_lock_guard = RLock()
        self._password_hashes: dict[str, str] = {}

    def get_or_create_phone_identity(self, phone: str) -> LoginIdentity:
        with self._guard:
            identity = self._identity_by_phone.get(phone)
            if identity is None:
                identity = LoginIdentity(uuid4().hex, IdentityType.PHONE, phone)
                self._identity_by_phone[phone] = identity
            return identity

    def create_account(self) -> PlatformAccount:
        with self._guard:
            account_id = uuid4().hex
            account = PlatformAccount(account_id, AccountStatus.ACTIVE, public_account_no(account_id))
            self._accounts[account.id] = account
            return account

    def account_for_id(self, account_id: str) -> PlatformAccount | None:
        with self._guard:
            return self._accounts.get(account_id)

    def update_account_profile(
        self, account_id: str, *, nickname: str | None = None, login_name: str | None = None
    ) -> PlatformAccount:
        with self._guard:
            account = self._accounts.get(account_id)
            if account is None:
                raise KeyError(account_id)
            normalized_login_name = login_name.lower() if login_name is not None else None
            if normalized_login_name is not None:
                for existing in self._accounts.values():
                    if existing.id != account_id and existing.login_name == normalized_login_name:
                        raise AccountLoginNameTakenError("login_name is already in use")
            updated = PlatformAccount(
                account.id,
                account.status,
                account.account_no or public_account_no(account.id),
                account.nickname if nickname is None else nickname,
                account.login_name if normalized_login_name is None else normalized_login_name,
            )
            self._accounts[account_id] = updated
            return updated

    def link_account(self, identity_id: str, account_id: str) -> None:
        with self._guard:
            if account_id not in self._accounts:
                raise KeyError(account_id)
            if account_id not in self._accounts_by_identity[identity_id]:
                self._accounts_by_identity[identity_id].append(account_id)
            self._routing.setdefault(identity_id, account_id)

    def accounts_for_identity(self, identity_id: str) -> list[PlatformAccount]:
        with self._guard:
            return [
                self._accounts[account_id] for account_id in self._accounts_by_identity[identity_id]
            ]

    def default_account_id(self, identity_id: str) -> str | None:
        with self._guard:
            return self._routing.get(identity_id)

    def set_default_account(self, identity_id: str, account_id: str) -> None:
        with self._guard:
            if account_id not in self._accounts_by_identity[identity_id]:
                raise KeyError(account_id)
            self._routing[identity_id] = account_id

    def lock_real_name_subject(self, fingerprint: str) -> AbstractContextManager[None]:
        with self._real_name_lock_guard:
            lock = self._real_name_locks.setdefault(fingerprint, RLock())
        return _RLockContext(lock)

    def get_or_create_real_name_subject(
        self, fingerprint: str, name: str, identity_document: str | None = None
    ) -> RealNameSubject:
        del identity_document
        with self._guard:
            subject = self._subjects_by_fingerprint.get(fingerprint)
            if subject is None:
                subject = RealNameSubject(uuid4().hex, fingerprint, name.strip())
                self._subjects_by_fingerprint[fingerprint] = subject
                self._subjects_by_id[subject.id] = subject
            return subject

    def link_real_name_account(
        self, account_id: str, subject_id: str, status: RealNameSlotStatus
    ) -> AccountRealNameLink:
        with self._guard:
            link = AccountRealNameLink(account_id, subject_id, status)
            self._real_name_links[account_id] = link
            return link

    def real_name_link_for_account(self, account_id: str) -> AccountRealNameLink | None:
        with self._guard:
            return self._real_name_links.get(account_id)

    def has_active_real_name_link(self, account_id: str) -> bool:
        with self._guard:
            link = self._real_name_links.get(account_id)
            return link is not None and link.slot_status is RealNameSlotStatus.ACTIVE

    def count_active_real_name_links(self, fingerprint: str) -> int:
        with self._guard:
            subject = self._subjects_by_fingerprint.get(fingerprint)
            if subject is None:
                return 0
            return sum(
                link.real_name_subject_id == subject.id
                and link.slot_status
                in {RealNameSlotStatus.ACTIVE, RealNameSlotStatus.PENDING_RELEASE}
                for link in self._real_name_links.values()
            )

    def set_password_hash(self, account_id: str, password_hash: str) -> None:
        with self._guard:
            if account_id not in self._accounts:
                raise KeyError(account_id)
            self._password_hashes[account_id] = password_hash

    def password_hash_for_account(self, account_id: str) -> str | None:
        with self._guard:
            return self._password_hashes.get(account_id)


class _RLockContext(AbstractContextManager[None]):
    def __init__(self, lock: RLock) -> None:
        self._lock = lock

    def __enter__(self) -> None:
        self._lock.acquire()

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self._lock.release()


login_identities = sa.table(
    "login_identities",
    sa.column("id", sa.String),
    sa.column("identity_type", sa.String),
    sa.column("normalized_value", sa.String),
)
platform_accounts = sa.table(
    "platform_accounts",
    sa.column("id", sa.String),
    sa.column("status", sa.String),
    sa.column("account_no", sa.String),
    sa.column("nickname", sa.String),
    sa.column("login_name", sa.String),
)
login_identity_accounts = sa.table(
    "login_identity_accounts",
    sa.column("identity_id", sa.String),
    sa.column("account_id", sa.String),
)
login_identity_routing = sa.table(
    "login_identity_routing",
    sa.column("identity_id", sa.String),
    sa.column("account_id", sa.String),
)
real_name_subjects = sa.table(
    "real_name_subjects",
    sa.column("id", sa.String),
    sa.column("id_fingerprint", sa.String),
    sa.column("encrypted_name", sa.Text),
    sa.column("encrypted_id_number", sa.Text),
)
account_real_name_links = sa.table(
    "account_real_name_links",
    sa.column("account_id", sa.String),
    sa.column("real_name_subject_id", sa.String),
    sa.column("slot_status", sa.String),
)
account_password_credentials = sa.table(
    "account_password_credentials",
    sa.column("account_id", sa.String),
    sa.column("password_hash", sa.String),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)
auth_sessions = sa.table(
    "auth_sessions",
    sa.column("id", sa.String),
    sa.column("account_id", sa.String),
    sa.column("token_fingerprint", sa.String),
    sa.column("expires_at", sa.DateTime),
    sa.column("revoked_at", sa.DateTime),
    sa.column("created_at", sa.DateTime),
)


class SqlIdentityRepository:
    """Transactional adapter for the identity and real-name foundation tables."""

    def __init__(self, engine: Engine, encryption_key: str | None = None) -> None:
        self.engine = engine
        raw_key = encryption_key or getenv("REAL_NAME_ENCRYPTION_KEY") or getenv("SESSION_SECRET")
        if not raw_key:
            raise ValueError("real-name encryption key is required for SQL persistence")
        self._fernet = Fernet(urlsafe_b64encode(sha256(raw_key.encode("utf-8")).digest()))

    def get_or_create_phone_identity(self, phone: str) -> LoginIdentity:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(
                        login_identities.c.id,
                        login_identities.c.identity_type,
                        login_identities.c.normalized_value,
                    ).where(
                        login_identities.c.identity_type == IdentityType.PHONE.value,
                        login_identities.c.normalized_value == phone,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                identity = LoginIdentity(uuid4().hex, IdentityType.PHONE, phone)
                try:
                    connection.execute(
                        login_identities.insert().values(
                            id=identity.id,
                            identity_type=identity.identity_type.value,
                            normalized_value=identity.normalized_value,
                        )
                    )
                    return identity
                except IntegrityError:
                    row = (
                        connection.execute(
                            sa.select(
                                login_identities.c.id,
                                login_identities.c.identity_type,
                                login_identities.c.normalized_value,
                            ).where(
                                login_identities.c.identity_type == IdentityType.PHONE.value,
                                login_identities.c.normalized_value == phone,
                            )
                        )
                        .mappings()
                        .one()
                    )
            return LoginIdentity(
                str(row["id"]),
                IdentityType(str(row["identity_type"])),
                str(row["normalized_value"]),
            )

    def create_account(self) -> PlatformAccount:
        account_id = uuid4().hex
        account = PlatformAccount(account_id, AccountStatus.ACTIVE, public_account_no(account_id))
        with self.engine.begin() as connection:
            connection.execute(
                platform_accounts.insert().values(
                    id=account.id,
                    status=account.status.value,
                    account_no=account.account_no,
                )
            )
        return account

    def account_for_id(self, account_id: str) -> PlatformAccount | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(
                        platform_accounts.c.id,
                        platform_accounts.c.status,
                        platform_accounts.c.account_no,
                        platform_accounts.c.nickname,
                        platform_accounts.c.login_name,
                    ).where(platform_accounts.c.id == account_id)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            account_no = str(row["account_no"] or public_account_no(account_id))
            if row["account_no"] is None:
                connection.execute(
                    platform_accounts.update()
                    .where(platform_accounts.c.id == account_id)
                    .values(account_no=account_no)
                )
            return PlatformAccount(
                str(row["id"]),
                AccountStatus(str(row["status"])),
                account_no,
                str(row["nickname"]) if row["nickname"] is not None else None,
                str(row["login_name"]) if row["login_name"] is not None else None,
            )
    def update_account_profile(
        self, account_id: str, *, nickname: str | None = None, login_name: str | None = None
    ) -> PlatformAccount:
        normalized_login_name = login_name.lower() if login_name is not None else None
        try:
            with self.engine.begin() as connection:
                exists = connection.execute(
                    sa.select(platform_accounts.c.id).where(platform_accounts.c.id == account_id)
                ).scalar_one_or_none()
                if exists is None:
                    raise KeyError(account_id)
                if normalized_login_name is not None:
                    duplicate = connection.execute(
                        sa.select(platform_accounts.c.id).where(
                            platform_accounts.c.login_name == normalized_login_name,
                            platform_accounts.c.id != account_id,
                        )
                    ).scalar_one_or_none()
                    if duplicate is not None:
                        raise AccountLoginNameTakenError("login_name is already in use")
                values: dict[str, str | None] = {}
                if nickname is not None:
                    values["nickname"] = nickname
                if normalized_login_name is not None:
                    values["login_name"] = normalized_login_name
                if values:
                    connection.execute(
                        platform_accounts.update()
                        .where(platform_accounts.c.id == account_id)
                        .values(**values)
                    )
            account = self.account_for_id(account_id)
            if account is None:
                raise KeyError(account_id)
            return account
        except IntegrityError as exc:
            raise AccountLoginNameTakenError("login_name is already in use") from exc

    def link_account(self, identity_id: str, account_id: str) -> None:
        with self.engine.begin() as connection:
            account = connection.execute(
                sa.select(platform_accounts.c.id).where(platform_accounts.c.id == account_id)
            ).scalar_one_or_none()
            if account is None:
                raise KeyError(account_id)
            try:
                connection.execute(
                    login_identity_accounts.insert().values(
                        identity_id=identity_id, account_id=account_id
                    )
                )
            except IntegrityError:
                pass
            connection.execute(
                login_identity_routing.insert().from_select(
                    [login_identity_routing.c.identity_id, login_identity_routing.c.account_id],
                    sa.select(
                        sa.literal(identity_id),
                        sa.literal(account_id),
                    ).where(
                        ~sa.exists(
                            sa.select(login_identity_routing.c.identity_id).where(
                                login_identity_routing.c.identity_id == identity_id
                            )
                        )
                    ),
                )
            )

    def accounts_for_identity(self, identity_id: str) -> list[PlatformAccount]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(
                    platform_accounts.c.id,
                    platform_accounts.c.status,
                    platform_accounts.c.account_no,
                    platform_accounts.c.nickname,
                    platform_accounts.c.login_name,
                )
                .select_from(
                    platform_accounts.join(
                        login_identity_accounts,
                        platform_accounts.c.id == login_identity_accounts.c.account_id,
                    )
                )
                .where(login_identity_accounts.c.identity_id == identity_id)
                .order_by(platform_accounts.c.id)
            ).mappings()
            return [
                PlatformAccount(
                    str(row["id"]),
                    AccountStatus(str(row["status"])),
                    str(row["account_no"] or public_account_no(str(row["id"]))),
                    str(row["nickname"]) if row["nickname"] is not None else None,
                    str(row["login_name"]) if row["login_name"] is not None else None,
                )
                for row in rows
            ]

    def default_account_id(self, identity_id: str) -> str | None:
        with self.engine.begin() as connection:
            return connection.execute(
                sa.select(login_identity_routing.c.account_id).where(
                    login_identity_routing.c.identity_id == identity_id
                )
            ).scalar_one_or_none()

    def set_default_account(self, identity_id: str, account_id: str) -> None:
        with self.engine.begin() as connection:
            linked = connection.execute(
                sa.select(login_identity_accounts.c.account_id).where(
                    login_identity_accounts.c.identity_id == identity_id,
                    login_identity_accounts.c.account_id == account_id,
                )
            ).scalar_one_or_none()
            if linked is None:
                raise KeyError(account_id)
            result = connection.execute(
                login_identity_routing.update()
                .where(login_identity_routing.c.identity_id == identity_id)
                .values(account_id=account_id)
            )
            if result.rowcount == 0:
                connection.execute(
                    login_identity_routing.insert().values(
                        identity_id=identity_id, account_id=account_id
                    )
                )

    @contextmanager
    def lock_real_name_subject(self, fingerprint: str) -> Iterator[None]:
        if self.engine.dialect.name != "mysql":
            yield
            return
        lock_name = f"novel_platform:rn:{sha256(fingerprint.encode()).hexdigest()[:45]}"
        with self.engine.begin() as connection:
            acquired = connection.execute(
                sa.text("SELECT GET_LOCK(:lock_name, 10)"), {"lock_name": lock_name}
            ).scalar_one()
            if acquired != 1:
                raise TimeoutError("real-name subject lock timeout")
            try:
                yield
            finally:
                connection.execute(
                    sa.text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name}
                )

    def get_or_create_real_name_subject(
        self, fingerprint: str, name: str, identity_document: str | None = None
    ) -> RealNameSubject:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(
                        real_name_subjects.c.id,
                        real_name_subjects.c.id_fingerprint,
                    ).where(real_name_subjects.c.id_fingerprint == fingerprint)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                subject = RealNameSubject(uuid4().hex, fingerprint, name.strip())
                try:
                    connection.execute(
                        real_name_subjects.insert().values(
                            id=subject.id,
                            id_fingerprint=fingerprint,
                            encrypted_name=self._encrypt(name),
                            encrypted_id_number=self._encrypt(identity_document or fingerprint),
                        )
                    )
                    return subject
                except IntegrityError:
                    row = (
                        connection.execute(
                            sa.select(
                                real_name_subjects.c.id,
                                real_name_subjects.c.id_fingerprint,
                            ).where(real_name_subjects.c.id_fingerprint == fingerprint)
                        )
                        .mappings()
                        .one()
                    )
            return RealNameSubject(str(row["id"]), str(row["id_fingerprint"]), "[PROTECTED]")

    def _encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.strip().encode("utf-8")).decode("ascii")

    def link_real_name_account(
        self, account_id: str, subject_id: str, status: RealNameSlotStatus
    ) -> AccountRealNameLink:
        with self.engine.begin() as connection:
            connection.execute(
                account_real_name_links.insert().values(
                    account_id=account_id,
                    real_name_subject_id=subject_id,
                    slot_status=status.value,
                )
            )
        return AccountRealNameLink(account_id, subject_id, status)

    def real_name_link_for_account(self, account_id: str) -> AccountRealNameLink | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(
                        account_real_name_links.c.account_id,
                        account_real_name_links.c.real_name_subject_id,
                        account_real_name_links.c.slot_status,
                    ).where(account_real_name_links.c.account_id == account_id)
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return AccountRealNameLink(
            str(row["account_id"]),
            str(row["real_name_subject_id"]),
            RealNameSlotStatus(str(row["slot_status"])),
        )

    def has_active_real_name_link(self, account_id: str) -> bool:
        link = self.real_name_link_for_account(account_id)
        return link is not None and link.slot_status is RealNameSlotStatus.ACTIVE

    def count_active_real_name_links(self, fingerprint: str) -> int:
        with self.engine.begin() as connection:
            return int(
                connection.execute(
                    sa.select(sa.func.count())
                    .select_from(
                        account_real_name_links.join(
                            real_name_subjects,
                            account_real_name_links.c.real_name_subject_id
                            == real_name_subjects.c.id,
                        )
                    )
                    .where(
                        real_name_subjects.c.id_fingerprint == fingerprint,
                        account_real_name_links.c.slot_status.in_(
                            [
                                RealNameSlotStatus.ACTIVE.value,
                                RealNameSlotStatus.PENDING_RELEASE.value,
                            ]
                        ),
                    )
                ).scalar_one()
            )

    def set_password_hash(self, account_id: str, password_hash: str) -> None:
        now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
        with self.engine.begin() as connection:
            result = connection.execute(
                account_password_credentials.update()
                .where(account_password_credentials.c.account_id == account_id)
                .values(password_hash=password_hash, updated_at=now)
            )
            if result.rowcount == 0:
                try:
                    connection.execute(
                        account_password_credentials.insert().values(
                            account_id=account_id,
                            password_hash=password_hash,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                except IntegrityError:
                    connection.execute(
                        account_password_credentials.update()
                        .where(account_password_credentials.c.account_id == account_id)
                        .values(password_hash=password_hash, updated_at=now)
                    )

    def password_hash_for_account(self, account_id: str) -> str | None:
        with self.engine.begin() as connection:
            return connection.execute(
                sa.select(account_password_credentials.c.password_hash).where(
                    account_password_credentials.c.account_id == account_id
                )
            ).scalar_one_or_none()

    def create_session(
        self, session_id: str, account_id: str, token_fingerprint: str, expires_at: datetime
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
        with self.engine.begin() as connection:
            connection.execute(
                auth_sessions.insert().values(
                    id=session_id,
                    account_id=account_id,
                    token_fingerprint=token_fingerprint,
                    expires_at=expires_at.replace(tzinfo=None),
                    revoked_at=None,
                    created_at=now,
                )
            )

    def session_active(
        self, session_id: str, account_id: str, token_fingerprint: str, expires_at: int
    ) -> bool:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(
                        auth_sessions.c.account_id,
                        auth_sessions.c.token_fingerprint,
                        auth_sessions.c.expires_at,
                        auth_sessions.c.revoked_at,
                    ).where(auth_sessions.c.id == session_id)
                )
                .mappings()
                .one_or_none()
            )
        if row is None or row["account_id"] != account_id:
            return False
        stored_expires = row["expires_at"]
        if stored_expires.tzinfo is None:
            stored_expires = stored_expires.replace(tzinfo=UTC)
        return (
            row["token_fingerprint"] == token_fingerprint
            and row["revoked_at"] is None
            and stored_expires > datetime.now(UTC)
            and stored_expires.timestamp() >= expires_at - 1
        )

    def revoke_session(self, session_id: str, token_fingerprint: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                auth_sessions.update()
                .where(
                    auth_sessions.c.id == session_id,
                    auth_sessions.c.token_fingerprint == token_fingerprint,
                )
                .values(revoked_at=datetime.now(UTC).replace(tzinfo=None, microsecond=0))
            )
