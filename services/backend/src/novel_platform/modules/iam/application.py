from dataclasses import dataclass
from hashlib import pbkdf2_hmac
from hmac import compare_digest
from os import getenv
from secrets import token_bytes

from novel_platform.core.auth import SessionSigner
from novel_platform.modules.iam.domain import (
    AccountLoginNameTakenError,
    AccountRealNameLink,
    InvalidIdentityDocumentError,
    InvalidLoginNameError,
    InvalidNicknameError,
    InvalidPhoneError,
    LoginIdentity,
    PlatformAccount,
    RealNameSlotStatus,
    identity_document_fingerprint,
    normalize_login_name,
    normalize_nickname,
    normalize_phone,
)
from novel_platform.modules.iam.repository import IdentityRepository


class IdentityNotFoundError(LookupError):
    pass


class AccountNotFoundError(LookupError):
    pass


class AccountAlreadyRealNamedError(ValueError):
    pass


class RealNameSlotLimitError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AccountRegistration:
    account_id: str
    identity_id: str
    phone: str
    account_no: str
    nickname: str | None
    login_name: str | None


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    account_id: str
    token: str


class IdentityApplication:
    def __init__(self, repository: IdentityRepository, signer: SessionSigner | None = None) -> None:
        self.repository = repository
        self.signer = signer or SessionSigner(getenv("SESSION_SECRET", "dev-only-session-secret"))
        bind_store = getattr(self.signer, "bind_session_store", None)
        if callable(bind_store) and all(
            callable(getattr(repository, name, None))
            for name in ("create_session", "session_active", "revoke_session")
        ):
            bind_store(repository)

    def register_phone_account(
        self, phone: str, password: str | None = None
    ) -> AccountRegistration:
        normalized_phone = normalize_phone(phone)
        identity = self.repository.get_or_create_phone_identity(normalized_phone)
        account = self.repository.create_account()
        self.repository.link_account(identity.id, account.id)
        if password is not None:
            self.set_password(account.id, password)
        return AccountRegistration(
            account.id,
            identity.id,
            normalized_phone,
            account.account_no,
            account.nickname,
            account.login_name,
        )

    def profile_for_account(self, account_id: str) -> PlatformAccount:
        account = self.repository.account_for_id(account_id)
        if account is None:
            raise AccountNotFoundError("account does not exist")
        return account

    def update_profile(
        self,
        account_id: str,
        *,
        nickname: str | None = None,
        login_name: str | None = None,
    ) -> PlatformAccount:
        self.profile_for_account(account_id)
        normalized_nickname = normalize_nickname(nickname) if nickname is not None else None
        normalized_login_name = normalize_login_name(login_name) if login_name is not None else None
        return self.repository.update_account_profile(
            account_id, nickname=normalized_nickname, login_name=normalized_login_name
        )

    def set_password(self, account_id: str, password: str) -> None:
        if not isinstance(password, str) or len(password) < 8:
            raise ValueError("password must contain at least 8 characters")
        self.repository.set_password_hash(account_id, _hash_password(password))

    def authenticate_phone(self, phone: str, password: str) -> AuthenticatedSession:
        account = self.default_account_for_phone(phone)
        password_hash = self.repository.password_hash_for_account(account.id)
        if password_hash is None or not _verify_password(password, password_hash):
            raise InvalidCredentialsError("invalid phone or password")
        return AuthenticatedSession(account.id, self.signer.issue(account.id))

    def accounts_for_phone(self, phone: str) -> list[PlatformAccount]:
        identity = self._phone_identity(phone)
        return self.repository.accounts_for_identity(identity.id)

    def default_account_for_phone(self, phone: str) -> PlatformAccount:
        identity = self._phone_identity(phone)
        account_id = self.repository.default_account_id(identity.id)
        if account_id is None:
            raise AccountNotFoundError("phone has no account")
        accounts = {
            account.id: account for account in self.repository.accounts_for_identity(identity.id)
        }
        try:
            return accounts[account_id]
        except KeyError as exc:
            raise AccountNotFoundError("default account does not exist") from exc

    def route_phone_to_account(self, phone: str, account_id: str) -> None:
        identity = self._phone_identity(phone)
        try:
            self.repository.set_default_account(identity.id, account_id)
        except KeyError as exc:
            raise AccountNotFoundError("account is not linked to phone") from exc

    def verify_real_name(
        self, account_id: str, name: str, identity_document: str
    ) -> AccountRealNameLink:
        fingerprint = identity_document_fingerprint(identity_document)
        with self.repository.lock_real_name_subject(fingerprint):
            existing = self.repository.real_name_link_for_account(account_id)
            if existing is not None:
                raise AccountAlreadyRealNamedError("account already has a real-name link")
            subject = self.repository.get_or_create_real_name_subject(
                fingerprint, name, identity_document
            )
            if self.repository.count_active_real_name_links(fingerprint) >= 3:
                raise RealNameSlotLimitError("real-name subject has reached the 3-account limit")
            return self.repository.link_real_name_account(
                account_id, subject.id, status=RealNameSlotStatus.ACTIVE
            )

    def is_real_named(self, account_id: str) -> bool:
        return self.repository.has_active_real_name_link(account_id)

    def revoke_session(self, token: str) -> None:
        self.signer.revoke(token)

    def _phone_identity(self, phone: str) -> LoginIdentity:
        normalized_phone = normalize_phone(phone)
        identity = self.repository.get_or_create_phone_identity(normalized_phone)
        if not self.repository.accounts_for_identity(identity.id):
            raise IdentityNotFoundError("phone identity has no account")
        return identity


__all__ = [
    "AccountAlreadyRealNamedError",
    "AccountLoginNameTakenError",
    "AccountNotFoundError",
    "AccountRegistration",
    "AuthenticatedSession",
    "IdentityApplication",
    "IdentityNotFoundError",
    "InvalidCredentialsError",
    "InvalidIdentityDocumentError",
    "InvalidLoginNameError",
    "InvalidNicknameError",
    "InvalidPhoneError",
    "RealNameSlotLimitError",
]


def _hash_password(password: str) -> str:
    salt = token_bytes(16)
    iterations = 600_000
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(raw_iterations)
        )
        return compare_digest(actual, bytes.fromhex(digest_hex))
    except TypeError, ValueError:
        return False
