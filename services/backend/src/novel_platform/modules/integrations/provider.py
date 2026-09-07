"""Deterministic, in-memory adapters for non-financial third-party boundaries."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import MappingProxyType
from typing import Any


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value.strip()


def _now(value: datetime | None, clock: Callable[[], datetime]) -> datetime:
    current = value or clock()
    return current if current.tzinfo is not None else current.replace(tzinfo=UTC)


def _digest(*parts: object) -> str:
    return sha256(":".join(str(part) for part in parts).encode("utf-8")).hexdigest()


class SandboxProvider:
    """Base class shared by deterministic adapters; it never performs I/O."""

    def __init__(self, provider_name: str, clock: Callable[[], datetime] | None = None) -> None:
        self.provider_name = _text(provider_name, "provider_name").upper()
        if not self.provider_name.startswith("SANDBOX_"):
            raise ValueError("NON_SANDBOX_PROVIDER_NOT_ALLOWED")
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def clock(self) -> Callable[[], datetime]:
        return self._clock

    @clock.setter
    def clock(self, value: Callable[[], datetime]) -> None:
        if not callable(value):
            raise TypeError("clock must be callable")
        self._clock = value

    @property
    def sandbox(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return self.provider_name

    def health(self) -> Mapping[str, object]:
        return MappingProxyType({"provider": self.provider_name, "status": "ok", "sandbox": True})


@dataclass(frozen=True, slots=True)
class OtpChallenge:
    phone: str
    purpose: str
    code: str
    expires_at: datetime
    request_id: str

    @property
    def otp(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class OtpVerification:
    verified: bool
    reason: str
    phone: str
    purpose: str

    @property
    def ok(self) -> bool:
        return self.verified

    def __bool__(self) -> bool:
        return self.verified


class SandboxSmsProvider(SandboxProvider):
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        super().__init__("SANDBOX_SMS", clock)
        self._challenges: dict[tuple[str, str], OtpChallenge] = {}
        self._used: set[tuple[str, str]] = set()

    def send_otp(
        self, phone: str, *, purpose: str = "LOGIN", ttl_seconds: int = 300
    ) -> OtpChallenge:
        phone = _text(phone, "phone")
        purpose = _text(purpose, "purpose").upper()
        if type(ttl_seconds) is not int or ttl_seconds <= 0:
            raise ValueError("OTP_TTL_INVALID")
        key = (phone, purpose)
        current = _now(None, self.clock)
        previous = self._challenges.get(key)
        if previous is not None and previous.expires_at > current and key not in self._used:
            return previous
        code = f"{int(_digest(self.provider_name, phone, purpose)[:8], 16) % 1_000_000:06d}"
        challenge = OtpChallenge(
            phone=phone,
            purpose=purpose,
            code=code,
            expires_at=current + timedelta(seconds=ttl_seconds),
            request_id=f"otp-{_digest(self.provider_name, phone, purpose)[:20]}",
        )
        self._challenges[key] = challenge
        return challenge

    request_otp = send_otp
    send = send_otp

    def verify_otp(
        self,
        phone: str,
        code: str,
        *,
        purpose: str = "LOGIN",
        now: datetime | None = None,
    ) -> OtpVerification:
        phone = _text(phone, "phone")
        purpose = _text(purpose, "purpose").upper()
        code = _text(code, "code")
        challenge = self._challenges.get((phone, purpose))
        if challenge is None:
            return OtpVerification(False, "OTP_NOT_FOUND", phone, purpose)
        current = _now(now, self.clock)
        key = (phone, purpose)
        if key in self._used:
            raise ValueError("OTP_ALREADY_USED")
        if current >= challenge.expires_at:
            return OtpVerification(False, "OTP_EXPIRED", phone, purpose)
        if code != challenge.code:
            return OtpVerification(False, "OTP_INVALID", phone, purpose)
        self._used.add(key)
        return OtpVerification(True, "OTP_VERIFIED", phone, purpose)


@dataclass(frozen=True, slots=True)
class OAuthAuthorizationCode:
    provider: str
    code: str
    subject: str
    redirect_uri: str
    expires_at: datetime

    @property
    def authorization_code(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class OAuthIdentity:
    provider: str
    subject: str
    identity_key: str

    @property
    def external_id(self) -> str:
        return self.identity_key

    @property
    def open_id(self) -> str:
        return self.identity_key


class SandboxOAuthProvider(SandboxProvider):
    def __init__(self, provider_name: str, clock: Callable[[], datetime] | None = None) -> None:
        super().__init__(provider_name, clock)
        self._codes: dict[str, OAuthAuthorizationCode] = {}
        self._used_codes: set[str] = set()
        self._sequence = 0

    def issue_code(
        self, subject: str, *, redirect_uri: str = "", ttl_seconds: int = 300
    ) -> OAuthAuthorizationCode:
        subject = _text(subject, "subject")
        if type(ttl_seconds) is not int or ttl_seconds <= 0:
            raise ValueError("OAUTH_CODE_TTL_INVALID")
        redirect_uri = redirect_uri.strip()
        self._sequence += 1
        code = f"{self.provider_name.lower()}-{_digest(self.provider_name, subject, redirect_uri, self._sequence)[:24]}"
        authorization = OAuthAuthorizationCode(
            self.provider_name,
            code,
            subject,
            redirect_uri,
            _now(None, self.clock) + timedelta(seconds=ttl_seconds),
        )
        self._codes[code] = authorization
        return authorization

    create_authorization_code = issue_code
    authorize = issue_code
    create_code = issue_code

    def exchange_code(self, code: str, *, now: datetime | None = None) -> OAuthIdentity:
        code = _text(code, "code")
        if code in self._used_codes:
            raise ValueError("OAUTH_CODE_ALREADY_USED")
        authorization = self._codes.get(code)
        if authorization is None:
            raise ValueError("OAUTH_CODE_NOT_FOUND")
        if _now(now, self.clock) >= authorization.expires_at:
            raise ValueError("OAUTH_CODE_EXPIRED")
        self._used_codes.add(code)
        identity_key = f"{self.provider_name.lower()}:{_digest(self.provider_name, authorization.subject)[:32]}"
        return OAuthIdentity(self.provider_name, authorization.subject, identity_key)

    consume_code = exchange_code
    exchange = exchange_code


class SandboxWechatOAuthProvider(SandboxOAuthProvider):
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        super().__init__("SANDBOX_OAUTH_WECHAT", clock)


class SandboxQqOAuthProvider(SandboxOAuthProvider):
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        super().__init__("SANDBOX_OAUTH_QQ", clock)


@dataclass(frozen=True, slots=True)
class RealNameVerification:
    verified: bool
    status: str
    subject_id: str | None
    name: str
    identity_document: str
    account_id: str | None = None

    @property
    def ok(self) -> bool:
        return self.verified

    @property
    def result(self) -> str:
        return self.status


class SandboxRealNameProvider(SandboxProvider):
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        super().__init__("SANDBOX_REALNAME", clock)

    def verify(
        self, name: str, identity_document: str, *, account_id: str | None = None
    ) -> RealNameVerification:
        name = _text(name, "name")
        identity_document = _text(identity_document, "identity_document").upper()
        valid = (
            len(identity_document) == 18
            and identity_document[:17].isdigit()
            and (identity_document[-1].isdigit() or identity_document[-1] == "X")
        )
        subject_id = f"realname:{_digest(identity_document)[:32]}" if valid else None
        return RealNameVerification(
            valid,
            "VERIFIED" if valid else "REJECTED",
            subject_id,
            name,
            identity_document,
            account_id,
        )

    verify_real_name = verify
    verify_identity = verify
    check = verify


@dataclass(frozen=True, slots=True)
class ModerationResult:
    content_id: str | None
    decision: str
    risk_level: str
    reasons: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.decision == "PASS"

    @property
    def flagged(self) -> bool:
        return not self.passed

    @property
    def status(self) -> str:
        return self.decision

    @property
    def allowed(self) -> bool:
        return self.passed


class SandboxModerationProvider(SandboxProvider):
    _blocked_terms = (
        "\u8fdd\u6cd5",
        "\u8bc8\u9a97",
        "\u8d4c\u535a",
        "\u8272\u60c5",
        "\u6b3a\u8bc8",
        "\u8fdd\u89c4",
        "\u66b4\u529b",
        "\u5e7f\u544a",
        "\u5bfc\u6d41",
        "spam",
    )

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        super().__init__("SANDBOX_MODERATION", clock)

    def moderate(self, content: str, content_id: str | None = None) -> ModerationResult:
        content = _text(content, "content")
        matches = tuple(term for term in self._blocked_terms if term in content)
        if matches:
            return ModerationResult(content_id, "BLOCK", "HIGH", matches)
        return ModerationResult(content_id, "PASS", "LOW", ())

    review = moderate
    check = moderate


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    data: bytes
    content_type: str
    etag: str

    @property
    def content(self) -> bytes:
        return self.data

    @property
    def uri(self) -> str:
        return f"sandbox://{self.key}"

    @property
    def url(self) -> str:
        return self.uri


class SandboxStorageProvider(SandboxProvider):
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        super().__init__("SANDBOX_STORAGE", clock)
        self._objects: dict[str, StoredObject] = {}

    def put_object(
        self,
        key: str,
        data: bytes | bytearray | memoryview | str,
        *,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        key = _text(key, "key")
        if isinstance(data, str):
            raw = data.encode("utf-8")
        elif isinstance(data, (bytes, bytearray, memoryview)):
            raw = bytes(data)
        else:
            raise TypeError("storage data must be bytes or text")
        content_type = _text(content_type, "content_type")
        obj = StoredObject(key, raw, content_type, _digest(key, raw.hex()))
        previous = self._objects.get(key)
        if previous is not None and previous != obj:
            raise ValueError("STORAGE_KEY_CONFLICT")
        self._objects[key] = obj
        return obj

    put = put_object
    upload = put_object

    def store(
        self,
        data: bytes | bytearray | memoryview | str,
        key: str | None = None,
        *,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        if key is None:
            raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
            key = f"objects/{_digest(raw.hex())[:32]}"
        return self.put_object(key, data, content_type=content_type)

    def get_object(self, key: str) -> StoredObject:
        key = _text(key, "key")
        try:
            return self._objects[key]
        except KeyError as exc:
            raise KeyError("STORAGE_OBJECT_NOT_FOUND") from exc

    get = get_object


@dataclass(frozen=True, slots=True)
class NotificationDelivery:
    delivery_id: str
    notification_id: str
    account_id: str
    channel: str
    payload: Mapping[str, Any]
    status: str = "DELIVERED"

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    @property
    def accepted(self) -> bool:
        return self.status == "DELIVERED"

    @property
    def id(self) -> str:
        return self.delivery_id

    @property
    def success(self) -> bool:
        return self.accepted


class SandboxNotificationProvider(SandboxProvider):
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        super().__init__("SANDBOX_NOTIFICATION", clock)
        self._deliveries: dict[str, NotificationDelivery] = {}

    def deliver(
        self,
        notification_id: str,
        account_id: str,
        channel: str,
        payload: Mapping[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> NotificationDelivery:
        notification_id = _text(notification_id, "notification_id")
        account_id = _text(account_id, "account_id")
        channel = _text(channel, "channel").upper()
        key = _text(idempotency_key, "idempotency_key") if idempotency_key else notification_id
        previous = self._deliveries.get(key)
        if previous is not None:
            if (
                previous.notification_id != notification_id
                or previous.account_id != account_id
                or previous.channel != channel
                or previous.payload != (payload or {})
            ):
                raise ValueError("NOTIFICATION_IDEMPOTENCY_CONFLICT")
            return previous
        delivery = NotificationDelivery(
            delivery_id=f"delivery-{_digest(self.provider_name, key)[:24]}",
            notification_id=notification_id,
            account_id=account_id,
            channel=channel,
            payload=payload or {},
        )
        self._deliveries[key] = delivery
        return delivery

    send = deliver
    deliver_notification = deliver

    @property
    def delivery_count(self) -> int:
        return len(self._deliveries)


class SandboxProviderRegistry:
    """Build and expose all deterministic non-payment sandbox adapters."""

    def __init__(
        self,
        settings: object | None = None,
        *,
        sms_provider: str = "SANDBOX_SMS",
        oauth_wechat_provider: str = "SANDBOX_OAUTH_WECHAT",
        oauth_qq_provider: str = "SANDBOX_OAUTH_QQ",
        realname_provider: str = "SANDBOX_REALNAME",
        moderation_provider: str = "SANDBOX_MODERATION",
        storage_provider: str = "SANDBOX_STORAGE",
        notification_provider: str = "SANDBOX_NOTIFICATION",
        provider_names: Mapping[str, str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        values = {
            "sms_provider": sms_provider,
            "oauth_wechat_provider": oauth_wechat_provider,
            "oauth_qq_provider": oauth_qq_provider,
            "realname_provider": realname_provider,
            "moderation_provider": moderation_provider,
            "storage_provider": storage_provider,
            "notification_provider": notification_provider,
        }
        if settings is not None:
            setting_values = (
                settings
                if isinstance(settings, Mapping)
                else {key: getattr(settings, key, values[key]) for key in values}
            )
            values.update({key: str(setting_values.get(key, values[key])) for key in values})
        if provider_names:
            aliases = {
                "sms": "sms_provider",
                "oauth_wechat": "oauth_wechat_provider",
                "oauth_qq": "oauth_qq_provider",
                "realname": "realname_provider",
                "real_name": "realname_provider",
                "moderation": "moderation_provider",
                "storage": "storage_provider",
                "object_storage": "storage_provider",
                "notification": "notification_provider",
            }
            aliases.update({key.upper(): value for key, value in aliases.items()})
            aliases.update(
                {
                    "SANDBOX_SMS": "sms_provider",
                    "SANDBOX_OAUTH_WECHAT": "oauth_wechat_provider",
                    "SANDBOX_OAUTH_QQ": "oauth_qq_provider",
                    "SANDBOX_REALNAME": "realname_provider",
                    "SANDBOX_MODERATION": "moderation_provider",
                    "SANDBOX_STORAGE": "storage_provider",
                    "SANDBOX_NOTIFICATION": "notification_provider",
                }
            )
            values.update(
                {
                    aliases.get(key, aliases.get(key.upper(), key)): value
                    for key, value in provider_names.items()
                    if aliases.get(key, aliases.get(key.upper(), key)) in values
                }
            )
        normalized = {key: _text(value, key).upper() for key, value in values.items()}
        expected = {
            "sms_provider": "SANDBOX_SMS",
            "oauth_wechat_provider": "SANDBOX_OAUTH_WECHAT",
            "oauth_qq_provider": "SANDBOX_OAUTH_QQ",
            "realname_provider": "SANDBOX_REALNAME",
            "moderation_provider": "SANDBOX_MODERATION",
            "storage_provider": "SANDBOX_STORAGE",
            "notification_provider": "SANDBOX_NOTIFICATION",
        }
        for key, provider_name in normalized.items():
            if provider_name != expected[key]:
                raise ValueError("NON_SANDBOX_PROVIDER_NOT_ALLOWED")
        self.sms = SandboxSmsProvider(clock)
        self.oauth_wechat = SandboxWechatOAuthProvider(clock)
        self.oauth_qq = SandboxQqOAuthProvider(clock)
        self.realname = SandboxRealNameProvider(clock)
        self.moderation = SandboxModerationProvider(clock)
        self.storage = SandboxStorageProvider(clock)
        self.notification = SandboxNotificationProvider(clock)
        self.providers: Mapping[str, SandboxProvider] = MappingProxyType(
            {
                provider.provider_name: provider
                for provider in (
                    self.sms,
                    self.oauth_wechat,
                    self.oauth_qq,
                    self.realname,
                    self.moderation,
                    self.storage,
                    self.notification,
                )
            }
        )

    def get(self, provider_name: str) -> SandboxProvider:
        provider_name = _text(provider_name, "provider_name").upper()
        provider_name = {
            "SMS": "SANDBOX_SMS",
            "OAUTH_WECHAT": "SANDBOX_OAUTH_WECHAT",
            "OAUTH_QQ": "SANDBOX_OAUTH_QQ",
            "REALNAME": "SANDBOX_REALNAME",
            "REAL_NAME": "SANDBOX_REALNAME",
            "MODERATION": "SANDBOX_MODERATION",
            "STORAGE": "SANDBOX_STORAGE",
            "OBJECT_STORAGE": "SANDBOX_STORAGE",
            "NOTIFICATION": "SANDBOX_NOTIFICATION",
        }.get(provider_name, provider_name)
        try:
            return self.providers[provider_name]
        except KeyError as exc:
            raise ValueError("UNSUPPORTED_SANDBOX_PROVIDER") from exc

    def health(self) -> Mapping[str, Mapping[str, object]]:
        return MappingProxyType(
            {name: provider.health() for name, provider in self.providers.items()}
        )

    @property
    def health_metadata(self) -> Mapping[str, Mapping[str, object]]:
        return self.health()

    @property
    def health_status(self) -> Mapping[str, str]:
        return MappingProxyType({name: "ok" for name in self.providers})

    provider = get

    @classmethod
    def from_settings(cls, settings: object) -> SandboxProviderRegistry:
        return cls(settings)


SandboxIntegrationRegistry = SandboxProviderRegistry
SandboxSMSProvider = SandboxSmsProvider
SandboxOAuthWechatProvider = SandboxWechatOAuthProvider
SandboxOAuthQQProvider = SandboxQqOAuthProvider


def build_sandbox_provider_registry(
    *,
    sms_provider: str = "SANDBOX_SMS",
    oauth_wechat_provider: str = "SANDBOX_OAUTH_WECHAT",
    oauth_qq_provider: str = "SANDBOX_OAUTH_QQ",
    realname_provider: str = "SANDBOX_REALNAME",
    moderation_provider: str = "SANDBOX_MODERATION",
    storage_provider: str = "SANDBOX_STORAGE",
    notification_provider: str = "SANDBOX_NOTIFICATION",
    clock: Callable[[], datetime] | None = None,
) -> SandboxProviderRegistry:
    return SandboxProviderRegistry(
        sms_provider=sms_provider,
        oauth_wechat_provider=oauth_wechat_provider,
        oauth_qq_provider=oauth_qq_provider,
        realname_provider=realname_provider,
        moderation_provider=moderation_provider,
        storage_provider=storage_provider,
        notification_provider=notification_provider,
        clock=clock,
    )


__all__ = [
    "ModerationResult",
    "NotificationDelivery",
    "OAuthAuthorizationCode",
    "OAuthIdentity",
    "OtpChallenge",
    "OtpVerification",
    "RealNameVerification",
    "SandboxIntegrationRegistry",
    "SandboxModerationProvider",
    "SandboxNotificationProvider",
    "SandboxOAuthProvider",
    "SandboxOAuthQQProvider",
    "SandboxOAuthWechatProvider",
    "SandboxProvider",
    "SandboxProviderRegistry",
    "SandboxQqOAuthProvider",
    "SandboxRealNameProvider",
    "SandboxSMSProvider",
    "SandboxSmsProvider",
    "SandboxStorageProvider",
    "SandboxWechatOAuthProvider",
    "StoredObject",
    "build_sandbox_provider_registry",
]
