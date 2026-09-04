from dataclasses import dataclass

from novel_platform.modules.iam.domain import (
    AccountRealNameLink,
    InvalidIdentityDocumentError,
    InvalidPhoneError,
    LoginIdentity,
    PlatformAccount,
    RealNameSlotStatus,
    identity_document_fingerprint,
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


@dataclass(frozen=True, slots=True)
class AccountRegistration:
    account_id: str
    identity_id: str
    phone: str


class IdentityApplication:
    def __init__(self, repository: IdentityRepository) -> None:
        self.repository = repository

    def register_phone_account(self, phone: str) -> AccountRegistration:
        normalized_phone = normalize_phone(phone)
        identity = self.repository.get_or_create_phone_identity(normalized_phone)
        account = self.repository.create_account()
        self.repository.link_account(identity.id, account.id)
        return AccountRegistration(account.id, identity.id, normalized_phone)

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
            subject = self.repository.get_or_create_real_name_subject(fingerprint, name)
            if self.repository.count_active_real_name_links(fingerprint) >= 3:
                raise RealNameSlotLimitError("real-name subject has reached the 3-account limit")
            return self.repository.link_real_name_account(
                account_id, subject.id, status=RealNameSlotStatus.ACTIVE
            )

    def _phone_identity(self, phone: str) -> LoginIdentity:
        normalized_phone = normalize_phone(phone)
        identity = self.repository.get_or_create_phone_identity(normalized_phone)
        if not self.repository.accounts_for_identity(identity.id):
            raise IdentityNotFoundError("phone identity has no account")
        return identity


__all__ = [
    "AccountAlreadyRealNamedError",
    "AccountNotFoundError",
    "AccountRegistration",
    "IdentityApplication",
    "IdentityNotFoundError",
    "InvalidIdentityDocumentError",
    "InvalidPhoneError",
    "RealNameSlotLimitError",
]
