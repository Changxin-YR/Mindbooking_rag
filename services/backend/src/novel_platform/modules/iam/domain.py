import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from hmac import new as hmac_new
from os import getenv


class IdentityType(StrEnum):
    PHONE = "PHONE"


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"


class RealNameSlotStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PENDING_RELEASE = "PENDING_RELEASE"
    RELEASED = "RELEASED"
    BLOCKED_BY_VIOLATION = "BLOCKED_BY_VIOLATION"


@dataclass(frozen=True, slots=True)
class LoginIdentity:
    id: str
    identity_type: IdentityType
    normalized_value: str


@dataclass(frozen=True, slots=True)
class PlatformAccount:
    id: str
    status: AccountStatus
    account_no: str = ""
    nickname: str | None = None
    login_name: str | None = None


@dataclass(frozen=True, slots=True)
class RealNameSubject:
    id: str
    id_fingerprint: str
    name: str


@dataclass(frozen=True, slots=True)
class AccountRealNameLink:
    account_id: str
    real_name_subject_id: str
    slot_status: RealNameSlotStatus


class InvalidPhoneError(ValueError):
    pass


class InvalidIdentityDocumentError(ValueError):
    pass


class InvalidNicknameError(ValueError):
    pass


class InvalidLoginNameError(ValueError):
    pass


class AccountLoginNameTakenError(ValueError):
    pass


def normalize_phone(phone: str) -> str:
    normalized = phone.strip().replace(" ", "")
    if re.fullmatch(r"1[3-9]\d{9}", normalized) is None:
        raise InvalidPhoneError("phone must be a valid mainland China mobile number")
    return normalized


def normalize_nickname(nickname: str) -> str:
    normalized = nickname.strip()
    if not 1 <= len(normalized) <= 32:
        raise InvalidNicknameError("nickname must contain 1 to 32 characters")
    return normalized


def normalize_login_name(login_name: str) -> str:
    normalized = login_name.strip().lower()
    if re.fullmatch(r"[a-z][a-z0-9_]{2,31}", normalized) is None:
        raise InvalidLoginNameError(
            "login_name must start with a letter and contain 3 to 32 letters, digits, or underscores"
        )
    if normalized in {"admin", "support", "system", "root", "null", "undefined"}:
        raise InvalidLoginNameError("login_name is reserved")
    return normalized


def identity_document_fingerprint(identity_document: str, secret: str | None = None) -> str:
    normalized = identity_document.strip().upper()
    if re.fullmatch(r"[0-9]{17}[0-9X]", normalized) is None:
        raise InvalidIdentityDocumentError("identity_document must be a valid identity number")
    key = (
        secret
        or getenv("PII_FINGERPRINT_SECRET")
        or getenv("HMAC_SECRET")
        or "development-only-pii-key"
    ).encode("utf-8")
    return hmac_new(key, normalized.encode("ascii"), sha256).hexdigest()


def public_account_no(account_id: str) -> str:
    """Derive a stable, non-secret public account identifier from the immutable id."""
    return "MB" + sha256(account_id.encode("utf-8")).hexdigest()[:10].upper()
