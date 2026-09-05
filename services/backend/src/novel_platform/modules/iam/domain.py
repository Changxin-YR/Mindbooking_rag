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


def normalize_phone(phone: str) -> str:
    normalized = phone.strip().replace(" ", "")
    if re.fullmatch(r"1[3-9]\d{9}", normalized) is None:
        raise InvalidPhoneError("phone must be a valid mainland China mobile number")
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
