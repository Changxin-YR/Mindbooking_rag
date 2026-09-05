"""Signed session primitives for HTTP adapters."""

import json
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from hmac import compare_digest
from hmac import new as hmac_new
from secrets import token_hex


@dataclass(frozen=True, slots=True)
class SessionClaims:
    account_id: str
    expires_at: int
    subject_type: str = "ACCOUNT"
    session_id: str = ""


class SessionSigner:
    def __init__(self, secret: str, ttl_seconds: int = 86_400) -> None:
        if not secret:
            raise ValueError("session secret is required")
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = ttl_seconds
        self._revoked: set[str] = set()
        self._session_store: object | None = None

    def bind_session_store(self, store: object) -> None:
        self._session_store = store

    def issue(self, account_id: str) -> str:
        return self._issue(account_id, "ACCOUNT")

    def issue_staff(self, staff_id: str) -> str:
        return self._issue(staff_id, "STAFF")

    def _issue(self, subject_id: str, subject_type: str) -> str:
        if not subject_id:
            raise ValueError("subject_id is required")
        session_id = token_hex(16)
        payload = {
            "account_id": subject_id,
            "expires_at": int(time.time()) + self._ttl_seconds,
            "session_id": session_id,
            "subject_type": subject_type,
        }
        encoded = _encode(payload)
        signature = hmac_new(self._secret, encoded.encode("ascii"), sha256).digest()
        token = f"{encoded}.{_b64encode(signature)}"
        if subject_type == "ACCOUNT" and self._session_store is not None:
            create = getattr(self._session_store, "create_session", None)
            if callable(create):
                create(
                    session_id,
                    subject_id,
                    self._fingerprint(token),
                    datetime_from_timestamp(payload["expires_at"]),
                )
        return token

    def verify(self, token: str) -> SessionClaims | None:
        try:
            if self._fingerprint(token) in self._revoked:
                return None
            encoded, signature = token.split(".", 1)
            encoded_bytes = _b64decode(encoded)
            signature_bytes = _b64decode(signature)
            if _b64encode(encoded_bytes) != encoded or _b64encode(signature_bytes) != signature:
                return None
            expected = hmac_new(self._secret, encoded.encode("ascii"), sha256).digest()
            if not compare_digest(signature_bytes, expected):
                return None
            payload = json.loads(encoded_bytes.decode("utf-8"))
            account_id = payload["account_id"]
            expires_at = int(payload["expires_at"])
            subject_type = payload.get("subject_type", "ACCOUNT")
            session_id = payload.get("session_id", "")
            if not isinstance(account_id, str) or not account_id or expires_at <= int(time.time()):
                return None
            if subject_type not in {"ACCOUNT", "STAFF"} or not isinstance(session_id, str):
                return None
        except ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError:
            return None
        claims = SessionClaims(account_id, expires_at, subject_type, session_id)
        if subject_type == "ACCOUNT" and self._session_store is not None:
            active = getattr(self._session_store, "session_active", None)
            if callable(active) and not active(
                session_id, account_id, self._fingerprint(token), expires_at
            ):
                return None
        return claims

    def revoke(self, token: str) -> None:
        if token:
            fingerprint = self._fingerprint(token)
            self._revoked.add(fingerprint)
            if self._session_store is not None:
                try:
                    encoded, _ = token.split(".", 1)
                    payload = json.loads(_b64decode(encoded).decode("utf-8"))
                    if payload.get("subject_type", "ACCOUNT") == "ACCOUNT":
                        revoke = getattr(self._session_store, "revoke_session", None)
                        if callable(revoke):
                            revoke(str(payload["session_id"]), fingerprint)
                except KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError:
                    pass

    @staticmethod
    def _fingerprint(token: str) -> str:
        return sha256(token.encode("ascii", "ignore")).hexdigest()


def _b64encode(value: bytes) -> str:
    return urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _encode(payload: dict[str, object]) -> str:
    value = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _b64encode(value)


def datetime_from_timestamp(value: object) -> datetime:
    return datetime.fromtimestamp(int(str(value)), UTC)
