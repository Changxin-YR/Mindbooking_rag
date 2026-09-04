from collections import defaultdict
from contextlib import AbstractContextManager
from threading import RLock
from typing import Protocol
from uuid import uuid4

from novel_platform.modules.iam.domain import (
    AccountRealNameLink,
    AccountStatus,
    IdentityType,
    LoginIdentity,
    PlatformAccount,
    RealNameSlotStatus,
    RealNameSubject,
)


class IdentityRepository(Protocol):
    def get_or_create_phone_identity(self, phone: str) -> LoginIdentity: ...

    def create_account(self) -> PlatformAccount: ...

    def link_account(self, identity_id: str, account_id: str) -> None: ...

    def accounts_for_identity(self, identity_id: str) -> list[PlatformAccount]: ...

    def default_account_id(self, identity_id: str) -> str | None: ...

    def set_default_account(self, identity_id: str, account_id: str) -> None: ...

    def lock_real_name_subject(self, fingerprint: str) -> AbstractContextManager[None]: ...

    def get_or_create_real_name_subject(self, fingerprint: str, name: str) -> RealNameSubject: ...

    def link_real_name_account(
        self, account_id: str, subject_id: str, status: RealNameSlotStatus
    ) -> AccountRealNameLink: ...

    def real_name_link_for_account(self, account_id: str) -> AccountRealNameLink | None: ...

    def count_active_real_name_links(self, fingerprint: str) -> int: ...


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

    def get_or_create_phone_identity(self, phone: str) -> LoginIdentity:
        with self._guard:
            identity = self._identity_by_phone.get(phone)
            if identity is None:
                identity = LoginIdentity(uuid4().hex, IdentityType.PHONE, phone)
                self._identity_by_phone[phone] = identity
            return identity

    def create_account(self) -> PlatformAccount:
        with self._guard:
            account = PlatformAccount(uuid4().hex, AccountStatus.ACTIVE)
            self._accounts[account.id] = account
            return account

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

    def get_or_create_real_name_subject(self, fingerprint: str, name: str) -> RealNameSubject:
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


class _RLockContext(AbstractContextManager[None]):
    def __init__(self, lock: RLock) -> None:
        self._lock = lock

    def __enter__(self) -> None:
        self._lock.acquire()

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self._lock.release()
